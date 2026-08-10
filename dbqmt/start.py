#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start.py  ——  一键启动 tick_reporter + xtqmt

用法：
    python start.py

行为：
    1. 先启动 tick_reporter（有外网，负责拉取代码 + 上报数据）
    2. 等待 3 秒让 reporter 完成初始化
    3. 再启动 xtqmt（仅 QMT 网络，负责行情订阅 + 推送）
    4. reporter 通过 UDP 实时推送代码变化给 xtqmt
    5. Ctrl+C 时同时关闭两个子进程
"""

import os
import signal
import subprocess
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTER_SCRIPT = os.path.join(SCRIPTS_DIR, "tick_reporter.py")
XTQMT_SCRIPT    = os.path.join(SCRIPTS_DIR, "xtqmt.py")

_procs: list[subprocess.Popen] = []


def _terminate_all():
    """向所有子进程发送 Ctrl+C 信号"""
    for p in _procs:
        if p.poll() is None:
            print(f"[start] 正在关闭 {p.args!r} ...")
            try:
                if sys.platform == "win32":
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    p.terminate()
            except Exception:
                pass


def _signal_handler(signum, frame):
    print("\n[start] 收到退出信号，关闭子进程...")
    _terminate_all()


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)


def main():
    # 1. 启动 tick_reporter
    print("[start] 启动 tick_reporter ...")
    reporter = subprocess.Popen(
        [sys.executable, REPORTER_SCRIPT],
        cwd=SCRIPTS_DIR,
    )
    _procs.append(reporter)

    # 2. 等待 reporter 初始化（启动 UDP 监听 + 首次 API 拉取）
    time.sleep(3)
    if reporter.poll() is not None:
        print(f"[start] tick_reporter 异常退出，返回码 {reporter.returncode}，终止启动")
        sys.exit(1)

    # 3. 启动 xtqmt
    print("[start] 启动 xtqmt ...")
    xtqmt = subprocess.Popen(
        [sys.executable, XTQMT_SCRIPT],
        cwd=SCRIPTS_DIR,
    )
    _procs.append(xtqmt)

    print("[start] 两个进程均已启动，按 Ctrl+C 退出")

    # 4. 等待任一进程退出，或用户 Ctrl+C
    try:
        while True:
            for p in _procs:
                if p.poll() is not None:
                    print(f"[start] 进程 {p.args!r} 已退出（返回码 {p.returncode}），关闭其余进程")
                    _terminate_all()
                    # 等待另一个进程结束
                    for other in _procs:
                        if other.poll() is None:
                            try:
                                other.wait(timeout=10)
                            except subprocess.TimeoutError:
                                other.kill()
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _terminate_all()
        for p in _procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutError:
                p.kill()
                p.wait()
        print("[start] 所有进程已退出")


if __name__ == "__main__":
    main()
