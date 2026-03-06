#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_utils.py
数据库工具类 —— tick_writer / tick_reporter 共用
"""

import datetime
import time

import aiosqlite
import logging

DB_PATH = "ticks.db"

# tick 状态常量
STATUS_PENDING   = 0   # 待上报
STATUS_REPORTING = 1   # 上报中（Reporter 已取走）
STATUS_DONE      = 2   # 上报成功，可归档/清理
STATUS_FAILED    = 3   # 上报失败，待重试


# ───────────────────────── 初始化 ─────────────────────────

async def init_db(db: aiosqlite.Connection) -> None:
    """建表 + 开启 WAL（支持一写多读的跨进程并发）"""
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS ticks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT    NOT NULL,
            open         REAL,
            high         REAL,
            low          REAL,
            price        REAL,
            cum_volume   INTEGER,
            cum_amount   REAL,
            trade_type   INTEGER,
            last_volume  INTEGER,
            cum_position INTEGER,
            last_amount  REAL,
            created_at   TEXT,
            created_ts   INTEGER,          -- created_at 对应的 Unix 毫秒时间戳
            status       INTEGER NOT NULL DEFAULT 0,  -- 0待上报 1上报中 2完成 3失败
            retry_count  INTEGER NOT NULL DEFAULT 0,
            updated_at   INTEGER           -- 状态变更时的 Unix 毫秒时间戳
        )
        """
    )
    # 加速 Reporter 的轮询查询
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticks_status ON ticks(status, id)"
    )
    await db.commit()
    logging.info("[db_utils] 数据库初始化完成: %s", DB_PATH)


# ───────────────────────── 写入（Writer 使用）─────────────────────────

async def insert_ticks(db: aiosqlite.Connection, ticks: list[dict]) -> None:
    """
    批量写入 tick，初始 status=STATUS_PENDING。
    写入失败会记录日志并丢弃本批，不抛出异常，不影响主流程。
    """
    if not ticks:
        return
    try:
        now_ms = int(time.time() * 1000)   # 写入时的当前 Unix 毫秒时间戳

        def _to_ts_ms(created_at: str) -> int:
            """将 '2026-03-06 10:21:15.037000+08:00' 解析为 Unix 毫秒时间戳"""
            try:
                dt = datetime.datetime.fromisoformat(created_at)
                return int(dt.timestamp() * 1000)
            except Exception:
                logging.warning("[db_utils] created_at 解析失败，使用当前时间: %s", created_at)
                return now_ms

        rows = [
            {**t, "created_ts": _to_ts_ms(t["created_at"]), "updated_at": now_ms}
            for t in ticks
        ]

        await db.executemany(
            """
            INSERT INTO ticks (
                symbol, open, high, low, price,
                cum_volume, cum_amount, trade_type, last_volume,
                cum_position, last_amount, created_at, created_ts, status, updated_at
            ) VALUES (
                :symbol, :open, :high, :low, :price,
                :cum_volume, :cum_amount, :trade_type, :last_volume,
                :cum_position, :last_amount, :created_at, :created_ts, 0, :updated_at
            )
            """,
            rows,
        )
        await db.commit()
        logging.debug("[db_utils] 批量写入 %d 条 tick", len(ticks))
    except Exception:
        logging.exception("[db_utils] 批量写入失败，丢弃本批 %d 条", len(ticks))


# ───────────────────────── 查询（Reporter 使用）─────────────────────────

async def fetch_pending_ticks(
    db: aiosqlite.Connection,
    batch_size: int = 50,
    max_retry: int = 3,
) -> list[dict]:
    """
    取出一批待上报的 tick（status=PENDING 或 FAILED 且 retry_count < max_retry）。
    同时将这些行的 status 置为 REPORTING，防止重复取走。
    返回字典列表，包含 id 字段供后续 mark 使用。
    """
    async with db.execute(
        """
        SELECT id, symbol, open, high, low, price,
               cum_volume, cum_amount, trade_type, last_volume,
               cum_position, last_amount, created_at, created_ts,
               updated_at, retry_count
        FROM ticks
        WHERE (status = ? OR (status = ? AND retry_count < ?))
        ORDER BY id
        LIMIT ?
        """,
        (STATUS_PENDING, STATUS_FAILED, max_retry, batch_size),
    ) as cursor:
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

    if not rows:
        return []

    ticks = [dict(zip(columns, row)) for row in rows]
    ids = [t["id"] for t in ticks]

    # 标记为"上报中"，避免并发重取
    placeholders = ",".join("?" * len(ids))
    await db.execute(
        f"UPDATE ticks SET status=?, updated_at=? WHERE id IN ({placeholders})",
        [STATUS_REPORTING, int(time.time() * 1000), *ids],
    )
    await db.commit()

    logging.debug("[db_utils] 取出 %d 条待上报 tick", len(ticks))
    return ticks


async def mark_ticks_done(db: aiosqlite.Connection, ids: list[int]) -> None:
    """将上报成功的 tick 标记为 DONE"""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    await db.execute(
        f"UPDATE ticks SET status=?, updated_at=? WHERE id IN ({placeholders})",
        [STATUS_DONE, int(time.time() * 1000), *ids],
    )
    await db.commit()
    logging.debug("[db_utils] 标记 %d 条 tick 为 DONE", len(ids))


async def mark_ticks_failed(db: aiosqlite.Connection, ids: list[int]) -> None:
    """将上报失败的 tick 标记为 FAILED，并自增重试次数"""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    await db.execute(
        f"""
        UPDATE ticks
        SET status=?, retry_count=retry_count+1, updated_at=?
        WHERE id IN ({placeholders})
        """,
        [STATUS_FAILED, int(time.time() * 1000), *ids],
    )
    await db.commit()
    logging.debug("[db_utils] 标记 %d 条 tick 为 FAILED", len(ids))


# ───────────────────────── 清理（可选定期任务）─────────────────────────

async def purge_done_ticks(db: aiosqlite.Connection, keep_hours: int = 24) -> int:
    """
    清理超过 keep_hours 小时的已完成 tick，返回删除行数。
    可由 Reporter 定期调用，避免数据库无限增长。
    """
    cutoff_ms = int((time.time() - keep_hours * 3600) * 1000)
    cursor = await db.execute(
        "DELETE FROM ticks WHERE status = ? AND updated_at < ?",
        (STATUS_DONE, cutoff_ms),
    )
    await db.commit()
    count = cursor.rowcount
    if count:
        logging.info("[db_utils] 已清理 %d 条过期 DONE tick", count)
    return count