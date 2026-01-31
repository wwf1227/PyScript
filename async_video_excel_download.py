#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/10/11
 @Author : wwf
 Description: 
"""
import os
import asyncio
import time

import httpx
import pandas as pd
from termcolor import colored
from tqdm import tqdm
from httpx import Limits, Timeout
from tenacity import retry, stop_after_attempt, wait_fixed


# 异步日志输出
def log_exception(exception_message):
    """捕获异常并以红色打印"""
    print(colored(f"ERROR: {exception_message}", "red"))


# 错误重试装饰器，使用 tenacity 来实现重试机制
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def download_video(client: httpx.AsyncClient, url: str, save_path: str):
    try:
        # 发起异步请求
        response = await client.get(url)

        # 检查请求是否成功
        if response.status_code != 200:
            raise Exception(f"Failed to download video: {url} - Status code: {response.status_code}")

        # 保存视频到文件
        with open(save_path, 'wb') as file:
            file.write(response.content)
        print(f"视频已保存: {save_path}")
    except Exception as e:
        log_exception(str(e))
        raise e  # 重新抛出异常，确保重试机制生效


# 读取Excel并异步下载视频
async def download_videos_from_excel(excel_path: str, download_folder: str, specified_sheet: str = None):
    # 读取Excel文件中的所有sheet
    xls = pd.ExcelFile(excel_path)

    # 创建下载文件夹（如果不存在）
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # 设置并发限制（最大连接数）
    limits = Limits(max_connections=10)  # 每个主机最多10个连接

    # 设置请求超时（连接超时为5秒，整体请求超时为10秒）
    timeout = Timeout(10.0, connect=5.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"}
    # 创建异步HTTP客户端
    async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True, headers=headers) as client:
        tasks = []

        # 如果指定了sheet名，则只处理指定的sheet
        sheets_to_process = [specified_sheet] if specified_sheet else xls.sheet_names

        # 遍历所有需要处理的sheet
        for sheet_name in sheets_to_process:
            print(f"正在处理工作表: {sheet_name}")
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            video_links = df['视频链接'].dropna()  # 假设Excel列名为 '视频链接'

            # 为每个sheet创建独立的文件夹
            sheet_folder = os.path.join(download_folder, sheet_name)
            if not os.path.exists(sheet_folder):
                os.makedirs(sheet_folder)

            # 从1.mp4开始命名
            current_file_index = 1

            # 下载视频
            for idx, url in enumerate(video_links):
                if isinstance(url, str) and url.startswith('http'):
                    # 累加数字命名文件
                    video_name = f"{current_file_index}.mp4"
                    video_path = os.path.join(sheet_folder, video_name)
                    tasks.append(download_video(client, url, video_path))
                    current_file_index += 1  # 文件名编号递增
                    if current_file_index > 5:
                        break

        # 使用 tqdm 显示进度条
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="下载视频"):
            await future


def main():
    # Excel文件路径和下载目录
    excel_path = 'video.xlsx'  # 替换为实际路径
    download_folder = 'datas'  # 替换为你想保存视频的文件夹路径

    # 选择要下载的sheet名称。如果不指定，则会处理所有sheet。
    specified_sheet = None  # 可以设置为特定的sheet名称，例：'Sheet1'
    # 启动异步下载
    asyncio.run(download_videos_from_excel(excel_path, download_folder, specified_sheet))


if __name__ == "__main__":
    start = time.time()
    main()
    total = time.time() - start
    print(f"总耗时：{total}")
