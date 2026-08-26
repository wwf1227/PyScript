#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tick_reporter.py  ——  普通网络进程
职责：
  1. 监听 UDP 端口，接收 xtqmt 实时推送的 tick
  2. 通过 aiohttp（连接池复用）上报到外部平台
  3. 定期从 API 拉取运行时股票代码，每次都通过 UDP 推送给 xtqmt（由 xtqmt 端做增量订阅）
  4. 每天上传 xtqmt 采集的股票/指数基础数据到服务端
"""

import asyncio
import datetime
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import signal
import socket
import time

import aiohttp
import certifi
import ssl

API_HOST = "https://wkatt1.tingyun.com"
AD_API_HOST = "https://wkadt1.tingyun.com"

REPORT_URL  = f"{AD_API_HOST}/appdatasvr/finbench/v1/data/standard"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 19999

# ── 股票代码拉取配置 ──
RUNTIME_CODE_URL = f"{API_HOST}/apptasksvr/stock-manager/query-runtime-code"
API_TIMEOUT = aiohttp.ClientTimeout(total=5)
POLL_INTERVAL = 60            # 每 60 秒拉取一次

#  CA 证书
ssl_ctx = ssl.create_default_context(cafile=certifi.where())

# 推送给 xtqmt 的 UDP 地址
CODES_PUSH_HOST = "127.0.0.1"
CODES_PUSH_PORT = 19998

# ── 股票基础数据上传配置 ──
UPLOAD_URL = f"{API_HOST}/apptasksvr/stock-manager/upload-code-data"
STOCK_BASE_FILE = "stock_base.txt"          # xtqmt 采集写入的共享文件
UPLOAD_CHECK_INTERVAL = 60                  # 每分钟检查一次是否有新文件

# ── 日志落盘（每日轮转，保留 30 天，UTF-8）──
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Reporter] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        TimedRotatingFileHandler(
            os.path.join(LOG_DIR, "tick_reporter.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        ),
    ],
)

_shutdown: asyncio.Event | None = None


# ─────────────────────── 数据转换 ───────────────────────

def _build_payload(tick: dict) -> dict:
    # created_at 已在发送侧统一为毫秒时间戳（int），直接使用
    # source 按 symbol 格式区分：掘金为 "SHSE.000001"，xtquant 为 "000001.SH"
    symbol: str = tick["symbol"]
    if "." in symbol:
        parts = symbol.split(".", 1)
        # 掘金格式：交易所前缀.代码（如 SHSE.000001）
        # xtquant 格式：代码.交易所后缀（如 000001.SH）
        if parts[0].isalpha():          # 掘金：前缀全为字母
            stock_id = parts[1]
            source   = "掘金量化"
        else:                           # xtquant：前缀为数字代码
            stock_id = parts[0]
            source   = "QMT"
    else:
        stock_id = symbol
        source   = "未知"

    return {
        "stock_id":   stock_id,
        "price":      tick["price"],
        "high":       tick["high"],
        "low":        tick["low"],
        "cum_volume": tick["cum_volume"],
        "cum_amount": tick["cum_amount"],
        "timestamp":  tick["created_at"],   # 已是毫秒时间戳，无需转换
        "source":     source,
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
            async with session.post(
                REPORT_URL,
                json=[payload],
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=ssl_ctx,
            ) as resp:
                resp.raise_for_status()
                logging.info("[Reporter] 上报成功 状态码=%s", resp.status)
        except aiohttp.ClientResponseError as e:
            body = ""
            if "resp" in locals():  # 确保 resp 已定义
                try:
                    body = await resp.text()
                except Exception:
                    body = "<无法读取响应体>"
            logging.error("[Reporter] 上报失败 HTTP=%s body=%s", e.status, body)
        except Exception as e:
            logging.error("[Reporter] 上报异常: %s", e)

    logging.info("[Reporter] 上报任务已退出")


# ─────────────────────── 股票代码拉取 ───────────────────────

async def _fetch_runtime_codes(session: aiohttp.ClientSession) -> tuple[list[str] | None, int]:
    """
    从服务端获取运行时股票代码列表。
    返回 (代码列表, lastUpdateTime)；失败时列表为 None。
    """
    try:
        async with session.get(RUNTIME_CODE_URL, timeout=API_TIMEOUT, ssl=ssl_ctx) as resp:
            resp.raise_for_status()
            result = await resp.json()
    except aiohttp.ClientResponseError as e:
        logging.warning("[Reporter] 拉取股票代码失败 HTTP=%s", e.status)
        return None, 0
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.warning("[Reporter] 拉取股票代码失败（网络错误）: %s", e)
        return None, 0
    except ValueError as e:
        logging.warning("[Reporter] 拉取股票代码失败（JSON 解析错误）: %s", e)
        return None, 0

    if result.get("resultCode") != 0:
        logging.warning("[Reporter] 拉取股票代码失败（业务错误）: %s", result.get("message"))
        return None, 0

    data = result.get("data")
    if data is None:
        logging.warning("[Reporter] 拉取股票代码失败: data 为 null")
        return None, 0

    codes = data.get("stockCode", [])
    last_update = data.get("lastUpdateTime", 0)
    logging.info("[Reporter] 拉取股票代码成功: %d 个标的, lastUpdateTime=%s",
                 len(codes),
                 time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_update / 1000)) if last_update else "N/A")
    return codes, last_update


def _push_codes_via_udp(codes: list[str], last_update: int) -> None:
    """通过 UDP 将股票代码列表推送给 xtqmt"""
    data = json.dumps({
        "lastUpdateTime": last_update,
        "stockCode": codes,
    }, ensure_ascii=False).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(data, (CODES_PUSH_HOST, CODES_PUSH_PORT))
        logging.info("[Reporter] 已推送 %d 个标的到 xtqmt", len(codes))
    except Exception as e:
        logging.warning("[Reporter] 推送股票代码失败: %s", e)
    finally:
        sock.close()


async def _codes_poller(session: aiohttp.ClientSession):
    """
    定期从 API 拉取股票代码，每次拉取都推送给 xtqmt。
    是否变化、是否增量订阅由 xtqmt 端判断（update_subscriptions 幂等）：
      - 代码未变化时，xtqmt 的 _diff_codes 结果为 no-op；
      - xtqmt 重启后 _sub_ids 为空，收到的代码会全部重新订阅。
    启动时立即拉取并推送一次，之后每 POLL_INTERVAL 秒拉取一次。
    """
    first = True

    while True:
        # 等待 POLL_INTERVAL 秒或 shutdown（首次跳过等待）
        if not first:
            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=POLL_INTERVAL)
                break  # shutdown 触发
            except asyncio.TimeoutError:
                pass
        first = False

        codes, last_update = await _fetch_runtime_codes(session)
        if codes is None:
            logging.warning("[Reporter] 拉取股票代码失败，保留上次列表不变")
            continue

        # 每次都推，xtqmt 端用 _diff_codes 做增量订阅
        _push_codes_via_udp(codes, last_update)

    logging.info("[Reporter] 股票代码拉取任务已退出")


# ─────────────────────── 股票基础数据上传 ───────────────────────

async def _upload_stock_base(session: aiohttp.ClientSession) -> bool:
    """将 stock_base.txt 以 multipart/form-data 上传到服务端，成功返回 True"""
    try:
        with open(STOCK_BASE_FILE, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename="stock_base.txt", content_type="text/plain")
            async with session.post(UPLOAD_URL, data=data, timeout=aiohttp.ClientTimeout(total=300), ssl=ssl_ctx) as resp:
                resp.raise_for_status()
                body = await resp.json()
    except aiohttp.ClientResponseError as e:
        body = ""
        if "resp" in locals():  # 确保 resp 已定义
            try:
                body = await resp.text()
            except Exception:
                body = "<无法读取响应体>"
        logging.error("[Reporter] 上传股票基础数据失败 HTTP=%s body=%s", e.status, body)
        return False
    except Exception as e:
        logging.error("[Reporter] 上传股票基础数据异常: %s", e)
        return False

    if body.get("resultCode") != 0:
        logging.error("[Reporter] 上传股票基础数据失败: %s", body.get("resultMsg"))
        return False

    d = body.get("data") or {}
    logging.info(
        "[Reporter] 上传股票基础数据成功: 总计 %s 条，新增 %s，更新 %s，无变化 %s，非法 %s",
        d.get("total"), d.get("insert"), d.get("update"), d.get("unchanged"), d.get("invalid"),
    )
    return True


async def _stock_base_uploader(session: aiohttp.ClientSession):
    """
    检测 stock_base.txt 是否出现当天新生成的文件，出现则上传一次。
    每天最多上传一次，避免重复（上传本身幂等，重复也无害）；失败会重试。
    """
    last_upload_date = None
    logging.info("[Reporter] 股票基础数据上传任务已启动（每 %d 秒检查 %s）",
                 UPLOAD_CHECK_INTERVAL, STOCK_BASE_FILE)
    while True:
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=UPLOAD_CHECK_INTERVAL)
            break  # shutdown 触发
        except asyncio.TimeoutError:
            pass

        try:
            if not os.path.exists(STOCK_BASE_FILE):
                logging.debug("[Reporter] %s 不存在，等待 xtqmt 生成...", STOCK_BASE_FILE)
                continue
            file_date = datetime.date.fromtimestamp(os.path.getmtime(STOCK_BASE_FILE))
            today = datetime.date.today()
            # 仅上传当天新生成的文件，且当天只上传成功一次
            if file_date != today:
                logging.debug("[Reporter] %s 非当天生成（%s），跳过", STOCK_BASE_FILE, file_date)
                continue
            if last_upload_date == today:
                logging.debug("[Reporter] 今天已上传过 %s，跳过", STOCK_BASE_FILE)
                continue
            logging.info("[Reporter] 发现当天 %s（%s），开始上传...", STOCK_BASE_FILE, file_date)
            if await _upload_stock_base(session):
                last_upload_date = today
        except Exception:
            logging.exception("[Reporter] 股票基础数据上传检查异常")

    logging.info("[Reporter] 股票基础数据上传任务已退出")


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
        await asyncio.gather(
            _report_worker(queue, session),
            _codes_poller(session),
            _stock_base_uploader(session),
        )

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
