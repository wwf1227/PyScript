#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import datetime
import signal
import socket
import logging
import json
import requests

REPORT_URL = "https://appalpha1.tingyun.com/appdatasvr/finbench/v1/data/standard"
LISTEN_PORT = 19999

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Reporter] %(levelname)s %(message)s",
)

_shutdown_event: asyncio.Event | None = None


def _build_payload(tick: dict) -> dict:
    dt = datetime.datetime.fromisoformat(tick["created_at"])
    timestamp_ms = int(dt.timestamp() * 1000)
    return {
        "stock_id": tick["symbol"].split(".")[1],
        "price": tick["price"],
        "high": tick["high"],
        "low": tick["low"],
        "cum_volume": tick["cum_volume"],
        "timestamp": timestamp_ms,
        "source": "掘金量化",
    }


def _post(tick: dict):
    payload = _build_payload(tick)
    logging.info("发送payload: %s", payload)  # ← 加这行
    try:
        resp = requests.post(REPORT_URL, json=[payload], timeout=10)
        resp.raise_for_status()
        logging.info("上报成功 状态码=%s", resp.status_code)
    except requests.HTTPError as e:
        logging.error("上报失败 HTTP错误=%s  返回body=%s", e, e.response.text)


async def reporter_loop():
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", LISTEN_PORT))
    sock.setblocking(False)

    logging.info("监听 UDP 端口 %d，等待 Writer 推送...", LISTEN_PORT)

    while True:
        if _shutdown_event.is_set():
            break
        try:
            # 等待 Writer 推过来的数据
            data = await asyncio.wait_for(
                loop.sock_recv(sock, 65535),
                timeout=5.0,
            )
            tick = json.loads(data.decode("utf-8"))
            # 在线程池里发 HTTP，不阻塞事件循环
            await loop.run_in_executor(None, _post, tick)
        except asyncio.TimeoutError:
            pass  # 5秒没数据，继续等
        except Exception:
            logging.exception("处理数据异常")

    sock.close()
    logging.info("Reporter 已退出")


def _signal_handler(signum, frame):
    logging.info("收到退出信号，关闭中...")
    if _shutdown_event:
        _shutdown_event.set()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)


async def main():
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    try:
        await reporter_loop()
    except Exception:
        logging.exception("reporter_loop 崩溃")


if __name__ == "__main__":
    asyncio.run(main())
