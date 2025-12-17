#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/12/10
 @Author : wwf
 Description: 
"""
import random
import time

import pandas as pd
import requests
from datetime import datetime


def time2date(timestamp):
    # 转换为秒（因为Python的datetime.fromtimestamp()需要秒为单位）
    timestamp_seconds = timestamp / 1000

    # 转换为datetime对象
    dt = datetime.fromtimestamp(timestamp_seconds)

    # 格式化为字符串
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def dates():
    # 使用pandas的date_range，注意需要指定负频率
    start_date = "2024-02-22"
    end_date = "2023-12-01"

    # 生成日期范围（注意：pandas不支持直接反向range，需要先正向再反转）
    date_range = pd.date_range(end=start_date, start=end_date, freq='D')[::-1]


    # for date in date_range:
    #     print(date.strftime("%Y-%m-%d"))
    #
    # print(f"\n总天数: {len(date_range)}")
    return date_range


session = requests.Session()

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://bf2bmc.cc/player/result",
    "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"macOS\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
}
cookies = {
    "_locale_": "zh_CN",
    "affid": "null",
    "ssid1": "ce36f8983cf564fde48293648e61d52f",
    "random": "3059",
    "token": "362b5a5ddb86b299a6d50dc2a11940dd55d676f6"
}
session.headers.update(headers)
session.cookies.update(cookies)


def main(date):
    time.sleep(random.randint(1, 3))
    url = "https://bf2bmc.cc/web/rest/member/dresult"
    # 23年12月1
    params = {
        "date": date,
        "lottery": "AULUCKY10",
        "page": "1"
    }
    response = session.get(url, headers=headers, cookies=cookies, params=params)
    response.raise_for_status()
    result = response.json()
    result_datas = []
    if result["statusCode"] == 200:

        datas = result["result"]["list"]
        for data in datas:
            b_values_int = [int(data["map"][f"B{i}"]) for i in range(1, 11)]
            # "开奖结果": data["result"],
            mapping = {
                "D": "大",
                "X": "小"
            }
            GDX = data["map"]["GDX"]
            GDX_ = mapping.get(GDX, GDX)

            mapping = {
                "D": "单",
                "S": "双"
            }
            GDS = data["map"]["GDS"]
            GDS_ = mapping.get(GDS, GDS)
            # print(
            #     f'期数:{data["drawNumber"]},开奖时间：{time2date(data["drawTime"])},开奖号码：{b_values_int},冠亚军和：{data["map"]["GYH"]},{GDX_},{GDS_}')
            result_datas.append({
                "期数": data["drawNumber"],
                "开奖时间": time2date(data["drawTime"]),
                "号码": data["map"]["GYH"],
                "单、双": GDS_,
                "大、小": GDX_,
                "号码1": b_values_int[0],
                "号码2": b_values_int[1],
                "号码3": b_values_int[2],
                "号码4": b_values_int[3],
                "号码5": b_values_int[4],
                "号码6": b_values_int[5],
                "号码7": b_values_int[6],
                "号码8": b_values_int[7],
                "号码9": b_values_int[8],
                "号码10": b_values_int[9],
            })
        return result_datas
    else:
        print(result.text)
        raise Exception("result[statusCode 不等于200")


if __name__ == '__main__':
    result_datas = []
    try:
        for date in dates():
            d_data = date.strftime("%Y-%m-%d")
            print(d_data)
            result_datas.extend(main(d_data))
    except Exception as e:
        print(e)
    finally:
        # 4. 创建DataFrame
        df = pd.DataFrame(result_datas)

        # 5. 保存到Excel
        df.to_excel("开奖数据.xlsx", index=False)
        print("数据已保存到 开奖数据.xlsx")
