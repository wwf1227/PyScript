#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Time : 2025/10/12
@Author : wwf
Description:
"""
import json
import os
from datetime import datetime

import requests


class FeishuSheetOperator:
    def __init__(self, start, end):
        # 在实际使用时，需要替换为有效的飞书API凭证
        self.APP_ID = "cli_a8626aa5e47e101c"
        self.APP_SECRET = "14AXuQE5vqK4Z75FOBVvzcJaUCtTVCR5"
        self.TOKEN_CACHE_FILE = "data/feishu_token_cache.json"
        self.headers = {}
        self.base_url = "https://open.feishu.cn"
        self.start_row = start
        self.end_row = end
        self.table_name = "MpdWs2EGshjQXbtJKrccT6xbnOb"
        self.sheet_name = "wlmPUI"
        self.get_tenant_access_token()

    def get_tenant_access_token(self):
        # 尝试从缓存读取token
        if os.path.exists(self.TOKEN_CACHE_FILE):
            try:
                with open(self.TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
                    if "token" in cache and "expire_time" in cache:
                        # 检查token是否在有效期内（提前10分钟过期）
                        if datetime.now().timestamp() < cache["expire_time"] - 600:
                            self.headers["Authorization"] = f"Bearer {cache['token']}"
                            return cache["token"]
            except:
                pass
        else:
            # 创建缓存文件
            os.makedirs(os.path.dirname(self.TOKEN_CACHE_FILE), exist_ok=True)

        # 重新获取token
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
        }
        data = {"app_id": self.APP_ID, "app_secret": self.APP_SECRET}

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            result = response.json()
            if result["code"] == 0:
                token = result["tenant_access_token"]
                expire_time = datetime.now().timestamp() + result["expire"]

                # 缓存token
                with open(self.TOKEN_CACHE_FILE, "w") as f:
                    json.dump({"token": token, "expire_time": expire_time}, f)

                self.headers["Authorization"] = f"Bearer {token}"
                self.headers["Content-Type"] = "application/json; charset=utf-8"
                
                return token
        
        raise Exception(f"Failed to get tenant_access_token: {response.text}")

    def sheet_value(self):
        try:
            params = {
                "valueRenderOption": "ToString",
                # 'valueRenderOption': 'Formula',
                "dateTimeRenderOption": "FormattedString",
            }

            response = requests.get(
                f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{self.table_name}/values/{self.sheet_name}!F{self.start_row}:F{self.end_row}",
                params=params,
                headers=self.headers,
            )
            
            if response.status_code != 200:
                print(response.text)
                # if response.json()['code'] == 99991663:
                #     token = get_token()
                #     if token:
                #         headers['Authorization'] = 'Bearer {}'.format(token)
                #         sheet_value()
                # else:
                raise Exception("响应状态码异常！")

            if response.json()["code"] == 0:
                res = response.json()["data"]["valueRange"]["values"]
                return res

        except Exception as e:
            print(e)

    def write_img_to_excel(self, image_url, range):
        # image_url A6:A6
        # 写入图片
        import base64
        
        print(f"开始下载图片：{image_url}")
        response = requests.get(
            image_url,
            headers={
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
            },
        )

        # 确保图片下载成功
        if response.status_code == 200:
            # 获取图片的二进制数据
            fb = response.content

            # 处理 Base64 编码的填充
            misssing_padding = 4 - len(fb) % 4
            if misssing_padding:
                fb += b"=" * misssing_padding

            # Base64 编码
            fb = base64.b64encode(fb).decode("utf-8")

            # 构建请求数据字典
            data = {
                "range": f"{self.sheet_name}!{range}",  # 可替换为实际的范围
                "image": fb,  # Base64 编码后的图片数据
                "name": "a.png",  # 图片名称
            }

            print(f"图片数据长度：{len(fb)},开始上传图片...")
            # 输出请求数据
            # print(data)
            response = requests.post(
                f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{self.table_name}/values_image",
                headers=self.headers,
                json=data,
            )
            if response.status_code != 200:
                print(f"上传失败：{data['range']}")
            # print(response.text)
        else:
            print(f"图片下载失败，错误代码：{response.status_code}")
            print(response.headers)

    def run(self):
        res = self.sheet_value()
        if res is not None:
            for idx, r in enumerate(res):
                print(f"{idx + self.start_row}-->{r[0]}")
                if r[0] is not None and "http" in r[0]:
                    img_url = r[0]
                    if r[0].startswith('["'):
                        img_url = json.loads(r[0])[0]
                    index = idx + self.start_row
                    self.write_img_to_excel(img_url, f"G{index}:G{index}")


if __name__ == "__main__":
    start = 1262
    end = 1510
    FeishuSheetOperator(start, end).run()
