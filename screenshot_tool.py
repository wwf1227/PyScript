# screenshot_tool.py
import asyncio
import io
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# 字体候选路径（按优先级，兼容 macOS / Windows / Linux）
_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",           # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc",     # macOS 备选
    "C:/Windows/Fonts/msyh.ttc",                    # Windows 微软雅黑
    "C:/Windows/Fonts/simsun.ttc",                  # Windows 宋体
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", # Linux WQY
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto
]


def _load_font(size: int = 48) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    logger.warning("未找到中文字体，使用 Pillow 默认字体（中文可能显示为方块）")
    return ImageFont.load_default()


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
    date_w, date_h = date_bbox[2] - date_bbox[0], date_bbox[3] - date_bbox[1]
    time_w, time_h = time_bbox[2] - time_bbox[0], time_bbox[3] - time_bbox[1]

    max_w = max(date_w, time_w)
    line_spacing = 4
    pad_h, pad_top, pad_bottom = 16, 14, 24
    margin = 20
    total_text_h = date_h + line_spacing + time_h

    box_w = max_w + pad_h * 2
    box_h = total_text_h + pad_top + pad_bottom

    positions = {
        'top-right':    (img.width - box_w - margin, margin),
        'top-left':     (margin, margin),
        'bottom-right': (img.width - box_w - margin, img.height - box_h - margin),
        'bottom-left':  (margin, img.height - box_h - margin),
    }
    rx, ry = positions.get(position, positions['top-right'])

    draw.rectangle([rx, ry, rx + box_w, ry + box_h], fill=(0, 0, 0, 160))
    draw.text((rx + pad_h, ry + pad_top), date_text, fill=(255, 255, 255, 255), font=font)
    draw.text((rx + pad_h, ry + pad_top + date_h + line_spacing), time_text, fill=(255, 255, 255, 255), font=font)

    composited = Image.alpha_composite(img, overlay).convert("RGB")
    out = io.BytesIO()
    composited.save(out, format='PNG')
    return out.getvalue()


async def take_screenshot(
    url: str,
    selector: str,
    output_path: str | Path = None,
    add_watermark: bool = True,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    goto_timeout: int = 45_000,       # goto 超时（ms）
    selector_timeout: int = 20_000,   # 等待元素超时（ms）
) -> bytes:
    """
    截取指定 URL 从顶部到目标元素底部的长图，返回 PNG 字节数据。

    关键改动：
    - wait_until 改为 'domcontentloaded'（而非 networkidle），
      避免新闻/社交类站点因持续心跳请求导致永久等待。
    - 页面加载后主动等待 selector 出现，若超时抛出清晰异常。
    - 截图改为直接截取 clip 区域，避免截全屏再裁剪的内存浪费。
    """
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

        # 隐藏 webdriver 标志
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )

        try:
            # ✅ 关键修复：用 domcontentloaded 代替 networkidle
            #    新闻/社交类页面有持续心跳请求，networkidle 永远不会触发
            await page.goto(url, wait_until='domcontentloaded', timeout=goto_timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"页面加载超时（domcontentloaded），尝试继续: {url}")
            # 即使 domcontentloaded 超时，页面可能已有足够内容，继续尝试

        # 等待页面稳定（JS 渲染评论区需要额外时间）
        await page.wait_for_timeout(2000)

        # 触发懒加载
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(1500)
        await page.evaluate('window.scrollTo(0, 0)')
        await page.wait_for_timeout(500)

        # 等待目标元素出现
        try:
            await page.wait_for_selector(selector, timeout=selector_timeout)
        except PlaywrightTimeoutError:
            await browser.close()
            raise ValueError(
                f"在 {selector_timeout}ms 内未找到元素 '{selector}'，"
                f"页面可能有反爬或需要登录: {url}"
            )

        # 获取目标元素底部坐标
        element_info = await page.evaluate('''
            (selector) => {
                const el = document.querySelector(selector);
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {
                    bottom: rect.bottom + window.scrollY,
                    width: document.documentElement.scrollWidth
                };
            }
        ''', selector)

        if not element_info:
            await browser.close()
            raise ValueError(f"未找到元素: {selector}")

        target_bottom_y = element_info['bottom']  # 页面坐标系，元素底部距顶部距离
        page_w = element_info['width']

        # 截完整长页面（full_page=True 才能覆盖视口以外的区域）
        screenshot_bytes = await page.screenshot(full_page=True)
        await browser.close()

    # 裁剪：从顶部截到元素底部
    # full_page 图片宽度 = 实际渲染宽度，需换算缩放比
    img = Image.open(io.BytesIO(screenshot_bytes))
    scale = img.width / page_w if page_w else 1.0
    crop_h = int(target_bottom_y * scale)
    cropped = img.crop((0, 0, img.width, min(crop_h, img.height)))

    out = io.BytesIO()
    cropped.save(out, format='PNG')
    screenshot_bytes = out.getvalue()

    if add_watermark:
        screenshot_bytes = add_date_watermark(screenshot_bytes, position='top-right')

    if output_path:
        Path(output_path).write_bytes(screenshot_bytes)

    return screenshot_bytes
