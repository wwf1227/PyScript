#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tick_reporter.py
进程二：轮询数据库，将待上报 tick 批量 POST 到服务端
可独立启动，与 tick_writer.py 并行运行，共享同一个 SQLite 文件
"""

import asyncio
import signal
import logging
import time

import aiohttp
import aiosqlite

from db_utils import (
    DB_PATH,
    init_db,
    fetch_pending_ticks,
    mark_ticks_done,
    mark_ticks_failed,
    purge_done_ticks,
)

# ================= 配置 =================

REPORT_URL       = "https://appalpha1.tingyun.com/appdatasvr/finbench/v1/data/standard"
BATCH_SIZE       = 50    # 每次从 DB 取多少条上报
POLL_INTERVAL    = 2.0   # 队列空时等待多少秒再轮询
HTTP_CONCURRENCY = 10    # 最大并发 HTTP 请求数
MAX_RETRY        = 3     # 单条 tick 最大重试次数
PURGE_INTERVAL   = 3600  # 每隔多少秒清理一次已完成数据（秒）
PURGE_KEEP_HOURS = 24    # 已完成数据保留多少小时

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Reporter] %(levelname)s %(message)s",
)

# ================= 关闭事件 =================

_shutdown_event: asyncio.Event | None = None


# ================= HTTP 上报 =================

def _build_payload(tick: dict) -> dict:
    """将数据库行转换为服务端所需字段"""
    return {
        "stock_id":   tick["symbol"].split(".")[1],
        "price":      tick["price"],
        "high":       tick["high"],
        "low":        tick["low"],
        "cum_volume": tick["cum_volume"],
        "timestamp":  tick["created_ts"],
        "source":     "掘金量化",
    }


async def _post_batch(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    ticks: list[dict],
) -> tuple[list[int], list[int]]:
    """
    并发上报一批 tick。
    返回 (成功 id 列表, 失败 id 列表)
    每条 tick 单独发送，互不影响；也可改成一次 POST 整批。
    """
    success_ids: list[int] = []
    failed_ids: list[int]  = []

    async def _post_one(tick: dict):
        payload = _build_payload(tick)
        async with semaphore:
            try:
                async with session.post(
                    REPORT_URL,
                    json=[payload],
                    proxy=None,
                    timeout=aiohttp.ClientTimeout(total=30, connect=10, sock_read=15),
                ) as resp:
                    resp.raise_for_status()
                    logging.debug("上报成功 tick_id=%s symbol=%s", tick["id"], tick["symbol"])
                    success_ids.append(tick["id"])
            except aiohttp.ClientResponseError as e:
                logging.error(
                    "HTTP 错误 tick_id=%s status=%s msg=%s",
                    tick["id"], e.status, e.message,
                )
                failed_ids.append(tick["id"])
            except Exception:
                logging.exception("上报异常 tick_id=%s", tick["id"])
                failed_ids.append(tick["id"])

    await asyncio.gather(*[_post_one(t) for t in ticks])
    return success_ids, failed_ids


# ================= 核心轮询循环 =================

async def reporter_loop():
    global _shutdown_event

    semaphore = asyncio.Semaphore(HTTP_CONCURRENCY)
    last_purge = time.monotonic()

    async with (
        aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            trust_env=False,
        ) as session,
        aiosqlite.connect(DB_PATH, timeout=30) as db,
    ):
        await init_db(db)

        while True:
            # ---- 拉取待上报数据 ----
            ticks = await fetch_pending_ticks(db, batch_size=BATCH_SIZE, max_retry=MAX_RETRY)

            if ticks:
                logging.info("取到 %d 条待上报 tick，开始上报...", len(ticks))
                success_ids, failed_ids = await _post_batch(session, semaphore, ticks)

                if success_ids:
                    await mark_ticks_done(db, success_ids)
                    logging.info("上报成功 %d 条", len(success_ids))

                if failed_ids:
                    await mark_ticks_failed(db, failed_ids)
                    logging.warning("上报失败 %d 条（已标记重试）", len(failed_ids))
            else:
                # 无数据时等待，避免空转消耗 CPU
                if _shutdown_event.is_set():
                    logging.info("shutdown 触发且无待处理数据，Reporter 退出")
                    break
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=POLL_INTERVAL)
                except asyncio.TimeoutError:
                    pass  # 正常超时，继续轮询

            # ---- 定期清理已完成数据 ----
            now = time.monotonic()
            if now - last_purge >= PURGE_INTERVAL:
                await purge_done_ticks(db, keep_hours=PURGE_KEEP_HOURS)
                last_purge = now

    logging.info("Reporter 异步循环已结束")


# ================= 信号处理 =================

def _signal_handler(signum, frame):
    logging.info("收到退出信号 (%s)，开始优雅关闭...", signum)
    if _shutdown_event:
        _shutdown_event.set()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)


# ================= 入口 =================

async def main():
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    logging.info("Reporter 启动，轮询数据库: %s", DB_PATH)
    try:
        await reporter_loop()
    except Exception:
        logging.exception("reporter_loop 意外崩溃")
    finally:
        logging.info("Reporter 进程已安全退出")


if __name__ == "__main__":
    asyncio.run(main())