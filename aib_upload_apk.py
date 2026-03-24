#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/11/12
 @Author : wwf
 Description: 
"""
import hashlib
import os
import subprocess
import threading
import time
import httpx
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type


def get_apk_name(apk_path):
    """
    使用 aapt 获取 APK 的应用名称
    """
    try:
        apk_path = os.path.abspath(apk_path)
        if not shutil.which("aapt"):
            print("❌ 未找到 aapt，请确保已安装并加入 PATH。")
            return None

        result = subprocess.run(
            ["aapt", "dump", "badging", apk_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        output = result.stdout
        for line in output.splitlines():
            if line.startswith("application-label"):
                # 兼容 application-label-zh-CN 等多语言标签
                app_name = line.split(":", 1)[1].strip().strip("'")
                return app_name
    except Exception as e:
        print(f"⚠️ 解析 APK 名称失败: {e}")
    return None


class AibApkManager:
    def __init__(self, apk_dir, base_url, cookie, max_workers=4):
        self.apk_dir = os.path.abspath(apk_dir)
        self.base_url = base_url.rstrip('/')
        self.cookie = cookie
        self.client = httpx.Client(headers={"Cookie": self.cookie})
        self.max_workers = max_workers

        # 进度统计
        self.total = 0
        self.completed = 0
        self.success_count = 0
        self.skip_count = 0
        self.fail_count = 0
        self.lock = threading.Lock()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(3),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    def check_apk_repeat(self, apk_path, file_name):
        """检查 APK 是否已上传过（失败自动重试）"""
        with open(apk_path, "rb") as f:
            md5_digest = hashlib.md5(f.read()).hexdigest()

        check_url = f"{self.base_url}/appops/app/checkAppRepeat/{md5_digest}/0"
        params = {"t": int(time.time() * 1000), "appName": file_name, "embedWkSdk": '1'}

        resp = self.client.get(check_url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    def upload_single_apk(self, apk_path, app_name):
        """上传单个 APK 文件（失败自动重试 3 次）"""
        upload_url = f"{self.base_url}/appops/app/upload?t={int(time.time() * 1000)}"

        with open(apk_path, "rb") as apk_file:
            files = {
                "file": (apk_path, apk_file.read(), 'application/vnd.android.package-archive'),
                "appName": (None, app_name),
                "remark": (None, ""),
                "embedWkSdk": (None, "0"),
                "originalAppName": (None, app_name),
                "moduleId": (None, "0")
            }
            print(f"正在上传:{app_name}")
            upload_resp = self.client.post(upload_url, files=files, timeout=500)
            if upload_resp.status_code == 200 and upload_resp.text != "-1":
                return True
            else:
                print(f"❌上传失败：{apk_path} - {app_name} - 上传失败({upload_resp.status_code})：{upload_resp.text}")
                raise httpx.RequestError(f"上传失败({upload_resp.status_code})：{upload_resp.text}")

    def _update_progress(self, status_icon, msg):
        """线程安全地更新进度"""
        with self.lock:
            self.completed += 1
            current = self.completed
            total = self.total
            print(f"[{current}/{total}] {status_icon} {msg}")

    def process_apk(self, file_name):
        """单个 APK 的完整处理流程"""
        apk_path = os.path.join(self.apk_dir, file_name)
        app_name = get_apk_name(apk_path)
        if not app_name:
            self._update_progress("⚠️", f"{file_name} 无法解析名称，跳过。")
            self.fail_count += 1
            return

        try:
            json_response = self.check_apk_repeat(apk_path, file_name)
        except Exception as e:
            self._update_progress("❌", f"{app_name} 检查重复失败: {e}")
            self.fail_count += 1
            return

        if not json_response:
            self._update_progress("⚠️", f"{app_name} 检查结果为空，跳过。")
            self.fail_count += 1
            return

        if json_response.get('success', False):
            try:
                self.upload_single_apk(apk_path, app_name)
                self._update_progress("✅", f"上传成功：{app_name}")
                self.success_count += 1
            except Exception as e:
                self._update_progress("❌", f"上传失败：{apk_path} - {app_name} - {e}")
                self.fail_count += 1
        else:
            self._update_progress("⏩", f"{app_name} 已存在，跳过。")
            self.skip_count += 1

    def upload_apk(self):
        """并发上传 APK 文件（带进度显示）"""
        apk_files = [f for f in os.listdir(self.apk_dir) if f.endswith(".apk")]
        if not apk_files:
            print("⚠️ 未找到任何 APK 文件。")
            return

        self.total = len(apk_files)
        print(f"📦 共发现 {self.total} 个 APK 文件，开始并发上传...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.process_apk, file_name): file_name for file_name in apk_files}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    file_name = futures[future]
                    self._update_progress("❌", f"{file_name} 执行异常: {e}")
                    self.fail_count += 1

        print("\n🎉 全部处理完成！")
        print(f"✅ 成功：{self.success_count}")
        print(f"⏩ 跳过：{self.skip_count}")
        print(f"❌ 失败：{self.fail_count}")


if __name__ == '__main__':
    apk_folder = "launch_time/apks"  # 你的 APK 文件夹路径

    base_url = "https://wukong1.tingyun.com"  # base_url（不带斜杠）
    cookie = "JSESSIONID=22EC905403ADC718A46A3CA449CB2E59; wk_appopsweb_uid=eb842f664856db23e78d372401827285631d3f9d; wk_uid=b2a1680cd495ef256826f2ff4dc3ca3ba24f0dab; wk_appops-cloudmanager-web_uid=af4e2503efa60a75371ccd12caeae057e1341696; CASTGC=TGT-324295-keYsuq9f4JuodfMbJkRsOGvGWlInSyTXJdjtql1D2yPGxfSa9K-account.tingyun.com"  # 登录后的 cookie

    manager = AibApkManager(apk_folder, base_url, cookie)
    # manager.upload_apk()
    manager.process_apk("com.csii.mobile.iap.bodl.apk")

    # name = get_apk_name("launch_time/apks/com.csii.tiannongshang.mobilebank.apk")
    # print(name)
