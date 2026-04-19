#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Time : 2026/04/18
@Author : wwf
Description: 优化版飞书表格图片处理工具
"""
import asyncio
import base64
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from screenshot_tool import take_screenshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class FeishuSheetOperator:
    def __init__(self, start: int, end: int):
        """
        初始化飞书表格操作器

        Args:
            start: 起始行号
            end:   结束行号
        """
        self.APP_ID = "cli_a9be44c67238dbc6"
        self.APP_SECRET = "ZJtXV2OVBGPJ1pmQCBF9Me1CsgSeyMqh"
        self.TOKEN_CACHE_FILE = "data/feishu_token_cache.json"
        self.headers: dict = {}
        self.base_url = "https://open.feishu.cn"

        self.read_column = "F"
        self.write_column = "G"
        self.start_row = start
        self.end_row = end
        self.table_name = "GfcUsbunHhotyJteMorcJZJbnye"
        self.sheet_name = "4c55b7"

        # 统计（asyncio.Lock 保护并发写入）
        self.success_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self._lock = asyncio.Lock()

        self.session = self._create_session()

    # ------------------------------------------------------------------
    # Session / Token
    # ------------------------------------------------------------------

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def init_token(self) -> None:
        """
        显式初始化 Token（从构造函数中分离，便于错误处理）。
        调用方应在构造后立即调用。
        """
        self.get_tenant_access_token()

    def get_tenant_access_token(self) -> str:
        """获取飞书租户访问令牌（支持文件缓存）"""
        cache_path = Path(self.TOKEN_CACHE_FILE)
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text())
                if datetime.now().timestamp() < cache.get("expire_time", 0) - 600:
                    self.headers = {
                        "Authorization": f"Bearer {cache['token']}",
                        "Content-Type": "application/json; charset=utf-8",
                    }
                    logger.info("✅ 使用缓存的访问令牌")
                    return cache["token"]
            except Exception as e:
                logger.warning(f"读取 token 缓存失败: {e}")
        else:
            cache_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("🔑 正在获取新的访问令牌...")
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        resp = self.session.post(
            url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"app_id": self.APP_ID, "app_secret": self.APP_SECRET},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(f"获取 token 失败: {result}")

        token = result["tenant_access_token"]
        expire_time = datetime.now().timestamp() + result["expire"]
        cache_path.write_text(json.dumps({"token": token, "expire_time": expire_time}))

        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        logger.info("✅ 访问令牌获取成功")
        return token

    # ------------------------------------------------------------------
    # 表格操作
    # ------------------------------------------------------------------

    def sheet_value(self) -> Optional[List]:
        """读取飞书表格指定列数据"""
        logger.info(f"📊 正在获取表格数据 (行 {self.start_row}-{self.end_row})...")
        url = (
            f"{self.base_url}/open-apis/sheets/v2/spreadsheets"
            f"/{self.table_name}/values"
            f"/{self.sheet_name}!{self.read_column}{self.start_row}"
            f":{self.read_column}{self.end_row}"
        )
        try:
            resp = self.session.get(
                url,
                params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"},
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                logger.error(f"API 返回错误: {body}")
                return None
            values = body["data"]["valueRange"]["values"]
            logger.info(f"✅ 成功获取 {len(values)} 行数据")
            return values
        except Exception as e:
            logger.error(f"获取表格数据失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 图片下载
    # ------------------------------------------------------------------

    def _is_image_response(self, resp: requests.Response) -> bool:
        return resp.headers.get("content-type", "").split(";")[0].strip().startswith("image/")

    def download_image(self, image_url: str, max_retries: int = 3) -> Optional[bytes]:
        headers = {
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": image_url.split("/api/")[0] if "/api/" in image_url else image_url,
        }

        for attempt in range(max_retries):
            try:
                resp = self.session.get(image_url, headers=headers, timeout=(10, 60), allow_redirects=True)
                if resp.status_code == 200:
                    if not self._is_image_response(resp):
                        logger.warning(f"URL 不是图片: {image_url}")
                        return None
                    return resp.content
                if resp.status_code == 403 and attempt == 0:
                    # 防盗链，去掉 Referer 重试一次
                    h2 = {k: v for k, v in headers.items() if k != "referer"}
                    resp2 = self.session.get(image_url, headers=h2, timeout=(10, 60))
                    if resp2.status_code == 200 and self._is_image_response(resp2):
                        return resp2.content
                logger.warning(f"下载失败 ({attempt+1}/{max_retries}): {resp.status_code}")
            except requests.Timeout:
                logger.warning(f"下载超时 ({attempt+1}/{max_retries})")
            except Exception as e:
                logger.warning(f"下载异常 ({attempt+1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return None

    # ------------------------------------------------------------------
    # 图片上传
    # ------------------------------------------------------------------

    def upload_image(self, image_data: bytes, cell_range: str, max_retries: int = 3) -> bool:
        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.table_name}/values_image"
        data = {
            "range": f"{self.sheet_name}!{cell_range}",
            "image": base64.b64encode(image_data).decode(),
            "name": "image.png",
        }

        for attempt in range(max_retries):
            try:
                resp = self.session.post(url, headers=self.headers, json=data, timeout=(10, 90))
                if resp.status_code == 200 and resp.json().get("code") == 0:
                    return True
                logger.warning(f"上传失败 ({attempt+1}/{max_retries}): {resp.text[:80]}")
            except requests.Timeout:
                logger.warning(f"上传超时 ({attempt+1}/{max_retries}): {cell_range}")
            except Exception as e:
                logger.warning(f"上传异常 ({attempt+1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        return False

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def parse_url(raw: str) -> Optional[str]:
        """从单元格原始值中解析出 URL"""
        if not raw or "http" not in raw:
            return None
        if raw.startswith('["'):
            try:
                return json.loads(raw)[0]
            except Exception:
                return None
        return raw

    def close(self):
        self.session.close()


# --------------------------------------------------------------------------
# 异步批处理主流程
# --------------------------------------------------------------------------

COMMENT_SELECTOR = "#comment-area > div.main-input"


async def process_batch(operator: FeishuSheetOperator, max_concurrent: int = 1):
    """
    并发截图并上传至飞书表格。

    修复点：
    1. upload_image 是同步阻塞 IO，改用 loop.run_in_executor 避免阻塞事件循环。
    2. 计数器通过 asyncio.Lock 保护，避免并发写入竞争。
    """
    sem = asyncio.Semaphore(max_concurrent)
    loop = asyncio.get_running_loop()

    async def process_one(url: str, cell_range: str, row_idx: int):
        async with sem:
            await asyncio.sleep(random.uniform(1, 3))
            try:
                img_bytes = await take_screenshot(url, COMMENT_SELECTOR)
                # ✅ 在线程池中执行同步阻塞上传，不阻塞事件循环
                success = await loop.run_in_executor(
                    None, lambda: operator.upload_image(image_data=img_bytes, cell_range=cell_range)
                )
                async with operator._lock:
                    if success:
                        operator.success_count += 1
                        logger.info(f"✅ 行 {row_idx} 上传成功")
                    else:
                        operator.fail_count += 1
                        logger.error(f"❌ 行 {row_idx} 上传失败")
            except Exception as e:
                async with operator._lock:
                    operator.fail_count += 1
                logger.error(f"❌ 行 {row_idx} 出现错误: {e}")

    res = operator.sheet_value()
    if res is None:
        logger.error("无法获取表格数据，程序退出")
        return

    logger.info(f"\n开始处理 {len(res)} 行数据...\n")
    start_time = time.time()

    tasks = []
    for idx, r in enumerate(res):
        row_index = idx + operator.start_row
        url = operator.parse_url(r[0] if r else "")
        if url is None:
            operator.skip_count += 1
            continue
        cell_range = f"{operator.write_column}{row_index}:{operator.write_column}{row_index}"
        tasks.append(process_one(url=url, cell_range=cell_range, row_idx=row_index))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"任务 [{i}] 异常: {result}")

    duration = time.time() - start_time
    logger.info(
        f"\n{'='*60}\n"
        f"✨ 处理完成！总计 {len(res)} 行 | "
        f"✅ 成功 {operator.success_count} | "
        f"❌ 失败 {operator.fail_count} | "
        f"⏭️  跳过 {operator.skip_count} | "
        f"⏱️  {duration:.1f}s\n"
        f"{'='*60}"
    )


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_line, end_line = int(sys.argv[1]), int(sys.argv[2])
    else:
        start_line, end_line = 55, 314

    logger.info(f"处理第 {start_line} 行 → 第 {end_line} 行")

    operator = None
    try:
        operator = FeishuSheetOperator(start_line, end_line)
        operator.init_token()   # ✅ token 初始化与构造分离，便于捕获异常
        asyncio.run(process_batch(operator))
    except KeyboardInterrupt:
        logger.warning("程序被用户中断")
    except Exception as e:
        logger.exception(f"程序异常退出: {e}")
    finally:
        if operator:
            operator.close()

    logger.info("结束！")
