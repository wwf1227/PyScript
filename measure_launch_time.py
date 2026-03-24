#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android App 启动时间测试工具
支持:
 - 通过命令行指定应用名 (--apps)
 - 从 Excel 文件读取应用名列表
 - 采集 am start -W TotalTime / WaitTime
 - 采集 logcat 中的 Displayed (TTID)
 - 结果输出到新的 Excel 文件
"""

import argparse
import os
import subprocess
import time
import pandas as pd
from datetime import datetime
import re
import sys

from logger import Logger

logger_file = f"launch_time/start_time_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logger = Logger(logger_file)


# =============== 工具函数 ===============

def run_adb(cmd, ignore_error=False):
    """
    运行 adb 命令并返回输出
    :param cmd: adb 命令字符串，例如 "shell pm list packages"
    :param ignore_error: 是否忽略错误，False 则命令失败会抛异常
    :return: stdout 输出字符串
    """
    try:
        result = subprocess.run(f"adb {cmd}", shell=True, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode != 0 and not ignore_error:
            logger.log(level="ERROR", message=stderr)
            raise RuntimeError(f"ADB 命令失败: {cmd}\nSTDOUT: {stdout}\nSTDERR: {stderr}")
        return stdout
    except subprocess.TimeoutExpired:
        logger.log(level="ERROR", message=f"ADB 命令超时: {cmd}")
        raise RuntimeError(f"ADB 命令超时: {cmd}")


def get_main_activity(pkg):
    """根据包名获取主启动 Activity"""
    activity = run_adb(f"shell cmd package resolve-activity --brief {pkg}")
    lines = [l for l in activity.splitlines() if l.strip() and not l.startswith("Error")]
    return lines[-1] if lines else None


def get_version_name(pkg):
    """根据包名获取应用版本号"""
    try:
        output = run_adb(f"shell dumpsys package {pkg} | grep versionName")
    except Exception as e:
        return None

    match = re.search(r"versionName\s*=\s*([\w.\-]+)", output)
    return match.group(1) if match else None


def measure_launch_time(pkg_activity, repeat):
    """测量启动时间和 TTID，返回平均值"""
    total_times, wait_times, ttid_times = [], [], []

    for i in range(repeat):

        logger.log(f"  🚀 第 {i + 1} 次启动...")

        # 清空日志，准备抓取 Displayed
        run_adb("logcat -c")

        # 启动应用并记录时间
        output = run_adb(f"shell am start -W {pkg_activity}")
        total = re.search(r"TotalTime: (\d+)", output)
        # wait = re.search(r"WaitTime: (\d+)", output)
        total_time = int(total.group(1)) if total else None
        # wait_time = int(wait.group(1)) if wait else None

        # 获取 Displayed (TTID)
        # log_output = run_adb('logcat -d | grep "Displayed" | tail -n 1')
        # ttid_match = re.search(r"\+(\d+)ms", log_output)
        # ttid_time = int(ttid_match.group(1)) if ttid_match else None

        if total_time:
            total_times.append(total_time)
        # if wait_time:
        #     wait_times.append(wait_time)
        # if ttid_time:
        #     ttid_times.append(ttid_time)

        logger.log(f"     ✅ TotalTime={total_time}ms")

        time.sleep(2)

        pkg = pkg_activity.split("/")[0]
        run_adb(f"shell am force-stop {pkg}")
        time.sleep(5)

    if total_times:
        # 原始平均值
        avg_total = sum(total_times) / len(total_times)

        # 去除最大最小值后的平均值
        if len(total_times) > 2:
            trimmed = sorted(total_times)[1:-1]
            avg_trimmed = sum(trimmed) / len(trimmed)
        else:
            avg_trimmed = avg_total  # 长度不足，直接使用原始平均
    else:
        avg_total = None
        avg_trimmed = None
    # avg_wait = sum(wait_times) / len(wait_times) if wait_times else None
    # avg_ttid = sum(ttid_times) / len(ttid_times) if ttid_times else None

    # return avg_total, avg_wait, avg_ttid
    return avg_total, avg_trimmed, total_times


# =============== 主逻辑 ===============

def main():
    parser = argparse.ArgumentParser(description="Android App 启动时间测试工具")
    parser.add_argument("--packages", type=str,
                        help="包名列表，用逗号分隔（例如：com.tencent.mm,com.ss.android.ugc.aweme）")
    parser.add_argument("--repeat", type=int, default=5, help="每个应用测试次数")
    parser.add_argument("--input", type=str, help="可选，从Excel文件读取包名列表（列名必须包含 'Package'）")
    args = parser.parse_args()

    # 读取包名列表
    pkg_list = []
    if args.packages:
        pkg_list = [p.strip() for p in args.packages.split(",")]
    elif args.input:
        df = pd.read_excel(args.input)
        pkg_list = df["package"].dropna().tolist()
    else:
        print("❌ 请使用 --packages 或 --input 指定包名来源")
        sys.exit(1)

    logger.log(f"📋 测试应用包名: {pkg_list}")
    logger.log(f"🔁 每个应用重复次数: {args.repeat}")

    results = []
    try:
        for pkg in pkg_list:
            logger.log(f"\n🔍 测试包名: {pkg}")
            version_name = get_version_name(pkg)
            main_activity = get_main_activity(pkg)
            if not main_activity:
                logger.log(f"⚠️ 无法找到主 Activity，跳过")
                results.append({"Package": pkg, "MainActivity": None,
                                "versionName": version_name,
                                "AvgTotalTime(s)": None,
                                "AvgTrimmedTime(s)": None, })
                continue

            logger.log(f"➡️  主 Activity: {main_activity}")
            avg_total, avg_trimmed, total_times = measure_launch_time(main_activity, args.repeat)
            data = {
                "Package": pkg,
                "MainActivity": main_activity.split("/")[-1],
                "versionName": version_name,
                "AvgTotalTime(s)": round(avg_total / 1000, 2),
                "AvgTrimmed(s)": round(avg_trimmed / 1000, 2),
                # "AvgWaitTime(ms)": avg_wait,
                # "AvgTTID(ms)": avg_ttid
            }
            for i, t in enumerate(total_times):
                data[f"第{i + 1}次启动(ms)"] = t
            results.append(data)

            time.sleep(6)
    except Exception as e:
        logger.log(level="ERROR", message=str(e))
    finally:
        # 保存结果到 Excel
        file_name = f"launch_times_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_file = os.path.join("launch_time", file_name)
        pd.DataFrame(results).to_excel(output_file, index=False)
        logger.log(f"\n✅ 测试完成！结果已保存到：{output_file}")


if __name__ == "__main__":
    main()
