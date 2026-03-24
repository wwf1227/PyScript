#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/11/12
 @Author : wwf
 Description: 
"""
import os
import time
import hashlib
import asyncio
import aiofiles
import subprocess
import shutil
import httpx
from tqdm.asyncio import tqdm_asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type


# ----------------------------
# 同步 aapt 解析函数（在异步中包装运行）
# ----------------------------
def get_apk_name_sync(apk_path):
    """使用 aapt 获取 APK 的应用名称"""
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
                app_name = line.split(":", 1)[1].strip().strip("'")
                return app_name
    except Exception as e:
        print(f"⚠️ 解析 APK 名称失败: {e}")
    return None


# ----------------------------
# 主类定义
# ----------------------------
class AsyncAibApkManager:
    def __init__(self, apk_dir, base_url, cookie, concurrency=6):
        self.apk_dir = os.path.abspath(apk_dir)
        self.base_url = base_url.rstrip('/')
        self.headers = {"Cookie": cookie}
        self.semaphore = asyncio.Semaphore(concurrency)
        self.success_count = 0
        self.skip_count = 0
        self.fail_count = 0
        self.lock = asyncio.Lock()  # 异步锁

    # ----------------------------
    # 检查是否重复上传
    # ----------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(3),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    async def check_apk_repeat(self, client: httpx.AsyncClient, apk_path, file_name):
        async with aiofiles.open(apk_path, "rb") as f:
            content = await f.read()
        md5_digest = hashlib.md5(content).hexdigest()

        check_url = f"{self.base_url}/appops/app/checkAppRepeat/{md5_digest}/0"
        params = {
            "t": int(time.time() * 1000),
            "appName": file_name,
            "embedWkSdk": "1"
        }

        resp = await client.get(check_url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    # ----------------------------
    # 上传单个 APK
    # ----------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    async def upload_single_apk(self, client: httpx.AsyncClient, apk_path, app_name):
        upload_url = f"{self.base_url}/appops/app/upload?t={int(time.time() * 1000)}"
        async with aiofiles.open(apk_path, "rb") as f:
            content = await f.read()

        files = {
            "file": (os.path.basename(apk_path), content, "application/vnd.android.package-archive"),
            "appName": (None, app_name),
            "remark": (None, ""),
            "embedWkSdk": (None, "0"),
            "originalAppName": (None, app_name),
            "moduleId": (None, "0"),
        }

        resp = await client.post(upload_url, files=files, timeout=600)
        if resp.status_code == 200 and resp.text != "-1":
            return True
        else:
            raise httpx.RequestError(f"上传失败({resp.status_code})：{resp.text}")

    # ----------------------------
    # 处理单个 APK 的上传逻辑
    # ----------------------------
    async def process_apk(self, client, file_name, progress):
        apk_path = os.path.join(self.apk_dir, file_name)
        # 使用线程池运行同步 aapt
        app_name = await asyncio.to_thread(get_apk_name_sync, apk_path)
        if not app_name:
            async with self.lock:
                self.fail_count += 1
            progress.set_description(f"⚠️ 无法解析：{file_name}")
            progress.update(1)
            return

        async with self.semaphore:
            try:
                json_response = await self.check_apk_repeat(client, apk_path, file_name)
                if json_response.get("success", False):
                    progress.write(f"⬆️ 正在上传：{app_name}")
                    await self.upload_single_apk(client, apk_path, app_name)
                    async with self.lock:
                        self.success_count += 1
                    progress.set_description(f"✅ 上传成功：{app_name}")
                else:
                    async with self.lock:
                        self.skip_count += 1
                    progress.set_description(f"⏩ 已存在：{app_name}")
            except Exception as e:
                async with self.lock:
                    self.fail_count += 1
                progress.set_description(f"❌ {app_name} 失败: {e}")
            finally:
                progress.update(1)

    # ----------------------------
    # 主上传入口
    # ----------------------------
    async def upload_all(self):
        apk_files = [f for f in os.listdir(self.apk_dir) if f.endswith(".apk")]
        if not apk_files:
            print("⚠️ 未找到任何 APK 文件。")
            return

        print(f"📦 共发现 {len(apk_files)} 个 APK 文件，开始并发上传...")

        async with httpx.AsyncClient(headers=self.headers) as client:
            with tqdm_asyncio(total=len(apk_files), desc="上传进度") as progress:
                tasks = [
                    asyncio.create_task(self.process_apk(client, file_name, progress))
                    for file_name in apk_files
                ]
                await asyncio.gather(*tasks)

        print("\n🎉 全部处理完成！")
        print(f"✅ 成功：{self.success_count}")
        print(f"⏩ 跳过：{self.skip_count}")
        print(f"❌ 失败：{self.fail_count}")


if __name__ == '__main__':
    apk_folder = os.path.join(os.path.dirname(__file__), "launch_time/apks")
    base_url = "https://wukong1.tingyun.com"  # base_url（不带斜杠）
    cookie = "JSESSIONID=22EC905403ADC718A46A3CA449CB2E59; wk_appopsweb_uid=eb842f664856db23e78d372401827285631d3f9d; wk_uid=b2a1680cd495ef256826f2ff4dc3ca3ba24f0dab; wk_appops-cloudmanager-web_uid=af4e2503efa60a75371ccd12caeae057e1341696; CASTGC=TGT-324295-keYsuq9f4JuodfMbJkRsOGvGWlInSyTXJdjtql1D2yPGxfSa9K-account.tingyun.com"  # 登录后的 cookie

    manager = AsyncAibApkManager(apk_folder, base_url, cookie)
    asyncio.run(manager.upload_all())

    # name = get_apk_name("launch_time/apks/com.csii.tiannongshang.mobilebank.apk")
    # print(name)
