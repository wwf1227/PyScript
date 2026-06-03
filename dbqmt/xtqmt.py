#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xtqmt.py  ——  xtquant 行情进程
职责：
  1. 接收 xtquant 的 tick 回调
  2. 通过 UDP 实时推送给 tick_reporter（同机器，普通网络进程）
  3. 异步写入本地 SQLite 做归档备份，每天定时清理 1 个月前的数据
"""

import asyncio
import datetime
import json
import logging
import signal
import socket
import threading
import time

import aiosqlite

from xtquant import xtdata
from db_utils import DB_PATH, init_db, insert_tick, purge_old_ticks

# ─────────────────────── 配置 ───────────────────────
REPORTER_HOST  = "127.0.0.1"
REPORTER_PORT  = 19999
QUEUE_MAXSIZE  = 5000       # 归档队列上限，超出则丢弃（不影响 UDP 实时推送）
PURGE_INTERVAL = 86400      # 归档清理周期：每 24 小时执行一次（秒）

STOCK_CODE = "000001.SH"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [XtWriter] %(levelname)s %(message)s",
)

# ─────────────────────── 全局状态 ───────────────────────
_queue: asyncio.Queue | None = None
_shutdown: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None
_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# ─────────────────────── 归档任务 ───────────────────────

async def _archive_worker():
    """消费队列，将 tick 写入 SQLite 归档"""
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await init_db(db)
        while True:
            try:
                tick = await asyncio.wait_for(_queue.get(), timeout=1.0)
                _queue.task_done()
                await insert_tick(db, tick)
            except asyncio.TimeoutError:
                pass

            if _shutdown.is_set() and _queue.empty():
                break

    logging.info("[XtWriter] 归档任务已安全退出")


async def _purge_worker():
    """每 PURGE_INTERVAL 秒清理一次超过 30 天的归档数据"""
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        while True:
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=PURGE_INTERVAL)
                break   # shutdown 触发，退出
            except asyncio.TimeoutError:
                await purge_old_ticks(db, keep_days=30)

    logging.info("[XtWriter] 清理任务已安全退出")


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


# ─────────────────────── xtquant tick 回调 ───────────────────────

def tick_callback(datas):
    """
    xtquant tick 回调，行情更新时自动触发。
    datas 支持两种格式：
      - dict:  {code: [tick, ...]}
      - list:  [tick, ...]  （订阅单标的时常见）
    每条 tick 统一映射为与 tick_writer 相同的字段结构后推送。
    """
    if isinstance(datas, dict):
        items = [
            (code, tick)
            for code, ticks in datas.items()
            for tick in (ticks if isinstance(ticks, list) else [ticks])
        ]
    else:
        raw = datas if isinstance(datas, list) else [datas]
        items = [(STOCK_CODE, tick) for tick in raw]

    for symbol, raw_tick in items:        
        tick_data = {
            "symbol":       symbol,
            "open":         float(raw_tick.get("open",      0)),
            "high":         float(raw_tick.get("high",      0)),
            "low":          float(raw_tick.get("low",       0)),
            "price":        float(raw_tick.get("lastPrice", 0)),
            "cum_volume":   int(raw_tick.get("volume",      0)),
            "cum_amount":   float(raw_tick.get("amount",    0)),
            "trade_type":   0,                                   # xtquant 无对应字段
            "last_volume":  0,                                   # xtquant 无对应字段
            "cum_position": int(raw_tick.get("openInt",     0)),
            "last_amount":  0.0,                                 # xtquant 无对应字段
            "created_at":   raw_tick.get("time", 0),
        }

        print(tick_data)

        # 1. UDP 实时推送给 Reporter（同步发送，微秒级，不阻塞回调）
        # try:
        #     _udp_sock.sendto(
        #         json.dumps(tick_data).encode("utf-8"),
        #         (REPORTER_HOST, REPORTER_PORT),
        #     )
        #     logging.info(
        #         "[XtWriter] UDP 已推送: ts=%s price=%s",
        #         tick_data["created_at"], tick_data["price"],
        #     )
        # except Exception as e:
        #     logging.warning("[XtWriter] UDP 发送失败: %s", e)

        # # 2. 异步写 DB 归档（队列满时丢弃，不影响实时推送）
        # try:
        #     _loop.call_soon_threadsafe(_queue.put_nowait, tick_data)
        # except asyncio.QueueFull:
        #     logging.warning("[XtWriter] 归档队列已满，丢弃本条备份")


# ─────────────────────── 启动 / 退出 ───────────────────────

def _trigger_shutdown():
    if _loop and not _loop.is_closed() and _shutdown:
        _loop.call_soon_threadsafe(_shutdown.set)


def _signal_handler(signum, frame):
    logging.info("[XtWriter] 收到退出信号，开始优雅关闭...")
    _trigger_shutdown()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)

# 启动后台异步线程
_bg_thread = threading.Thread(target=_run_loop, name="XtWriterLoop", daemon=False)
_bg_thread.start()

# 等待 asyncio 队列就绪（最多 5 秒）
for _ in range(50):
    if _queue is not None:
        break
    time.sleep(0.1)
else:
    raise RuntimeError("[XtWriter] 异步服务启动超时")

logging.info("[XtWriter] 后台线程已就绪")

# ─────────────────────── 订阅行情 ───────────────────────
try:
    logging.info("[XtWriter] 开始订阅 %s Tick...", STOCK_CODE)
    xtdata.subscribe_quote(
        stock_code=STOCK_CODE,
        period="tick",
        callback=tick_callback,
        count=-1,
    )
    logging.info("[XtWriter] 订阅成功，等待行情推送...")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logging.info("[XtWriter] 收到 KeyboardInterrupt")
finally:
    xtdata.unsubscribe_quote(STOCK_CODE, period="tick")
    logging.info("[XtWriter] 已取消 xtquant 订阅")
    _trigger_shutdown()
    _bg_thread.join(timeout=15)
    _udp_sock.close()
    logging.info("[XtWriter] 进程已安全退出")
