# screenshot_tool.py
import asyncio
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ── 自定义异常 ─────────────────────────────────────────────────────────────

class PageNotFoundError(Exception):
    """页面内容不存在（如头条「抱歉，你访问的内容不存在」），应写入错误原因到表格"""
    pass

class PageBlockedError(Exception):
    """页面被反爬拦截或重定向到登录页"""
    pass


# ── 字体（兼容 macOS / Windows / Linux） ──────────────────────────────────
_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

def _load_font(size: int = 48):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    logger.warning("未找到中文字体，水印中文可能显示为方块")
    return ImageFont.load_default()


# ── 反爬检测关键词 ─────────────────────────────────────────────────────────
_BLOCK_SIGNALS = [
    "host not in allowlist",
    "访问被拒绝",
    "access denied",
    "403 forbidden",
    "captcha",
    "please verify",
    "robot check",
    "unusual traffic",
]

# ── 今日头条 selector 策略 ─────────────────────────────────────────────────
#
# 根据截图分析的实际页面结构（无痕/无 cookie 访问）：
#   - 文章正文渲染完成后，继续向下滚动，评论区自动出现（无需点击）
#   - 评论区顶部显示「评论 N」标题，下方是「请先登录后发表评论～」
#   - 左侧「评论」按钮点击只会弹出登录框，不展开评论区
#   - 目标：截到「评论 N」标题出现的位置即可，这是评论区的顶部锚点
#
# 关键结论：
#   1. 不需要点击任何按钮，滚动到底部评论区自动渲染
#   2. click_comment_trigger 应设为 False
#   3. 评论区 selector 找「评论」标题或评论容器顶部

# 评论区顶部标题/容器（滚动到底后自动出现，无需点击）
TOUTIAO_COMMENT_AREA_SELECTORS = [
    # 评论数标题，如「评论 0」「评论 163」—— 最可靠的锚点
    "//h2[contains(text(),'评论')]",              # XPath 文字匹配
    "//div[contains(@class,'comment') and contains(text(),'评论')]",
    # 评论区容器
    "#comment-area",
    ".comment-area",
    "[data-e2e='comment-area']",
    "[data-e2e='comment-list']",
    "div[class*='CommentArea']",
    "div[class*='comment-area']",
    "div[class*='commentArea']",
    # 登录提示（未登录时评论区底部显示）
    "//span[contains(text(),'登录后发表评论')]",
    "//p[contains(text(),'请先')]",
    # 评论列表容器
    "div[class*='CommentList']",
    "div[class*='comment-list']",
]

# 兜底：只截文章正文末尾（不含评论区）
TOUTIAO_ARTICLE_END_SELECTORS = [
    "div[class*='ArticleContent']",
    "div[class*='article-content']",
    ".article-content",
    "[data-e2e='article-content']",
    "article",
    ".article",
    "#article-content",
    ".content-area",
    "body",   # 最终保底
]


# ── 水印 ──────────────────────────────────────────────────────────────────

def add_date_watermark(image_bytes: bytes, position: str = 'top-right') -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    now = datetime.now()
    date_text = now.strftime("%Y年%m月%d日")
    time_text = now.strftime("%H:%M:%S")
    font = _load_font(48)

    date_bbox = draw.textbbox((0, 0), date_text, font=font)
    time_bbox = draw.textbbox((0, 0), time_text, font=font)
    date_h = date_bbox[3] - date_bbox[1]
    time_h = time_bbox[3] - time_bbox[1]
    max_w = max(date_bbox[2] - date_bbox[0], time_bbox[2] - time_bbox[0])

    line_spacing, pad_h, pad_top, pad_bottom, margin = 4, 16, 14, 24, 20
    box_w = max_w + pad_h * 2
    box_h = date_h + line_spacing + time_h + pad_top + pad_bottom

    pos_map = {
        'top-right':    (img.width - box_w - margin, margin),
        'top-left':     (margin, margin),
        'bottom-right': (img.width - box_w - margin, img.height - box_h - margin),
        'bottom-left':  (margin, img.height - box_h - margin),
    }
    rx, ry = pos_map.get(position, pos_map['top-right'])

    draw.rectangle([rx, ry, rx + box_w, ry + box_h], fill=(0, 0, 0, 160))
    draw.text((rx + pad_h, ry + pad_top), date_text, fill=(255, 255, 255, 255), font=font)
    draw.text((rx + pad_h, ry + pad_top + date_h + line_spacing), time_text, fill=(255, 255, 255, 255), font=font)

    out = io.BytesIO()
    Image.alpha_composite(img, overlay).convert("RGB").save(out, format='PNG')
    return out.getvalue()


