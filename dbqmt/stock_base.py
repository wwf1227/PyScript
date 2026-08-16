#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_base.py  ——  股票/指数基础数据采集

从 QMT 加载全部 A 股股票 + 指数的代码与名称，输出为可上传服务端的文本。
仅被 xtqmt.py 导入（依赖 xtquant，只能在 Windows/QMT 环境运行）。

输出格式：制表符分隔 4 列 —— 代码、名称、板块、股票/指数
"""

import logging
import os
import tempfile

from xtquant import xtdata

# 采集结果写入的共享文件，供 tick_reporter.py 上传
STOCK_BASE_FILE = "stock_base.txt"

SEP = "\t"


# ─────────────────────── 代码分类 ───────────────────────
# 不看板块名，只按代码段判断 —— QMT 的板块名不可靠，
# "沪深京A股" 里混着债券，"上证指数" 里混着B股。

def classify(code: str):
    """返回 (大类, 板块细分)；不是股票/指数就返回 None。"""
    if "." not in code:
        return None
    num, ex = code.split(".", 1)
    if len(num) != 6 or not num.isdigit():
        return None
    h2, h3 = num[:2], num[:3]

    if ex == "SH":
        if h3 in ("600", "601", "603", "605"):
            return "股票", "沪主板"
        if h3 in ("688", "689"):
            return "股票", "科创板"
        if h3 == "900":
            return "股票", "B股"
        if h3 in ("801", "852"):
            return "指数", "申万一二级"
        if h3 == "850":
            return "指数", "申万三级"
        if h3 in ("930", "931", "932", "950"):
            return "指数", "中证系列"
        if h3 in ("970", "980"):
            return "指数", "国证系列"
        if h3 == "000":
            return "指数", "上证系列"

    elif ex == "SZ":
        if h3 in ("000", "001", "003"):
            return "股票", "深主板"
        if h3 == "002":
            return "股票", "中小板"
        if h3 in ("300", "301"):
            return "股票", "创业板"
        if h3 == "200":
            return "股票", "B股"
        if h3 == "399":
            return "指数", "深证系列"

    elif ex == "BJ":
        # 北交所股票段；81x/82x 是债券和定向可转债，剔除
        if h3 == "430" or h3 == "920" or h2 in ("83", "87"):
            return "股票", "北交所"

    return None


# ─────────────────────── 采集 ───────────────────────

def collect_stock_base() -> list[tuple[str, str, str, str]]:
    """
    从 QMT 采集全部股票 + 指数。
    返回排序后的 (代码, 名称, 板块, 股票/指数) 列表。
    """
    xtdata.download_sector_data()

    sectors = xtdata.get_sector_list() or []
    targets = [s for s in sectors if ("A股" in s or "指数" in s
                                      or s in ("科创板", "创业板"))]
    logging.info("[stock_base] 扫描板块 %d 个", len(targets))

    codes = set()
    for sec in targets:
        try:
            codes.update(xtdata.get_stock_list_in_sector(sec) or [])
        except Exception:
            continue

    logging.info("[stock_base] QMT 原始代码 %d 个，开始分类…", len(codes))

    rows = []
    no_name = 0
    for code in codes:
        r = classify(code.strip().upper())
        if not r:
            continue
        cat, board = r
        detail = xtdata.get_instrument_detail(code) or {}
        name = str(detail.get("InstrumentName", "")).strip()
        if not name:
            no_name += 1
        rows.append((code, name, board, cat))

    # 先股票后指数，再按板块、代码排序
    rows.sort(key=lambda x: (x[3] != "股票", x[2], x[0]))
    if no_name:
        logging.warning("[stock_base] %d 个代码取不到名称，行情端可能未下载该品种", no_name)
    return rows


# ─────────────────────── 输出 ───────────────────────

def write_stock_base_file(rows: list[tuple[str, str, str, str]], path: str = STOCK_BASE_FILE) -> None:
    """原子写入制表符分隔的 4 列文本（先写临时文件再 rename）"""
    dirname = os.path.dirname(os.path.abspath(path)) or "."
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=dirname, delete=False, suffix=".tmp"
    ) as f:
        for row in rows:
            f.write(SEP.join(row) + "\n")
        tmp_path = f.name
    os.replace(tmp_path, path)
    logging.info("[stock_base] 已写入 %d 条记录到 %s", len(rows), path)
