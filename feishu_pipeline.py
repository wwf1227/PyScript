#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书表格截图上传工具 - Pipeline 版本

架构：
  读表格 → [Task Queue] → 并发截图/下载 → [Result Queue] → 并发上传飞书 → 统计

核心设计：
  - 全程 aiohttp，无 requests，无 run_in_executor
  - 截图（慢，2并发）与上传（快，5并发）解耦，互不等待
  - Token 自动缓存 + 续期
  - 每阶段独立异常隔离，单行失败不影响整体
"""

import asyncio
import base64
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

from screenshot_tool import (
    take_screenshot, take_toutiao_screenshot,
    TOUTIAO_COMMENT_AREA_SELECTORS,
    PageNotFoundError, PageBlockedError,
)

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Task:
    """从表格读出的单行任务"""
    row_index: int          # 飞书表格中的实际行号
    cell_range: str         # 写入目标单元格，如 "G10:G10"
    url: str                # 图片 URL 或需截图的页面 URL
    is_screenshot: bool     # True = 需要 Playwright 截图；False = 直接下载图片


@dataclass
class Result:
    """截图/下载结果"""
    task: Task
    image_bytes: Optional[bytes] = None
    error: Optional[str] = None
    not_found: bool = False     # True 表示内容不存在，应写入错误原因到表格

    @property
    def ok(self) -> bool:
        return self.image_bytes is not None


@dataclass
class Stats:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    not_found: int = 0          # 内容不存在，已将原因写入表格
    errors: list = field(default_factory=list)

    def report(self, total: int, duration: float) -> str:
        lines = [
            "=" * 60,
            f"✨ 处理完成！",
            f"📊 总计: {total} 行  ✅ 成功: {self.success}  ❌ 失败: {self.failed}  "
            f"🚫 不存在: {self.not_found}  ⏭️  跳过: {self.skipped}",
            f"⏱️  耗时: {duration:.1f}s  🚀 均速: {total / duration:.2f} 行/s",
        ]
        if self.errors:
            lines.append("--- 错误详情 ---")
            lines.extend(f"  {e}" for e in self.errors[-20:])  # 最多展示 20 条
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 需要截图的域名（其余 URL 视为直接图片下载）
# ---------------------------------------------------------------------------

SCREENSHOT_DOMAINS = {"toutiao.com", "weibo.com", "weibo.cn", "douyin.com", "bilibili.com"}
COMMENT_SELECTOR = "#comment-area > div.main-input"


def _needs_screenshot(url: str) -> bool:
    return any(d in url for d in SCREENSHOT_DOMAINS)


# ---------------------------------------------------------------------------
# Token 管理（独立，便于复用）
# ---------------------------------------------------------------------------

class FeishuToken:
    """飞书 tenant_access_token 管理，支持文件缓存和自动续期"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        cache_file: str = "data/feishu_token_cache.json",
        base_url: str = "https://open.feishu.cn",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.cache_path = Path(cache_file)
        self.base_url = base_url
        self._token: Optional[str] = None
        self._expire_time: float = 0.0

    def _load_cache(self) -> bool:
        """从文件缓存加载，有效则返回 True"""
        if not self.cache_path.exists():
            return False
        try:
            cache = json.loads(self.cache_path.read_text())
            if datetime.now().timestamp() < cache.get("expire_time", 0) - 600:
                self._token = cache["token"]
                self._expire_time = cache["expire_time"]
                logger.info("✅ 使用缓存 Token")
                return True
        except Exception as e:
            logger.warning(f"读取 Token 缓存失败: {e}")
        return False

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps({"token": self._token, "expire_time": self._expire_time})
        )

    async def get(self, session: aiohttp.ClientSession) -> str:
        """获取有效 Token，过期自动刷新"""
        if self._token and datetime.now().timestamp() < self._expire_time - 600:
            return self._token
        if self._load_cache():
            return self._token

        logger.info("🔑 正在获取新 Token...")
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        async with session.post(
            url,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            body = await resp.json()

        if body.get("code") != 0:
            raise RuntimeError(f"获取 Token 失败: {body}")

        self._token = body["tenant_access_token"]
        self._expire_time = datetime.now().timestamp() + body["expire"]
        self._save_cache()
        logger.info("✅ Token 获取成功")
        return self._token


# ---------------------------------------------------------------------------
# 飞书表格操作（纯异步）
# ---------------------------------------------------------------------------

class FeishuSheet:
    """飞书表格读写，依赖外部传入的 aiohttp.ClientSession"""

    def __init__(
        self,
        table_name: str,
        sheet_name: str,
        read_column: str,
        write_column: str,
        base_url: str = "https://open.feishu.cn",
    ):
        self.table_name = table_name
        self.sheet_name = sheet_name
        self.read_column = read_column
        self.write_column = write_column
        self.base_url = base_url

    def cell_range(self, row: int) -> str:
        return f"{self.write_column}{row}:{self.write_column}{row}"

    async def read_values(
        self,
        session: aiohttp.ClientSession,
        token: str,
        start_row: int,
        end_row: int,
    ) -> Optional[list]:
        """读取指定行范围的数据"""
        url = (
            f"{self.base_url}/open-apis/sheets/v2/spreadsheets"
            f"/{self.table_name}/values"
            f"/{self.sheet_name}!{self.read_column}{start_row}"
            f":{self.read_column}{end_row}"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with session.get(
                url,
                headers=headers,
                params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                body = await resp.json()
            if body.get("code") != 0:
                logger.error(f"读取表格失败: {body}")
                return None
            values = body["data"]["valueRange"]["values"]
            logger.info(f"✅ 读取 {len(values)} 行数据")
            return values
        except Exception as e:
            logger.error(f"读取表格异常: {e}")
            return None

    async def upload_image(
        self,
        session: aiohttp.ClientSession,
        token: str,
        image_data: bytes,
        row: int,
        max_retries: int = 3,
    ) -> bool:
        """上传图片到指定行"""
        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.table_name}/values_image"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "range": f"{self.sheet_name}!{self.cell_range(row)}",
            "image": base64.b64encode(image_data).decode(),
            "name": "image.png",
        }

        for attempt in range(max_retries):
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    resp.raise_for_status()
                    body = await resp.json()
                if body.get("code") == 0:
                    return True
                logger.warning(f"上传 API 错误 ({attempt+1}/{max_retries}): {body.get('msg')}")
            except asyncio.TimeoutError:
                logger.warning(f"上传超时 ({attempt+1}/{max_retries}): 行 {row}")
            except Exception as e:
                logger.warning(f"上传异常 ({attempt+1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return False

    async def write_text(
        self,
        session: aiohttp.ClientSession,
        token: str,
        text: str,
        row: int,
    ) -> bool:
        """将文本写入指定行单元格（用于记录错误原因）"""
        url = (
            f"{self.base_url}/open-apis/sheets/v2/spreadsheets"
            f"/{self.table_name}/values"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "valueRange": {
                "range": f"{self.sheet_name}!{self.cell_range(row)}",
                "values": [[text]],
            }
        }
        try:
            async with session.put(
                url, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                body = await resp.json()
                return body.get("code") == 0
        except Exception as e:
            logger.warning(f"写入文本失败 行{row}: {e}")
            return False

async def fetch_image(
    task: Task,
    session: aiohttp.ClientSession,
    screenshot_sem: asyncio.Semaphore,
    download_sem: asyncio.Semaphore,
) -> Result:
    """
    根据 task.is_screenshot 决定截图还是下载。
    各自用独立 Semaphore 控制并发。
    """
    if task.is_screenshot:
        async with screenshot_sem:
            await asyncio.sleep(random.uniform(1.0, 3.0))
            try:
                if "toutiao.com" in task.url:
                    img = await take_toutiao_screenshot(task.url, include_comments=True)
                else:
                    img = await take_screenshot(task.url, COMMENT_SELECTOR)
                return Result(task=task, image_bytes=img)
            except PageNotFoundError as e:
                # 内容不存在，需要写入错误原因到表格，not_found=True 标记
                return Result(task=task, error=str(e), not_found=True)
            except PageBlockedError as e:
                return Result(task=task, error=f"页面被拦截: {e}")
            except Exception as e:
                return Result(task=task, error=f"截图失败: {e}")
    else:
        async with download_sem:
            await asyncio.sleep(random.uniform(0.2, 0.8))
            try:
                img = await _download_image(session, task.url)
                if img is None:
                    return Result(task=task, error="图片下载返回空")
                return Result(task=task, image_bytes=img)
            except Exception as e:
                return Result(task=task, error=f"下载失败: {e}")


async def _download_image(
    session: aiohttp.ClientSession,
    url: str,
    max_retries: int = 3,
) -> Optional[bytes]:
    """直接下载图片 URL"""
    headers = {
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        ),
        "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9",
        "referer": url.split("/api/")[0] if "/api/" in url else url,
    }

    for attempt in range(max_retries):
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=True
            ) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get("content-type", "")
                    if not content_type.split(";")[0].strip().startswith("image/"):
                        logger.warning(f"URL 不是图片 (content-type={content_type}): {url[:60]}")
                        return None
                    return await resp.read()
                if resp.status == 403 and attempt == 0:
                    # 防盗链，去掉 Referer 重试
                    h2 = {k: v for k, v in headers.items() if k != "referer"}
                    async with session.get(url, headers=h2, timeout=aiohttp.ClientTimeout(total=60)) as r2:
                        if r2.status == 200:
                            return await r2.read()
                logger.warning(f"下载失败 ({attempt+1}/{max_retries}): HTTP {resp.status}")
        except asyncio.TimeoutError:
            logger.warning(f"下载超时 ({attempt+1}/{max_retries}): {url[:60]}")
        except Exception as e:
            logger.warning(f"下载异常 ({attempt+1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)

    return None


# ---------------------------------------------------------------------------
# URL 解析
# ---------------------------------------------------------------------------

def parse_url(raw) -> Optional[str]:
    """从单元格原始值解析出有效 URL"""
    if not raw or "http" not in str(raw):
        return None
    raw = str(raw)
    if raw.startswith('["'):
        try:
            return json.loads(raw)[0]
        except Exception:
            return None
    return raw


# ---------------------------------------------------------------------------
# 主 Pipeline
# ---------------------------------------------------------------------------

class FeishuPipeline:
    """
    生产者-消费者流水线：

        [读表格] → fetch_queue → [截图/下载 Worker × N]
                                       ↓
                               upload_queue → [上传 Worker × M]
                                                     ↓
                                                  [统计]

    截图慢（浏览器启动），并发控制在 screenshot_concurrency。
    上传快（纯 HTTP），并发控制在 upload_concurrency。
    两者解耦：截图完一个立刻塞进上传队列，不等所有截图完成。
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        table_name: str,
        sheet_name: str,
        read_column: str = "F",
        write_column: str = "G",
        start_row: int = 1,
        end_row: int = 100,
        screenshot_concurrency: int = 2,
        download_concurrency: int = 5,   # 重命名：仅控制图片下载并发
    ):
        self.token_mgr = FeishuToken(app_id, app_secret)
        self.sheet = FeishuSheet(table_name, sheet_name, read_column, write_column)
        self.start_row = start_row
        self.end_row = end_row

        self.screenshot_sem = asyncio.Semaphore(screenshot_concurrency)
        self.download_sem = asyncio.Semaphore(download_concurrency)

        # 飞书写入接口有频率限制，强制串行（同一时刻只有一个写入请求）
        self.write_sem = asyncio.Semaphore(1)

        # queue_maxsize 用下载并发数作为缓冲参考
        self._queue_maxsize = download_concurrency * 2

        self.stats = Stats()

    async def run(self):
        t0 = time.monotonic()

        # 共享 Session（连接池复用）
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=10)
        async with aiohttp.ClientSession(connector=connector) as session:

            # 1. 获取 Token
            token = await self.token_mgr.get(session)

            # 2. 读表格
            rows = await self.sheet.read_values(session, token, self.start_row, self.end_row)
            if not rows:
                logger.error("读取表格失败，退出")
                return

            # 3. 解析任务
            tasks = self._build_tasks(rows)
            total = len(rows)
            logger.info(f"共 {total} 行，有效任务 {len(tasks)} 个，跳过 {self.stats.skipped} 行\n")

            if not tasks:
                return

            # 4. 启动流水线
            upload_queue: asyncio.Queue[Optional[Result]] = asyncio.Queue(maxsize=self._queue_maxsize)

            # 飞书写入串行：只启动 1 个 worker，从根本上避免并发写入
            upload_workers = [
                asyncio.create_task(
                    self._upload_worker(session, token, upload_queue),
                    name="upload-0",
                )
            ]

            # 生产者：并发 fetch，结果推入 upload_queue
            fetch_tasks = [
                fetch_image(task, session, self.screenshot_sem, self.download_sem)
                for task in tasks
            ]

            # 分批 gather，每批完成后推入队列（保持内存可控）
            for coro in asyncio.as_completed(fetch_tasks):
                result: Result = await coro
                await upload_queue.put(result)

            # 发送结束信号（每个 worker 一个 None）
            for _ in upload_workers:
                await upload_queue.put(None)

            # 等待所有上传完成
            await asyncio.gather(*upload_workers)

        duration = time.monotonic() - t0
        logger.info(self.stats.report(total, duration))

    def _build_tasks(self, rows: list) -> list[Task]:
        tasks = []
        for idx, row in enumerate(rows):
            row_index = idx + self.start_row
            raw = row[0] if row else None
            url = parse_url(raw)
            if url is None:
                self.stats.skipped += 1
                continue
            tasks.append(Task(
                row_index=row_index,
                cell_range=self.sheet.cell_range(row_index),
                url=url,
                is_screenshot=_needs_screenshot(url),
            ))
        return tasks

    async def _upload_worker(
        self,
        session: aiohttp.ClientSession,
        token: str,
        queue: asyncio.Queue,
    ):
        """消费 Result，上传到飞书"""
        while True:
            result: Optional[Result] = await queue.get()
            if result is None:           # 结束信号
                queue.task_done()
                break

            # 每次操作前确保 token 有效
            try:
                current_token = await self.token_mgr.get(session)
            except Exception as e:
                logger.error(f"Token 刷新失败: {e}")
                current_token = token

            async with self.write_sem:
                if result.not_found:
                    # 内容不存在：把原因写入对应单元格，不算失败
                    written = await self.sheet.write_text(
                        session, current_token,
                        text=f"内容不存在",
                        row=result.task.row_index,
                    )
                    self.stats.not_found += 1
                    if written:
                        logger.warning(f"🚫 行 {result.task.row_index} 内容不存在，已写入单元格")
                    else:
                        logger.warning(f"🚫 行 {result.task.row_index} 内容不存在，写入单元格失败")

                elif not result.ok:
                    # 其他错误（截图失败、下载失败等）：记录日志，不写表格
                    self.stats.failed += 1
                    self.stats.errors.append(f"行{result.task.row_index} {result.error}")
                    logger.error(f"❌ 行 {result.task.row_index} 获取图片失败: {result.error}")

                else:
                    # 正常：上传图片
                    success = await self.sheet.upload_image(
                        session, current_token, result.image_bytes, result.task.row_index
                    )
                    if success:
                        self.stats.success += 1
                        logger.info(f"✅ 行 {result.task.row_index} 上传成功")
                    else:
                        self.stats.failed += 1
                        self.stats.errors.append(f"行{result.task.row_index} 上传失败")
                        logger.error(f"❌ 行 {result.task.row_index} 上传失败")

            queue.task_done()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

APP_ID     = "cli_a9be44c67238dbc6"
APP_SECRET = "ZJtXV2OVBGPJ1pmQCBF9Me1CsgSeyMqh"
TABLE_NAME = "GfcUsbunHhotyJteMorcJZJbnye"
SHEET_NAME = "4c55b7"


async def main(start: int, end: int):
    pipeline = FeishuPipeline(
        app_id=APP_ID,
        app_secret=APP_SECRET,
        table_name=TABLE_NAME,
        sheet_name=SHEET_NAME,
        read_column="F",
        write_column="G",
        start_row=start,
        end_row=end,
        screenshot_concurrency=2,    # 截图：浏览器资源重，控制在 2
        download_concurrency=5,      # 下载：纯 HTTP，可以放开
        # 飞书写入固定串行，不可配置
    )
    await pipeline.run()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_line, end_line = int(sys.argv[1]), int(sys.argv[2])
    else:
        start_line, end_line = 55, 314

    logger.info(f"处理第 {start_line} 行 → 第 {end_line} 行")

    try:
        asyncio.run(main(start_line, end_line))
    except KeyboardInterrupt:
        logger.warning("用户中断")
    except Exception as e:
        logger.exception(f"程序异常退出: {e}")