# ── 内部工具 ──────────────────────────────────────────────────────────────

async def _check_blocked(page: Page) -> Optional[str]:
    """
    检测页面异常状态：
      - 内容不存在 → 抛出 PageNotFoundError（调用方应写入错误原因到表格）
      - 反爬/登录重定向 → 抛出 PageBlockedError
      - 正常 → 返回 None
    """
    try:
        current_url = page.url

        # 重定向到登录页
        if "sso.toutiao.com" in current_url or "/login" in current_url:
            raise PageBlockedError(f"被重定向到登录页: {current_url}")

        title = await page.title()
        body_text = (await page.evaluate("document.body.innerText || ''")).lower()

        # ── 内容不存在检测（优先级最高，应写入表格而非重试）──
        NOT_FOUND_SIGNALS = [
            "你访问的内容不存在",
            "内容不存在",
            "页面不存在",
            "该内容已被删除",
            "内容已下线",
            "404",
        ]
        for signal in NOT_FOUND_SIGNALS:
            if signal in body_text or signal in title.lower():
                raise PageNotFoundError(f"内容不存在（匹配: '{signal}'）")

        # ── 反爬拦截检测 ──
        for signal in _BLOCK_SIGNALS:
            if signal in body_text or signal in title.lower():
                raise PageBlockedError(f"含拦截信号 '{signal}'（title={title!r}）")

        if len(body_text.strip()) < 100:
            raise PageBlockedError(f"内容过短（{len(body_text.strip())} 字），疑似拦截（title={title!r}）")

    except (PageNotFoundError, PageBlockedError):
        raise   # 直接向上传递，不吞掉
    except Exception as e:
        logger.debug(f"页面状态检测异常（忽略）: {e}")
    return None


async def _try_click(page: Page, selector: str) -> bool:
    """尝试点击一个 selector，成功返回 True"""
    try:
        if selector.startswith("//"):
            locator = page.locator(f"xpath={selector}").first
        else:
            locator = page.locator(selector).first
        if await locator.is_visible(timeout=2000):
            await locator.click(timeout=3000)
            return True
    except Exception as e:
        logger.debug(f"点击 {selector!r} 失败: {e}")
    return False


async def _find_first_selector(
    page: Page,
    candidates: list[str],
    timeout_each: int = 3000,
) -> Optional[str]:
    """按顺序尝试 selector，返回第一个命中的"""
    for sel in candidates:
        try:
            locator_str = f"xpath={sel}" if sel.startswith("//") else sel
            await page.wait_for_selector(locator_str, timeout=timeout_each)
            logger.info(f"命中 selector: {sel}")
            return sel
        except PlaywrightTimeoutError:
            logger.debug(f"未命中: {sel}")
    return None


async def _get_element_bottom(page: Page, selector: str) -> Optional[dict]:
    """获取元素底部坐标（页面坐标系）和页面宽度"""
    js_sel = f"xpath={selector}" if selector.startswith("//") else selector
    return await page.evaluate('''
        (sel) => {
            const el = sel.startsWith("xpath=")
                ? document.evaluate(sel.slice(6), document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue
                : document.querySelector(sel);
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {
                bottom: rect.bottom + window.scrollY,
                width: document.documentElement.scrollWidth
            };
        }
    ''', js_sel)


async def _dump_debug(page: Page, filename: str):
    """保存调试截图 + 打印 id/class 信息"""
    try:
        await page.screenshot(path=filename, full_page=True)
        ids = await page.evaluate(
            "[...document.querySelectorAll('[id]')].map(e => e.id).filter(Boolean)"
        )
        cls = await page.evaluate('''() => [...new Set(
            [...document.querySelectorAll("[class]")]
                .flatMap(e => [...e.classList])
                .filter(c => /comment|discuss|reply/i.test(c))
        )]''')
        logger.warning(f"调试截图已保存: {filename}")
        logger.warning(f"所有 id: {ids}")
        logger.warning(f"含 comment/discuss/reply 的 class: {cls}")
    except Exception:
        pass


# ── 主截图函数 ─────────────────────────────────────────────────────────────

