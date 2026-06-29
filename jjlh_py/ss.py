#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tick_reporter.py  ——  普通网络进程
职责：
  1. 监听 UDP 端口，接收 tick_writer 实时推送的 tick
  2. 通过 aiohttp（连接池复用）上报到外部平台
"""

import asyncio
import datetime
import json
import logging
import signal

import aiohttp

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

REPORT_URL  = "https://appalpha1.tingyun.com/appdatasvr/finbench/v1/data/standard"
REPORT_URL_BAK  = "https://wkadt1.tingyun.com/appdatasvr/finbench/v1/data/standard"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 19999

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Reporter] %(levelname)s %(message)s",
)

_shutdown: asyncio.Event | None = None


# ─────────────────────── 数据转换 ───────────────────────

def _build_payload(tick: dict) -> dict:
    dt = datetime.datetime.fromisoformat(tick["created_at"])
    return {
        "stock_id":   tick["symbol"].split(".")[1],
        "price":      tick["price"],
        "high":       tick["high"],
        "low":        tick["low"],
        "cum_volume": tick["cum_volume"],
        "timestamp":  int(dt.timestamp() * 1000),
        "source":     "掘金量化",
    }


# ─────────────────────── UDP 协议 ───────────────────────

class _UDPProtocol(asyncio.DatagramProtocol):
    """asyncio 原生 UDP 协议，收到数据后放入队列"""

    def __init__(self, queue: asyncio.Queue):
        self._queue = queue

    def datagram_received(self, data: bytes, addr):
        try:
            tick = json.loads(data.decode("utf-8"))
            self._queue.put_nowait(tick)
        except Exception as e:
            logging.warning("[Reporter] 解析 UDP 数据失败: %s", e)

    def error_received(self, exc):
        logging.error("[Reporter] UDP 错误: %s", exc)


def is_retryable(exc: BaseException) -> bool:
    """4xx 不重试，5xx 和网络异常重试"""
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status >= 500
    return True 

@retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=5),
    reraise=True,
)
async def send_report(url,session, payload):
    """发送单个上报请求（包含重试逻辑）"""
    async with session.post(
        url,
        json=[payload],
        timeout=aiohttp.ClientTimeout(total=10)
    ) as resp:       
        # 正常情况或不可重试的错误，正常抛出异常
        resp.raise_for_status()
        logging.info("[Reporter] 上报成功 状态码=%s", resp.status)
        return resp

# ─────────────────────── 上报任务 ───────────────────────

async def _report_worker(queue: asyncio.Queue, session: aiohttp.ClientSession):
    """从队列取 tick，上报到外部平台"""
    while True:
        try:
            tick = await asyncio.wait_for(queue.get(), timeout=1.0)
            queue.task_done()
        except asyncio.TimeoutError:
            if _shutdown.is_set():
                break
            continue

        payload = _build_payload(tick)
        logging.info("[Reporter] 上报 payload: %s", payload)
        try:
            await send_report(REPORT_URL,session, payload)
        except aiohttp.ClientResponseError as e:
            body = await e.response.text() if e.response else ""
            logging.error("[Reporter] 上报失败 HTTP=%s body=%s", e.status, body)
        except Exception as e:
            logging.error("[Reporter] 上报异常: %s", e)
            
        try:
            await send_report(REPORT_URL_BAK,session, payload)
        except aiohttp.ClientResponseError as e:
            body = await e.response.text() if e.response else ""
            logging.error("[Reporter] 上报失败 HTTP=%s body=%s", e.status, body)
        except Exception as e:
            logging.error("[Reporter] 上报异常: %s", e)

    logging.info("[Reporter] 上报任务已退出")


# ─────────────────────── 主循环 ───────────────────────

async def main():
    global _shutdown
    _shutdown = asyncio.Event()

    queue: asyncio.Queue = asyncio.Queue()

    # 创建 UDP 监听（asyncio 原生，不阻塞事件循环）
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _UDPProtocol(queue),
        local_addr=(LISTEN_HOST, LISTEN_PORT),
    )
    logging.info("[Reporter] 监听 UDP %s:%d，等待 Writer 推送...", LISTEN_HOST, LISTEN_PORT)

    # 创建 aiohttp Session（连接池复用，整个进程生命周期共享）
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        await _report_worker(queue, session)

    transport.close()
    logging.info("[Reporter] 进程已安全退出")


# ─────────────────────── 信号处理 ───────────────────────

def _signal_handler(signum, frame):
    logging.info("[Reporter] 收到退出信号，关闭中...")
    if _shutdown:
        asyncio.get_event_loop().call_soon_threadsafe(_shutdown.set)


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)


if __name__ == "__main__":
    asyncio.run(main())
