#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tick_writer.py  ——  VPN 进程
职责：
  1. 接收掘金量化 gm.api 的 tick 回调
  2. 通过 UDP 实时推送给 tick_reporter（同机器，普通网络进程）
  3. 异步写入本地 SQLite 做归档备份，每天定时清理 1 个月前的数据
"""

import asyncio
import json
import logging
import signal
import socket
import threading
import time
from datetime import datetime

import aiosqlite

from gm.api import *
from db_utils import DB_PATH, init_db, insert_tick, purge_old_ticks

# ─────────────────────── 配置 ───────────────────────
REPORTER_HOST  = "127.0.0.1"
REPORTER_PORT  = 19999
QUEUE_MAXSIZE  = 5000       # 归档队列上限，超出则丢弃（不影响 UDP 实时推送）
PURGE_INTERVAL = 86400      # 归档清理周期：每 24 小时执行一次（秒）
COMMIT_BATCH   = 10         # 每积攒多少条 tick 后批量 commit 一次

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Writer] %(levelname)s %(message)s",
)

# ─────────────────────── 全局状态 ───────────────────────
_queue: asyncio.Queue | None = None
_shutdown: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None
_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# ─────────────────────── 归档任务 ───────────────────────

async def _archive_worker():
    """消费队列，将 tick 写入 SQLite 归档；每 COMMIT_BATCH 条或队列空闲时批量 commit"""
    pending = 0
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await init_db(db)
        while True:
            try:
                tick = await asyncio.wait_for(_queue.get(), timeout=1.0)
                _queue.task_done()
                await insert_tick(db, tick)
                pending += 1
                if pending >= COMMIT_BATCH:
                    await db.commit()
                    pending = 0
            except asyncio.TimeoutError:
                if pending > 0:
                    await db.commit()
                    pending = 0

            if _shutdown.is_set() and _queue.empty():
                if pending > 0:
                    await db.commit()
                break

    logging.info("[Writer] 归档任务已安全退出")


async def _purge_worker():
    """每 PURGE_INTERVAL 秒清理一次超过 30 天的归档数据"""
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        while True:
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=PURGE_INTERVAL)
                break   # shutdown 触发，退出
            except asyncio.TimeoutError:
                await purge_old_ticks(db, keep_days=30)

    logging.info("[Writer] 清理任务已安全退出")


async def _async_main():
    global _queue, _shutdown
    _queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
    _shutdown = asyncio.Event()

    await asyncio.gather(
        _archive_worker(),
        _purge_worker(),
    )


def _run_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_async_main())
    finally:
        _loop.close()


# ─────────────────────── gm.api 回调 ───────────────────────

def init(context):
    subscribe(symbols="SHSE.000001", frequency="tick", wait_group=True)
    logging.info("[Writer] 策略初始化完成，已订阅 SHSE.000001 Tick")


def on_tick(context, tick):
    tick_data = {
        "symbol":       tick.symbol,
        "open":         float(tick.open),
        "high":         float(tick.high),
        "low":          float(tick.low),
        "price":        float(tick.price),
        "cum_volume":   int(tick.cum_volume),
        "cum_amount":   float(tick.cum_amount),
        "trade_type":   int(tick.trade_type),
        "last_volume":  int(tick.last_volume),
        "cum_position": int(tick.cum_position),
        "last_amount":  float(tick.last_amount),
        "created_at":   str(tick.created_at),
        "local_time":   datetime.now().astimezone().isoformat(),
    }
    logging.info("[on_tick] 回调 tick: %s local=%s price=%s",
                     tick_data["created_at"], tick_data.get("local_time", ""), tick_data["price"])
    # 1. UDP 实时推送给 Reporter（同步发送，微秒级，不阻塞回调）
    # try:
    #     _udp_sock.sendto(
    #         json.dumps(tick_data).encode("utf-8"),
    #         (REPORTER_HOST, REPORTER_PORT),
    #     )
    #     logging.info(
    #         "[Writer] UDP 已推送: %s price=%s",
    #         tick_data["created_at"], tick_data["price"],
    #     )
    # except Exception as e:
    #     logging.warning("[Writer] UDP 发送失败: %s", e)

    # 2. 异步写 DB 归档（队列满时丢弃，不影响实时推送）
    try:
        _loop.call_soon_threadsafe(_queue.put_nowait, tick_data)
    except asyncio.QueueFull:
        logging.warning("[Writer] 归档队列已满，丢弃本条备份")


# ─────────────────────── 启动 / 退出 ───────────────────────

def _trigger_shutdown():
    if _loop and not _loop.is_closed() and _shutdown:
        _loop.call_soon_threadsafe(_shutdown.set)


def _signal_handler(signum, frame):
    logging.info("[Writer] 收到退出信号，开始优雅关闭...")
    _trigger_shutdown()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)

# 启动后台异步线程
_bg_thread = threading.Thread(target=_run_loop, name="WriterLoop", daemon=False)
_bg_thread.start()

# 等待 asyncio 队列就绪（最多 5 秒）
for _ in range(50):
    if _queue is not None:
        break
    time.sleep(0.1)
else:
    raise RuntimeError("[Writer] 异步服务启动超时")

logging.info("[Writer] 后台线程已就绪")

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
    logging.info("[Writer] run() 收到 KeyboardInterrupt")
finally:
    _trigger_shutdown()
    _bg_thread.join(timeout=15)
    _udp_sock.close()
    logging.info("[Writer] 进程已安全退出")
