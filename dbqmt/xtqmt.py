#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xtqmt.py  ——  xtquant 行情进程
职责：
  1. 监听 UDP 端口，实时接收 tick_reporter 推送的股票代码更新
  2. 接收 xtquant 的 tick 回调
  3. 通过 UDP 实时推送给 tick_reporter（同机器，普通网络进程）
  4. 异步写入本地 SQLite 做归档备份，每天定时清理 1 个月前的数据
"""

import asyncio
import datetime
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import signal
import socket
import threading
import time

import aiosqlite

from xtquant import xtdata
from db_utils import DB_PATH, init_db, insert_tick, purge_old_ticks
from stock_base import STOCK_BASE_FILE, collect_stock_base, write_stock_base_file

# ─────────────────────── 配置 ───────────────────────
REPORTER_HOST  = "127.0.0.1"
REPORTER_PORT  = 19999
QUEUE_MAXSIZE  = 5000       # 归档队列上限，超出则丢弃（不影响 UDP 实时推送）
PURGE_INTERVAL = 86400      # 归档清理周期：每 24 小时执行一次（秒）

# 接收 tick_reporter 推送股票代码的 UDP 监听地址
CODES_LISTEN_HOST = "127.0.0.1"
CODES_LISTEN_PORT = 19998
CODES_RECV_TIMEOUT = 1      # UDP 接收超时（秒），短超时以便及时检查 shutdown 退出信号

# 股票基础数据每日采集时间（开盘 09:30 前）
COLLECT_HOUR = 8
COLLECT_MINUTE = 30
COLLECT_RETRY_HOUR = 9      # 采集失败时重试到 09:30
COLLECT_RETRY_MINUTE = 30


# ── 日志落盘（每日轮转，保留 30 天，UTF-8）──
# 不写控制台：Windows 控制台一旦进入「快速编辑/选择模式」，会把高频日志写满缓冲区并阻塞进程。
# 日志只落盘；控制台仅保留进程崩溃时的 traceback（由解释器直接写 stderr，不经 logging）。
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [XtWriter] %(levelname)s %(message)s",
    handlers=[
        TimedRotatingFileHandler(
            os.path.join(LOG_DIR, "xtqmt.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        ),
    ],
)

# ─────────────────────── 全局状态 ───────────────────────
_queue: asyncio.Queue | None = None
_shutdown: asyncio.Event | None = None
# 主线程退出信号（线程安全），Ctrl+C 时置位，主循环据此跳出
_main_shutdown = threading.Event()
_loop: asyncio.AbstractEventLoop | None = None
_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 当前已订阅的股票代码 → subscription_id 映射
_sub_ids: dict[str, int] = {}
# 当前已订阅的股票代码集合（供回调线程安全读取）
_subscribed_codes: set[str] = set()
_sub_lock = threading.Lock()
# 上次从 API 获取到的 lastUpdateTime，用于跳过无变化的更新
_last_update_time: int = 0
# 采集线程与订阅更新共用，避免 xtdata 并发调用
_xtdata_lock = threading.Lock()


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


# ─────────────────────── 股票代码接收 ───────────────────────

def _setup_codes_listener() -> socket.socket:
    """创建并绑定 UDP 监听 socket，用于接收 reporter 推送的股票代码"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((CODES_LISTEN_HOST, CODES_LISTEN_PORT))
    sock.settimeout(CODES_RECV_TIMEOUT)
    logging.info("[XtWriter] 监听 UDP %s:%d 等待代码推送...", CODES_LISTEN_HOST, CODES_LISTEN_PORT)
    return sock