async def take_screenshot(
    url: str,
    selector: str | list[str],
    output_path: str | Path = None,
    add_watermark: bool = True,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    goto_timeout: int = 45_000,
    selector_timeout: int = 5_000,
    click_comment_trigger: bool = False,
) -> bytes:
    """
    截取指定 URL 从顶部到目标元素底部的长图，返回 PNG 字节数据。

    selector 支持：
        - 字符串：单个 CSS selector
        - 列表：多个候选，按顺序尝试，命中第一个
        - // 开头视为 XPath

    click_comment_trigger：
        True 时，加载完先点击今日头条评论触发按钮，再等 selector
    """
    candidates = [selector] if isinstance(selector, str) else list(selector)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ]
        )
        # 不设置 storage_state = 无 cookie = 等效无痕模式
        # 这是今日头条能正常加载的关键（有 cookie 反而会被重定向登录）
        context = await browser.new_context(
            viewport={'width': viewport_width, 'height': viewport_height},
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )

        # 1. 加载页面
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=goto_timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"domcontentloaded 超时，继续: {url}")

        await page.wait_for_timeout(2000)

        # 2. 页面状态检测：内容不存在 → PageNotFoundError，反爬 → PageBlockedError
        #    两种异常都向上传递，让调用方决定如何处理（写表格 or 重试 or 跳过）
        try:
            await _check_blocked(page)
        except (PageNotFoundError, PageBlockedError):
            await _dump_debug(page, "debug_blocked.png")
            await browser.close()
            raise   # 直接向上抛，不包装

        # 3. 分段慢速滚动到底部，确保触发评论区懒加载
        # 今日头条评论区在滚动到文章末尾后才渲染，一次性跳到底部可能跳过懒加载触发点
        await page.evaluate('''async () => {
            await new Promise(resolve => {
                const distance = 600;   // 每次滚动距离（px）
                const delay = 200;      // 每次间隔（ms）
                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    if (window.scrollY + window.innerHeight >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, delay);
            });
        }''')
        await page.wait_for_timeout(2000)   # 等待评论区 JS 渲染
        await page.evaluate('window.scrollTo(0, 0)')
        await page.wait_for_timeout(300)

        # 4. 点击评论触发按钮（今日头条评论区默认折叠，需点击展开）
        if click_comment_trigger:
            for trigger_sel in TOUTIAO_COMMENT_TRIGGER_SELECTORS:
                if await _try_click(page, trigger_sel):
                    logger.info(f"已点击评论触发按钮: {trigger_sel}")
                    await page.wait_for_timeout(1500)
                    break
            else:
                logger.warning("未找到评论触发按钮，继续尝试 selector")

        # 5. 多候选 selector 探测
        matched = await _find_first_selector(page, candidates, timeout_each=selector_timeout)

        if matched is None:
            await _dump_debug(page, "debug_no_selector.png")
            await browser.close()
            raise ValueError(
                f"所有 {len(candidates)} 个 selector 均未命中，"
                f"请查看 debug_no_selector.png 更新 selector。URL: {url}"
            )

        # 6. 获取元素底部坐标
        info = await _get_element_bottom(page, matched)
        if not info:
            await browser.close()
            raise ValueError(f"获取元素坐标失败: {matched}")

        target_bottom_y = info['bottom']
        page_w = info['width']

        # 7. 截完整长图
        screenshot_bytes = await page.screenshot(full_page=True)
        await browser.close()

    # 8. 裁剪到元素底部
    img = Image.open(io.BytesIO(screenshot_bytes))
    scale = img.width / page_w if page_w else 1.0
    crop_h = int(target_bottom_y * scale)
    cropped = img.crop((0, 0, img.width, min(crop_h, img.height)))

    out = io.BytesIO()
    cropped.save(out, format='PNG')
    img_bytes = out.getvalue()

    if add_watermark:
        img_bytes = add_date_watermark(img_bytes, position='top-right')

    if output_path:
        Path(output_path).write_bytes(img_bytes)

    return img_bytes


# ── 今日头条快捷函数 ───────────────────────────────────────────────────────

async def take_toutiao_screenshot(
    url: str,
    output_path: str | Path = None,
    add_watermark: bool = True,
    include_comments: bool = True,
) -> bytes:
    """
    今日头条文章截图快捷入口。

    实际页面行为（根据截图确认）：
      - 无 cookie 访问可正常加载文章
      - 评论区在滚动到文章末尾后自动渲染，无需点击
      - 未登录时评论区显示「请先登录后发表评论～」

    include_comments=True（默认）：截到评论区顶部（含「评论 N」标题）
    include_comments=False：只截文章正文，速度更快
    """
    if include_comments:
        return await take_screenshot(
            url=url,
            selector=TOUTIAO_COMMENT_AREA_SELECTORS,
            output_path=output_path,
            add_watermark=add_watermark,
            click_comment_trigger=False,   # 评论区无需点击，滚动后自动出现
        )
    else:
        return await take_screenshot(
            url=url,
            selector=TOUTIAO_ARTICLE_END_SELECTORS,
            output_path=output_path,
            add_watermark=add_watermark,
            click_comment_trigger=False,
        )
