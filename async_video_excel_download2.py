#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/10/11
 @Author : wwf
 Description: 
"""
import json
import os
import asyncio
import re
import time

import httpx
import pandas as pd
from tqdm import tqdm
from httpx import Limits, Timeout
from tenacity import retry, stop_after_attempt, wait_fixed

# 行号：start_line不能小于2
start_line = 2
end_line = 5

timeout = Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

limits = Limits(
    max_connections=20,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
}

# 并发控制，避免任务过多爆内存/文件 IO
semaphore = asyncio.Semaphore(20)

if start_line < 2:
    print("起始行号不能小于2")
    exit(1)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def download_video(client: httpx.AsyncClient, url: str, save_path: str):
    async with semaphore:  # 限制同时下载数量

        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise Exception(f"Failed: {response.status_code} {url}")

            with open(save_path, 'wb') as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)


async def download_qishui(client: httpx.AsyncClient, url: str, save_path: str):
    html_content = await get_html(client, url)
    if html_content is None:
        print(f"url:{url} 无法解析，跳过")
        return

    media_url = extract_url_from_html(html_content)
    if media_url is None or media_url == "":
        print(f"url:{url} 无法解析，跳过")
        return

    await download_video(client, media_url, save_path)


async def download_videos_from_excel(excel_path: str, download_folder: str, specified_sheet: str = None):
    xls = pd.ExcelFile(excel_path)
    os.makedirs(download_folder, exist_ok=True)

    sheets = [specified_sheet] if specified_sheet else xls.sheet_names
    tasks = []

    # *** 只创建一个共享 client，大幅提升性能 ***
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, limits=limits,
                                 cookies=None) as client:
        for sheet_name in sheets:
            print(f"正在处理工作表: {sheet_name}")

            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            video_links = df['video_url'].dropna()

            sheet_folder = os.path.join(download_folder, sheet_name)
            os.makedirs(sheet_folder, exist_ok=True)

            video_links_data = video_links.iloc[start_line - 2:end_line - 1]

            for idx, url in enumerate(video_links_data):
                video_file_name = idx + start_line

                if isinstance(url, str) and url.startswith("http"):
                    video_name = f"{video_file_name}.mp4"
                    video_path = os.path.join(sheet_folder, video_name)
                    if os.path.exists(video_path):
                        continue

                    # 检测平台
                    platform = detect_platform(url)
                    if platform == "unknown":
                        tasks.append(download_video(client, url, video_path))
                    elif platform == "qishui":
                        tasks.append(download_qishui(client, url, video_path))

        # 显示下载进度
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="下载视频"):
            await future


async def get_html(client, url):
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return None


def extract_url_from_html(html_content):
    """
    直接从HTML内容提取URL
    """
    try:
        match = re.search(r'_ROUTER_DATA\s*=\s*({.*?})\s*;', html_content, re.S)
        if not match:
            return None

        json_str = match.group(1)
        router_data = json.loads(json_str)

        url = (
            router_data
            .get("loaderData", {})
            .get("ugc_video_page", {})
            .get("videoOptions", {})
            .get("url")
        )
        if not url:
            return None

        return url.encode("utf-8").decode("unicode_escape")

    except Exception:
        return None


def detect_platform(url):
    """
    检测视频链接所属平台
    返回: platform_name (str)
    """
    url_lower = url.lower()

    # 抖音
    if 'douyin.com' in url_lower or 'v.douyin.com' in url_lower:
        if 'qishui.douyin.com' in url_lower:
            return 'qishui'
        return 'douyin'

    # 快手
    elif 'kuaishou.com' in url_lower or 'v.kuaishou.com' in url_lower:
        return 'kuaishou'

    # 小红书
    elif 'xiaohongshu.com' in url_lower or 'xhslink.com' in url_lower:
        return 'xiaohongshu'

    # # 微信视频号
    # elif 'weixin' in url_lower or 'channels.weixin' in url_lower:
    #     return 'weixin'
    #
    # # Bilibili
    # elif 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
    #     return 'bilibili'
    #
    # # YouTube
    # elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
    #     return 'youtube'

    # 其他平台
    else:
        return 'unknown'


def main():
    start = time.time()

    excel_path = "video.xlsx"
    download_folder = "videos"
    specified_sheet = None

    asyncio.run(download_videos_from_excel(excel_path, download_folder, specified_sheet))

    print(f"总耗时：{time.time() - start}")


if __name__ == "__main__":
    main()
