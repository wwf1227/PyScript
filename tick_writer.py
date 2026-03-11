#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import signal
import socket
import threading
import logging
import time
import json

import aiosqlite
import asyncio

from gm.api import *
from db_utils import DB_PATH, init_db, insert_ticks

QUEUE_MAXSIZE  = 5000
REPORTER_PORT  = 19999

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Writer] %(levelname)s %(message)s",
)

_tick_queue: asyncio.Queue | None = None
_shutdown_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None
_sock: socket.socket | None = None


async def _db_writer():
    global _tick_queue, _shutdown_event

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await init_db(db)

        while True:
            try:
                tick = await asyncio.wait_for(_tick_queue.get(), timeout=1.0)
                _tick_queue.task_done()
                await insert_ticks(db, [tick])
            except asyncio.TimeoutError:
                pass

            if _shutdown_event.is_set() and _tick_queue.empty():
                break

    logging.info("_db_writer 安全退出")


async def _async_main():
    global _tick_queue, _shutdown_event
    _tick_queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
    _shutdown_event = asyncio.Event()
    try:
        await _db_writer()
    except Exception:
        logging.exception("_db_writer 意外崩溃")


def _run_event_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_async_main())
    finally:
        _loop.close()


def _trigger_shutdown():
    if _loop and _shutdown_event:
        _loop.call_soon_threadsafe(_shutdown_event.set)


def _signal_handler(signum, frame):
    logging.info("收到退出信号，开始优雅关闭...")
    _trigger_shutdown()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)

_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

_bg_thread = threading.Thread(target=_run_event_loop, name="WriterLoop", daemon=False)
_bg_thread.start()

for _ in range(50):
    if _tick_queue is not None:
        break
    time.sleep(0.1)
else:
    raise RuntimeError("Writer 异步服务启动超时")

logging.info("Writer 后台线程已就绪")


def init(context):
    subscribe(symbols="SHSE.000001", frequency="tick", wait_group=True)
    logging.info("策略初始化完成，已订阅 SHSE.000001 Tick")


def on_tick(context, tick):
    tick_data = {
        "symbol":       tick.symbol,
        "open":         float(tick.open),
        "high":         float(tick.high),
        "low":          float(tick.low),
        "price":        float(tick.price),
        "cum_volume":   int(tick.cum_volume),
        "cum_amount":   float(tick.cum_amount),
        "trade_type":   int(tick["trade_type"]),
        "last_volume":  int(tick["last_volume"]),
        "cum_position": int(tick["cum_position"]),
        "last_amount":  float(tick["last_amount"]),
        "created_at":   str(tick["created_at"]),
    }

    # ✅ 直接发给 Reporter，不经过数据库
    try:
        data = json.dumps(tick_data).encode("utf-8")
        _sock.sendto(data, ("127.0.0.1", REPORTER_PORT))
        logging.info("已发送 tick 到 Reporter: %s price=%s", tick_data["created_at"], tick_data["price"])
    except Exception as e:
        logging.warning("发送失败: %s", e)

    # 数据库只做备份
    try:
        _loop.call_soon_threadsafe(_tick_queue.put_nowait, tick_data)
    except asyncio.QueueFull:
        logging.warning("队列已满，丢弃备份")


try:
    run(
        strategy_id="d8b27796-d0db-11f0-9754-00e04cac3d6d",
        filename="tick_writer.py",
        mode=MODE_LIVE,
        token="517eec8206acf119ccfb2aa7437f41acd9bc1c01",
        backtest_start_time="2026-03-02 13:00:47",
        backtest_end_time="2026-03-02 14:11:00",
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=10000000,
        backtest_commission_ratio=0.0001,
        backtest_slippage_ratio=0.0001,
        backtest_match_mode=1,
    )
except KeyboardInterrupt:
    logging.info("run() 收到 KeyboardInterrupt")
finally:
    _trigger_shutdown()
    _bg_thread.join(timeout=15)
    _sock.close()
    logging.info("Writer 进程已安全退出")