#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/11/3
 @Author : wwf
 Description: 
"""
import glob
import os
import subprocess
import pandas as pd
from datetime import datetime
import re
from logger import Logger


def select_apk(pkg, apk_files, apk_dir, logger=None):
    """
    从 apk_files 中为指定包名选择合适的 APK 文件。
    匹配规则：
        - 优先匹配精确文件 pkg.apk
        - 否则匹配 pkg_版本号.apk
        - 不会误匹配 pkgX.apk 或 pkg.extra.apk
    """
    # 精确匹配文件
    exact_filename = f"{pkg}.apk"

    # 只匹配以下两种情况：
    # 1. 精确文件：com.a.apk
    # 2. 带版本号：com.a_1.0.apk、com.a_2.3.4.apk
    pattern = re.compile(rf"^{re.escape(pkg)}(?:_(\d+(?:\.\d+)*))?\.apk$")
    matched = [f for f in apk_files if pattern.match(f)]

    if not matched:
        if logger:
            logger.log(message=f"{pkg} 的 APK 文件不存在", level="ERROR")
        return None

    if exact_filename in matched:
        selected_apk = exact_filename
    else:
        # 提取版本号排序
        def version_key(filename):
            m = pattern.match(filename)
            if m and m.group(1):
                return tuple(map(int, m.group(1).split('.')))
            return (0,)

        matched.sort(key=version_key, reverse=True)
        selected_apk = matched[0]

    # if logger:
    #     logger.log(message=f"为 {pkg} 选择的安装包: {selected_apk}")

    return os.path.join(apk_dir, selected_apk)


class APKManager:

    def __init__(self):
        logger_file = f"launch_time/install_apk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.logger = Logger(logger_file)

    def run_adb(self, cmd, ignore_error=False):
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
                self.logger.log(level="ERROR", message=stderr)
                raise RuntimeError(f"ADB 命令失败: {cmd}\nSTDOUT: {stdout}\nSTDERR: {stderr}")
            return stdout
        except subprocess.TimeoutExpired:
            self.logger.log(level="ERROR", message=f"ADB 命令超时: {cmd}")
            raise RuntimeError(f"ADB 命令超时: {cmd}")

    def get_version_name(self, pkg):
        """根据包名获取应用版本号"""
        try:
            output = self.run_adb(f"shell dumpsys package {pkg} | grep versionName")
        except Exception as e:
            return None

        match = re.search(r"versionName\s*=\s*([\w.\-]+)", output)
        return match.group(1) if match else None

    def get_installed_packages(self, include_system=False):
        """
        获取设备上已安装的包名列表。
        :param include_system: 是否包含系统应用（默认只返回第三方）
        :return: set[str] 已安装包名集合
        """
        cmd = "shell pm list packages"
        if not include_system:
            cmd += " -3"  # 只获取第三方应用

        output = self.run_adb(cmd)
        packages = {
            line.replace("package:", "").strip()
            for line in output.splitlines()
            if line.strip()
        }
        return packages

    def dump_apk(self):

        df = pd.read_excel("launch_time/banks.xlsx")

        apk_path = os.path.join("launch_time", "apks")
        if not os.path.exists(apk_path):
            os.makedirs(apk_path)

        pkg_list = df["package"].dropna().tolist()

        apk_files = [f for f in os.listdir(apk_path) if f.endswith(".apk")]

        for pkg in pkg_list:
            if not pkg:
                continue

            # 判断是否已存在
            found = any(f.startswith(pkg) and f.endswith(".apk") for f in apk_files)
            if found:
                self.logger.log(f"{pkg} 已存在，跳过dump。")
                continue

            output = self.run_adb(f"shell pm path {pkg}")
            if not output:
                self.logger.log(message=f"{pkg} apk 未找到，请手动检查", level="ERROR")
                continue

            apk_paths = [line.split(":", 1)[1].strip() for line in output.splitlines() if line.startswith("package:")]
            if not apk_paths:
                self.logger.log(message=f"{pkg} 未找到任何apk路径", level="ERROR")
                continue

            version_name = self.get_version_name(pkg)
            for i, p in enumerate(apk_paths):
                apk_file_path = os.path.join(apk_path, f"{pkg}_{i}_{version_name}.apk" if len(
                    apk_paths) > 1 else f"{pkg}_{version_name}.apk")
                self.run_adb(f"pull -a {p} {apk_file_path}")
                self.logger.log(message=f"已提取 {pkg} -> {apk_file_path}")

    def install_apk(self, new_device_id=None):

        df = pd.read_excel("launch_time/banks.xlsx")
        pkg_list = df["package"].dropna().tolist()

        apk_dir = os.path.join("launch_time", "apks")
        if not os.path.exists(apk_dir):
            self.logger.log(message="未找到APK目录，请先执行 dump_apk()", level="ERROR")
            return

        apk_files = [f for f in os.listdir(apk_dir) if f.endswith(".apk")]
        if not apk_files:
            self.logger.log(message="未找到任何APK文件，请检查 dump_apk 结果", level="ERROR")
            return

        # 如果没有指定设备，则让 adb 自动安装到默认连接设备
        device_arg = f"-s {new_device_id}" if new_device_id else ""

        # 获取已安装的第三方包名
        installed_packages = self.get_installed_packages()

        # for apk_file in apk_files:
        #     full_path = os.path.join(apk_path, apk_file)
        #     self.logger.log(message=f"正在安装 {apk_file} 到新设备...", level="INFO")
        #
        #     result = self.run_adb(f"{device_arg} install -r {full_path}")
        #
        #     if "Success" in str(result):
        #         self.logger.log(message=f"✅ 安装成功：{apk_file}", level="INFO")
        #     else:
        #         self.logger.log(message=f"❌ 安装失败：{apk_file}，请检查：{result}", level="ERROR")

        for pkg in pkg_list:
            if not pkg:
                continue

            # 判断是否已安装
            if pkg in installed_packages:
                self.logger.log(message=f"{pkg} 已安装，跳过安装。")
                continue

            # 匹配以包名开头且以.apk结尾的文件
            # matched = [f for f in apk_files if f.startswith(pkg) and f.endswith(".apk")]
            # if not matched:
            #     self.logger.log(message=f"{pkg} 的 APK 文件不存在", level="ERROR")
            #     continue

            # 获取最后一个
            # apk_file = matched[-1]
            full_path = select_apk(pkg, apk_files, apk_dir, self.logger)
            print(full_path)
            # full_path = os.path.join(apk_dir, selected)

            self.logger.log(message=f"正在安装 {full_path} 到新设备...", level="INFO")
            try:
                result = self.run_adb(f"{device_arg} install -r {full_path}")

                if "Success" in str(result):
                    self.logger.log(message=f"✅ 安装成功：{pkg}.apk", level="INFO")
                else:
                    self.logger.log(message=f"❌ 安装失败：{pkg}.apk，请检查：{result}", level="ERROR")
            except Exception as e:
                self.logger.log(message=f"❌ 安装失败：{pkg}.apk，{e}", level="ERROR")


if __name__ == "__main__":
    apkM = APKManager()
    # apkM.install_apk()
    # print(apkM.get_installed_packages())
    apkM.dump_apk()
