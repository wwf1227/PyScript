#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tick_writer.py
进程一：接收掘金量化 Tick 回调，批量写入 SQLite 数据库
"""

import asyncio
import os
import signal
import threading
import logging
import time

import aiosqlite

from gm.api import *
from db_utils import DB_PATH, init_db, insert_ticks

# ================= 配置 =================

BATCH_SIZE     = 1    # 积累多少条触发写库
FLUSH_INTERVAL = 3     # 最长多少秒强制刷盘
QUEUE_MAXSIZE  = 5000  # 内存队列上限，防止 OOM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Writer] %(levelname)s %(message)s",
)

# ================= 全局状态 =================

_tick_queue: asyncio.Queue | None = None
_shutdown_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None


# ================= 异步写入消费者 =================

async def _db_writer():
    """
    从队列消费 tick，按 BATCH_SIZE 或 FLUSH_INTERVAL 批量写入数据库。
    不做 HTTP 上报，专注持久化。
    """
    global _tick_queue, _shutdown_event

    buffer: list[dict] = []
    last_flush = time.monotonic()

    async with aiosqlite.connect(DB_PATH) as db:
        await init_db(db)

        while True:
            # ---- 从队列取数据，最多等 1 秒 ----
            try:
                tick = await asyncio.wait_for(_tick_queue.get(), timeout=1.0)
                buffer.append(tick)
                _tick_queue.task_done()
            except asyncio.TimeoutError:
                pass  # 超时正常，继续检查刷盘条件

            # ---- 批量刷盘 ----
            now = time.monotonic()
            should_flush = len(buffer) >= BATCH_SIZE or (
                buffer and now - last_flush >= FLUSH_INTERVAL
            )
            if should_flush:
                await insert_ticks(db, buffer)
                buffer.clear()
                last_flush = now

            # ---- 退出条件：shutdown 已触发且队列已清空 ----
            if _shutdown_event.is_set() and _tick_queue.empty():
                break

        # ---- 优雅退出：处理最后剩余数据 ----
        remaining: list[dict] = []
        while not _tick_queue.empty():
            remaining.append(_tick_queue.get_nowait())
            _tick_queue.task_done()

        if buffer or remaining:
            await insert_ticks(db, buffer + remaining)

        logging.info("_db_writer 安全退出，刷盘剩余 %d 条", len(buffer) + len(remaining))


# ================= 后台事件循环线程 =================

async def _async_main():
    global _tick_queue, _shutdown_event

    _tick_queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
    _shutdown_event = asyncio.Event()

    try:
        await _db_writer()
    except Exception:
        logging.exception("_db_writer 意外崩溃")
    finally:
        logging.info("Writer 异步服务已关闭")


def _run_event_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_async_main())
    finally:
        _loop.close()


# ================= 安全退出 =================

def _trigger_shutdown():
    """线程安全地通知消费者退出"""
    if _loop and _shutdown_event:
        _loop.call_soon_threadsafe(_shutdown_event.set)


def _signal_handler(signum, frame):
    logging.info("收到退出信号 (%s)，开始优雅关闭...", signum)
    _trigger_shutdown()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)


# ================= 启动后台线程 =================

_bg_thread = threading.Thread(target=_run_event_loop, name="WriterLoop", daemon=False)
_bg_thread.start()

# 等待队列和事件就绪（最多 5 秒）
for _ in range(50):
    if _tick_queue is not None:
        break
    time.sleep(0.1)
else:
    raise RuntimeError("Writer 异步服务启动超时")

logging.info("Writer 后台线程已就绪")


# ================= 掘金策略回调 =================

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
    try:
        # call_soon_threadsafe + put_nowait 是跨线程投递的正确姿势
        _loop.call_soon_threadsafe(_tick_queue.put_nowait, tick_data)
    except asyncio.QueueFull:
        logging.warning("队列已满，丢弃 tick: %s", tick_data["symbol"])


# ================= 主线程：运行掘金策略 =================

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
    logging.info("等待后台写入线程退出（最多 15 秒）...")
    _trigger_shutdown()
    _bg_thread.join(timeout=15)
    if _bg_thread.is_alive():
        logging.warning("后台线程超时未退出，强制结束")
    logging.info("Writer 进程已安全退出")