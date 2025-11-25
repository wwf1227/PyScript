#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/10/11
 @Author : wwf
 Description: 
"""
import os
import sys
import json
import re
import requests
import pandas as pd

session = requests.Session()

header = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
}


def extract_video_id(url):
    # 定义正则表达式，匹配 URL 中的数字 ID
    match = re.search(r'/video/(\d+)', url)
    if match:
        return match.group(1)  # 返回捕获的数字 ID
    else:
        return None  # 如果没有匹配到，返回 None


def extract_url_from_html(html_content):
    """
    直接从HTML内容提取URL
    """
    # 提取_ROUTER_DATA对象
    pattern = r'_ROUTER_DATA\s*=\s*({.*?});'
    match = re.search(pattern, html_content, re.DOTALL)

    try:
        if match:
            router_data = json.loads(match.group(1))
            url = router_data['loaderData']['ugc_video_page']['videoOptions']['url']
            # 处理Unicode转义
            return url.encode('utf-8').decode('unicode_escape')
        return None
    except Exception as e:
        return None


def get_excel_path(excel_filename):
    # 如果是打包后的 .exe 文件，sys._MEIPASS 提供了解压后的临时路径
    if getattr(sys, 'frozen', False):
        # 打包后的 exe 在临时路径中运行
        base_path = sys._MEIPASS
    else:
        # 非打包状态下，直接使用当前脚本路径
        base_path = os.path.dirname(os.path.abspath(__file__))

    # 构造 Excel 文件的完整路径
    excel_path = os.path.join(base_path, excel_filename)
    return excel_path


# 读取Excel表格的函数
def read_excel(file_path):
    try:
        df = pd.read_excel(file_path)
        print("Excel 文件读取成功")
        return df
    except Exception as e:
        print(f"读取 Excel 文件时发生错误: {e}")
        return None


def get_html(url):
    try:
        respose = session.get(url, headers=header)
        respose.raise_for_status()
        return respose.text
    except Exception as e:
        return None


# 下载视频的函数
def download_video(url, save_path):
    try:
        with session.get(url, headers=header, stream=True) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return save_path
    except:
        return None


# 主函数
def main():
    # Excel文件路径
    excel_path = get_excel_path('video.xlsx')  # 替换为你自己的Excel文件路径
    download_folder = get_excel_path('videos')  # 替换为你想保存视频的文件夹路径

    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # 读取Excel表格
    df = read_excel(excel_path)

    # 获取视频链接的列（假设列名为 'Video_URL'，根据实际情况修改列名）
    video_links = df['视频链接'].dropna()

    # 累加器，用于生成视频名称
    video_count = 0

    # 遍历所有视频链接，下载视频
    for url in video_links:
        url = url.strip()
        # 累加数字
        video_count += 1
        video_name = f"{video_count}.mp4"
        video_path = os.path.join(download_folder, video_name)

        # 判断url为汽水音乐
        if url.startswith('https://qishui.douyin.com/'):
            html_content = get_html(url.strip())
            if html_content is None:
                print(f"url:{url} 无法解析，跳过")
                continue
            # print("获取页面内容完成")
            media_url = extract_url_from_html(html_content)
            if media_url is None or media_url == "":
                print(f"url:{url} 无法解析，跳过")
                continue
            print(f"正在下载视频{url}")
            path = download_video(media_url, video_path)
            if path is None:
                print(f"url:{url} 下载失败，跳过，下载地址为：{media_url}")
                continue
            else:
                print(f"url:{url} 下载完成，存储路径：{path}")
        elif url.startswith('http'):
            # 认为该url可以直接下载
            path = download_video(url, video_path)
            if path is None:
                print(f"url:{url} 下载失败，跳过，下载地址为：{url}")
                continue
            else:
                print(f"url:{url} 下载完成，存储路径：{path}")


if __name__ == "__main__":
    main()