def receive_codes_from_udp(sock: socket.socket) -> tuple[list[str] | None, int]:
    """
    阻塞等待 reporter 推送股票代码（最多 CODES_RECV_TIMEOUT 秒）。
    返回 (代码列表, lastUpdateTime)；超时时返回 (None, 0)。
    """
    try:
        data, addr = sock.recvfrom(65536)
    except socket.timeout:
        return None, 0

    try:
        msg = json.loads(data.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as e:
        logging.warning("[XtWriter] 解析代码推送消息失败: %s", e)
        return None, 0

    codes = msg.get("stockCode", [])
    last_update = msg.get("lastUpdateTime", 0)
    logging.info(
        "[XtWriter] 收到代码推送: %d 个标的, lastUpdateTime=%s",
        len(codes),
        datetime.datetime.fromtimestamp(last_update / 1000).isoformat() if last_update else "N/A",
    )
    return codes, last_update


# ─────────────────────── 订阅管理 ───────────────────────

def _diff_codes(new_codes: list[str]) -> tuple[list[str], list[str]]:
    """对比新旧代码列表，返回 (需要新增的, 需要退订的)"""
    old_set = set(_sub_ids.keys())
    new_set = set(new_codes)
    to_add = list(new_set - old_set)
    to_remove = list(old_set - new_set)
    return to_add, to_remove


def update_subscriptions(new_codes: list[str]):
    """
    增量更新股票订阅：只订阅新增的，只退订移除的，不变的保持不动。
    """
    global _subscribed_codes

    to_add, to_remove = _diff_codes(new_codes)

    # 订阅/退订与采集线程共用锁，避免 xtdata 并发调用
    with _xtdata_lock:
        # 退订移除的代码
        for code in to_remove:
            seq = _sub_ids.pop(code, None)
            if seq is not None:
                try:
                    xtdata.unsubscribe_quote(seq)
                    logging.info("[XtWriter] 已退订 %s (seq=%s)", code, seq)
                except Exception as e:
                    logging.warning("[XtWriter] 退订 %s 失败: %s", code, e)

        # 订阅新增的代码
        for code in to_add:
            try:
                seq = xtdata.subscribe_quote(
                    stock_code=code,
                    period="tick",
                    callback=tick_callback,
                    count=-1,
                )
                _sub_ids[code] = seq
                logging.info("[XtWriter] 已订阅 %s (seq=%s)", code, seq)
            except Exception as e:
                logging.warning("[XtWriter] 订阅 %s 失败: %s", code, e)

    # 更新全局代码集合（线程安全）
    with _sub_lock:
        _subscribed_codes = set(_sub_ids.keys())

    if to_add or to_remove:
        logging.info(
            "[XtWriter] 订阅更新完成: +%d -%d, 当前共 %d 个标的",
            len(to_add), len(to_remove), len(_sub_ids),
        )


# ─────────────────────── 股票基础数据采集 ───────────────────────

def _stock_base_scheduler():
    """
    每天 08:30 采集一次股票/指数基础数据，写入 stock_base.txt。
    失败时在 08:30–09:30 窗口内每分钟重试，成功当天不再重复。
    运行在独立 daemon 线程，不阻塞主线程 UDP 接收。
    """
    done_date = None
    while True:
        now = datetime.datetime.now()
        in_window = (
            (now.hour, now.minute) >= (COLLECT_HOUR, COLLECT_MINUTE)
            and (now.hour, now.minute) <= (COLLECT_RETRY_HOUR, COLLECT_RETRY_MINUTE)
        )

        if in_window and done_date != now.date():
            logging.info("[XtWriter] 开始采集股票基础数据...")
            try:
                with _xtdata_lock:
                    rows = collect_stock_base()
                write_stock_base_file(rows)
                done_date = now.date()
                logging.info("[XtWriter] 股票基础数据采集完成，共 %d 条", len(rows))
            except Exception:
                logging.exception("[XtWriter] 股票基础数据采集失败，稍后重试")

        time.sleep(30)


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
        # 多标的订阅时 xtquant 一律回调 dict 格式，此分支仅作单标的兜底
        raw = datas if isinstance(datas, list) else [datas]
        with _sub_lock:
            first_code = next(iter(_subscribed_codes), "UNKNOWN")
        items = [(first_code, tick) for tick in raw]

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

        # print(tick_data)

        # 1. UDP 实时推送给 Reporter（同步发送，微秒级，不阻塞回调）
        try:
            _udp_sock.sendto(
                json.dumps(tick_data).encode("utf-8"),
                (REPORTER_HOST, REPORTER_PORT),
            )
            logging.info(
                "[XtWriter] UDP 已推送: ts=%s price=%s",
                tick_data["created_at"], tick_data["price"],
            )
        except Exception as e:
            logging.warning("[XtWriter] UDP 发送失败: %s", e)

        # 2. 异步写 DB 归档（队列满时丢弃，不影响实时推送）
        try:
            _loop.call_soon_threadsafe(_queue.put_nowait, tick_data)
        except asyncio.QueueFull:
            logging.warning("[XtWriter] 归档队列已满，丢弃本条备份")


# ─────────────────────── 启动 / 退出 ───────────────────────

def _trigger_shutdown():
    if _loop and not _loop.is_closed() and _shutdown:
        _loop.call_soon_threadsafe(_shutdown.set)


def _signal_handler(signum, frame):
    logging.info("[XtWriter] 收到退出信号，关闭中...")
    _main_shutdown.set()
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

# 启动股票基础数据采集线程（daemon，随进程退出）
_stock_base_thread = threading.Thread(target=_stock_base_scheduler, name="StockBaseScheduler", daemon=True)
_stock_base_thread.start()

# ─────────────────────── 主循环：实时接收代码推送 + 增量订阅 ───────────────────────

_codes_sock = _setup_codes_listener()

try:
    while not _main_shutdown.is_set():
        new_codes, last_update = receive_codes_from_udp(_codes_sock)

        if new_codes is not None:
            # reporter 推送前已过滤无变化的情况，这里直接更新即可
            _last_update_time = last_update
            update_subscriptions(new_codes)
        # else: UDP 超时（reporter 可能挂了或网络问题），保持现有订阅不变，继续等待

finally:
    _codes_sock.close()
    for code, seq in _sub_ids.items():
        try:
            xtdata.unsubscribe_quote(seq)
        except Exception as e:
            logging.warning("[XtWriter] 取消订阅 %s 失败: %s", code, e)
    logging.info("[XtWriter] 已取消 xtquant 订阅")
    _trigger_shutdown()
    _bg_thread.join(timeout=15)
    _udp_sock.close()
    logging.info("[XtWriter] 进程已安全退出")
