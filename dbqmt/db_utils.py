#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_utils.py
数据库工具类 —— 仅用于 tick 归档，供排查使用
数据保留最近 1 个月，由 tick_writer 定期清理
"""

import logging
import time

import aiosqlite

DB_PATH = "ticks.db"


# ───────────────────────── 初始化 ─────────────────────────

async def init_db(db: aiosqlite.Connection) -> None:
    """建表 + 开启 WAL（支持 Writer/Reporter 跨进程并发读写）"""
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
            created_at   INTEGER NOT NULL  -- 毫秒时间戳，两端发送侧统一转换后写入
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticks_created_at ON ticks(created_at)"
    )
    await db.commit()
    logging.info("[db_utils] 数据库初始化完成: %s", DB_PATH)


# ───────────────────────── 写入 ─────────────────────────

async def insert_tick(db: aiosqlite.Connection, tick: dict) -> None:
    """
    写入单条 tick 归档记录。
    写入失败只记录日志，不抛异常，不影响主流程。
    """
    try:
        await db.execute(
            """
            INSERT INTO ticks (
                symbol, open, high, low, price,
                cum_volume, cum_amount, trade_type, last_volume,
                cum_position, last_amount, created_at
            ) VALUES (
                :symbol, :open, :high, :low, :price,
                :cum_volume, :cum_amount, :trade_type, :last_volume,
                :cum_position, :last_amount, :created_at
            )
            """,
            tick,
        )
        await db.commit()
        logging.debug("[db_utils] 归档 tick: ts=%s price=%s", tick["created_at"], tick["price"])
    except Exception:
        logging.exception("[db_utils] 写入失败，丢弃本条 tick")


# ───────────────────────── 清理 ─────────────────────────

async def purge_old_ticks(db: aiosqlite.Connection, keep_days: int = 30) -> int:
    """
    删除超过 keep_days 天的归档记录，返回删除行数。
    由 tick_writer 每天定时调用一次。
    """
    cutoff_ms = int((time.time() - keep_days * 86400) * 1000)
    cursor = await db.execute(
        "DELETE FROM ticks WHERE created_at < ?",
        (cutoff_ms,),
    )
    await db.commit()
    count = cursor.rowcount
    if count:
        logging.info("[db_utils] 已清理 %d 条超过 %d 天的归档 tick", count, keep_days)
    return count
