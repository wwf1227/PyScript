#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import re
import time
import requests


URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)


def normalize_url(url: str) -> str:
    """清洗URL尾部垃圾字符"""
    return url.strip().strip(
        '.,;:!?)>"\'）】》]'
    )


def extract_urls(text, unique=True):
    """稳定URL提取"""

    # ⭐ 防止换行影响
    text = text.replace('\n', ' ')

    raw = URL_RE.findall(text)
    urls = [normalize_url(u) for u in raw]

    if unique:
        urls = list(dict.fromkeys(urls))

    return urls


def page_contains_keyword(url, keyword, timeout=10):
    """请求网页检测关键字"""

    try:
        time.sleep(random.randint(1,3))
        r = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent":
                "Mozilla/5.0"
            }
        )

        r.encoding = r.apparent_encoding

        return keyword in r.text

    except Exception as e:
        print("请求失败:", url, e)
        return False


def check_urls(urls, keyword):
    """批量检测"""
    hit = []

    for i, u in enumerate(urls, 1):
        print(f"检测({i}/{len(urls)}):", u)

        if page_contains_keyword(u, keyword):
            print("  ✅ 命中")
            hit.append(u)
        else:
            print("  ❌ 未命中")

    return hit


if __name__ == "__main__":

    text = """
题为：换季皮肤过敏，哪些修护面霜品牌比较好？
2026-03-20 07:59:04: 第1遍结果:https://www.doubao.com/thread/a1992bd6104fb
2026-03-20 07:59:04: 第2遍结果:https://www.doubao.com/thread/a7b9566a0c52a
2026-03-20 07:59:04: 第3遍结果:https://www.doubao.com/thread/a65ea942d8619
2026-03-20 07:59:04: 第4遍结果:https://www.doubao.com/thread/abf5a80adc3cb
2026-03-20 07:59:04: 第5遍结果:https://www.doubao.com/thread/aa39600a7e971
2026-03-20 07:59:04: 等待：4000
    """

    urls = extract_urls(text)

    print("\n⭐ 共提取 URL 数量:", len(urls))
    print("=" * 60)

    for u in urls:
        print(u)

    print("\n⭐ 开始检测网页内容")
    print("=" * 60)

    keyword = "完成思考"

    hit_urls = check_urls(urls, keyword)

    print("\n⭐ 命中关键字的 URL 数量:", len(hit_urls))
    print("=" * 60)

    for u in hit_urls:
        print(u)