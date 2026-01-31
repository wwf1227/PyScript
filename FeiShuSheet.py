#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/10/10
 @Author : wwf
 Description: 
"""
import time
from datetime import datetime
import json
import os

import requests
from requests_toolbelt import MultipartEncoder


class FeishuSheetOperator:
    def __init__(self):
        # 在实际使用时，需要替换为有效的飞书API凭证
        self.APP_ID = "cli_a8626aa5e47e101c"
        self.APP_SECRET = "14AXuQE5vqK4Z75FOBVvzcJaUCtTVCR5"
        self.TOKEN_CACHE_FILE = "data/files/feishu_token_cache.json"
        self.headers = {}
        self.base_url = "https://open.feishu.cn"

    def get_tenant_access_token(self):
        # 尝试从缓存读取token
        if os.path.exists(self.TOKEN_CACHE_FILE):
            try:
                with open(self.TOKEN_CACHE_FILE, 'r') as f:
                    cache = json.load(f)
                    if 'token' in cache and 'expire_time' in cache:
                        # 检查token是否在有效期内（提前10分钟过期）
                        if datetime.now().timestamp() < cache['expire_time'] - 600:
                            self.headers['Authorization'] = f"Bearer {cache['token']}"
                            return cache['token']
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
        data = {
            "app_id": self.APP_ID,
            "app_secret": self.APP_SECRET
        }

        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            if result['code'] == 0:
                token = result['tenant_access_token']
                expire_time = datetime.now().timestamp() + result['expire']

                # 缓存token
                with open(self.TOKEN_CACHE_FILE, 'w') as f:
                    json.dump({
                        'token': token,
                        'expire_time': expire_time
                    }, f)

                self.headers['Authorization'] = f"Bearer {token}"
                return token

        raise Exception(f"Failed to get tenant_access_token: {response.text}")

    def get_sheet_data(self, spreadsheet_token, sheet_id=None):
        """获取表格数据"""
        url = f"{self.base_url}/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/"
        if sheet_id:
            url += sheet_id

        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to get sheet data: {response.text}")

    def download_image(self, image_url, save_path):
        """下载图片"""
        try:
            response = requests.get(image_url, stream=True)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=128):
                        f.write(chunk)
                print(f"Image downloaded: {save_path}")
                return True
            else:
                print(f"Failed to download image from {image_url}")
                return False
        except Exception as e:
            print(f"Error downloading image: {e}")
            return False

    def upload_image(self, image_path):
        """上传图片到飞书"""
        # 第一步：获取上传凭证
        url = f"{self.base_url}/open-apis/im/v1/images/upload"
        headers = {
            **self.headers,
            "Content-Type": "multipart/form-data"
        }

        # 从文件名获取文件类型
        file_ext = os.path.splitext(image_path)[1].lower()[1:]  # 获取扩展名并去除点号
        content_type_map = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'bmp': 'image/bmp'
        }
        content_type = content_type_map.get(file_ext, 'application/octet-stream')

        try:
            with open(image_path, 'rb') as f:
                files = {
                    'image': (os.path.basename(image_path), f, content_type)
                }
                data = {
                    'image_type': 'message'
                }

                response = requests.post(url, headers=headers, files=files, data=data)

            if response.status_code == 200:
                result = response.json()
                if result['code'] == 0:
                    return result['data']['image_key']

            print(f"Failed to upload image: {response.text}")
            return None
        except Exception as e:
            print(f"Error uploading image: {e}")
            return None

    def upload_video(self, spreadsheet_token, file_path):
        # 文件限制：单文件≤20MB（超20MB需使用分片上传API）
        url = f"{self.base_url}/open-apis/drive/v1/medias/upload_all"
        file_size = os.path.getsize(file_path)

        form = MultipartEncoder(
            fields={
                "file_name": "demo.mp4",
                "parent_type": "sheet_file",  # 表格文件类型
                "parent_node": spreadsheet_token,  # 表格token
                "size": str(file_size),
                "file": ("demo.mp4", open(file_path, "rb"), "video/mp4")
            }
        )

        self.headers['Content-Type'] = form.content_type

        response = requests.post(url, headers=self.headers, data=form)
        response.raise_for_status()
        # {"code":0,"data":{"file_token":"XEc7bH7XcoMoJExlOERc5iEFnGg"},"msg":"Success"}
        return response.json()["data"]["file_token"]  # 返回视频文件token

    def upload_cell_with_video(self, spreadsheet_token, file_token, range_="Sheet1!A1:A1"):
        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values"

        payload = {
            "valueRange": {
                "range": range_,
                "values": [
                    [{"type": "file", "fileToken": file_token}]
                ]
            }
        }

        self.headers = {
            "Content-Type": "application/json"
        }

        return requests.put(url, json=payload, headers=self.headers)

    def update_cell_with_image(self, spreadsheet_token, sheet_id, range_, image_key):
        """更新表格单元格，插入图片"""
        url = f"{self.base_url}/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/cells/image"
        data = {
            "requests": [
                {
                    "insert_image": {
                        "range": {
                            "sheet_id": sheet_id,
                            "range": range_
                        },
                        "image_key": image_key,
                        "image_size": {
                            "width": 300,
                            "height": 200
                        }
                    }
                }
            ]
        }

        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code == 200:
            result = response.json()
            if result['code'] == 0:
                return True

        print(f"Failed to update cell with image: {response.text}")
        return False

    def process_sheet_links(self, spreadsheet_token, sheet_id, link_column, image_column):
        """处理表格中的链接，下载图片并更新表格"""
        # 获取表格数据
        sheet_data = self.get_sheet_data(spreadsheet_token, sheet_id)

        # 创建临时目录存放下载的图片
        temp_dir = "/app/data/files/temp_images"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # 处理每一行数据
        if 'data' in sheet_data and 'value_range' in sheet_data['data'] and 'values' in sheet_data['data'][
            'value_range']:
            values = sheet_data['data']['value_range']['values']
            headers = values[0]  # 假设第一行是表头

            # 查找链接列和图片列的索引
            link_col_index = -1
            image_col_index = -1

            for i, header in enumerate(headers):
                if header == link_column:
                    link_col_index = i
                elif header == image_column:
                    image_col_index = i

            if link_col_index == -1:
                print(f"Link column '{link_column}' not found in headers")
                return

            if image_col_index == -1:
                print(f"Image column '{image_column}' not found in headers")
                return

            # 处理每行数据
            for row_idx, row in enumerate(values[1:], 2):  # 从第二行开始处理数据行
                if len(row) > link_col_index and row[link_col_index]:
                    link_value = row[link_col_index]
                    # 检查是否是有效的URL
                    if isinstance(link_value, str) and (
                            link_value.startswith('http://') or link_value.startswith('https://')):
                        print(f"Processing link in row {row_idx}: {link_value}")

                        # 下载图片
                        image_filename = f"image_row_{row_idx}_{int(time.time())}.jpg"
                        image_path = os.path.join(temp_dir, image_filename)

                        if self.download_image(link_value, image_path):
                            # 上传图片到飞书
                            image_key = self.upload_image(image_path)

                            if image_key:
                                # 构建单元格范围，例如 "A2"
                                col_letter = chr(65 + image_col_index)  # A=65
                                cell_range = f"{col_letter}{row_idx}"

                                # 更新表格单元格
                                if self.update_cell_with_image(spreadsheet_token, sheet_id, cell_range, image_key):
                                    print(f"Successfully updated cell {cell_range} with image")

                            # 清理临时文件
                            if os.path.exists(image_path):
                                os.remove(image_path)
                    else:
                        print(f"Not a valid URL in row {row_idx}: {link_value}")

        # 清理临时目录
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                pass


# if __name__ == "__main__":
#     feishu = FeishuSheetOperator()
#     spreadsheet_token = "MpdWs2EGshjQXbtJKrccT6xbnOb"
#     tenant_access_token = feishu.get_tenant_access_token()
#     print(tenant_access_token)
#     print(feishu.headers)
# https://ci7xdvsfgai.feishu.cn/sheets/MpdWs2EGshjQXbtJKrccT6xbnOb?sheet=wlmPUI
# print(feishu.get_sheet_data("MpdWs2EGshjQXbtJKrccT6xbnOb", "wlmPUI"))
# file_token = feishu.upload_video(spreadsheet_token, "/Users/wwf/Downloads/445b6ebb9f753f67c679077e756960d0.mp4")
# print(file_token) # EtWbbPYIFoTs8wxkQiXcvR6qnFg

# print(feishu.upload_cell_with_video(spreadsheet_token, "EtWbbPYIFoTs8wxkQiXcvR6qnFg", range_="wlmPUI!A2:A2"))

# headers = {
#     'Authorization': 'Bearer t-g104c4iiIRGHA63SPTNVUCXWIWQWBVACZDEDOVA4',
#     'Content-Type': 'application/json; charset=utf-8'
# }

# response = requests.get('https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/WLdfsfZ16hTZaAt0NyqcWK0UnGg', headers=headers)
# print(response.text)
# {"code":0,"data":{"spreadsheet":{"owner_id":"ou_aab68001356844f7e3b22a85f4a5dfc4","title":"test1","token":"WLdfsfZ16hTZaAt0NyqcWK0UnGg","url":"https://ci7xdvsfgai.feishu.cn/sheets/WLdfsfZ16hTZaAt0NyqcWK0UnGg"}},"msg":""}


# 获取工作表
# response = requests.get('https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/VRqDsOQGRhbN6jtWNdecTmnynSf/sheets/query', headers=headers)
# print(response.text)
# {"code":0,"data":{"sheets":[{"grid_properties":{"column_count":20,"frozen_column_count":0,"frozen_row_count":0,"row_count":200},"hidden":false,"index":0,"resource_type":"sheet","sheet_id":"5d75d8","title":"Sheet1"}]},"msg":"success"}

# 查询工作表
# response = requests.get("https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/VRqDsOQGRhbN6jtWNdecTmnynSf/sheets/6fc11d",headers=headers)
# print(response.text)
# {"code":0,"data":{"sheet":{"grid_properties":{"column_count":20,"frozen_column_count":0,"frozen_row_count":0,"row_count":200},"hidden":false,"index":0,"resource_type":"sheet","sheet_id":"5d75d8","title":"Sheet1"}},"msg":"success"}


# 查询单个范围
params = {
    'valueRenderOption': 'ToString',
    # 'valueRenderOption': 'Formula',
    'dateTimeRenderOption': 'FormattedString',
}

headers = {
    'Authorization': 'Bearer t-g1041vgTYEBZXZAM63VQHUX266HNALICQXS6A465',
    'Content-Type': 'application/json; charset=utf-8'
}
response = requests.get(
    'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/MpdWs2EGshjQXbtJKrccT6xbnOb/values/wlmPUI!F2:G7',
    params=params,
    headers=headers,
)
print(response.text)
# {"code":0,"data":{"revision":5,"spreadsheetToken":"VRqDsOQGRhbN6jtWNdecTmnynSf","valueRange":{"majorDimension":"ROWS","range":"6fc11d!F2:G7","revision":5,"values":[["[\"https://usergrowth.com.cn/mago_ai/api/upload/getImg/view?Uri=adsources-console/ddd81c1c-0d81-4efa-bd2a-a268b20e6f03\"]",null],["[\"https://usergrowth.com.cn/mago_ai/api/upload/getImg/view?Uri=adsources-console/2f6be222-9133-4528-b9ab-1c384601b75c\"]",null],["[\"https://usergrowth.com.cn/mago_ai/api/upload/getImg/view?Uri=adsources-console/0f310612-b085-409e-927c-1eb81487caaf\"]",null],["[\"https://usergrowth.com.cn/mago_ai/api/upload/getImg/view?Uri=adsources-console/2a233e78-611a-4937-94d2-3088950b4cac\"]",null],[null,null],[null,null]]}},"msg":"success"}


# 写入数据
json_data = {
    'valueRange': {
        'range': 'wlmPUI!A5:A5',
        'values': [
            [
                'WOSHI  通过脚本更新的',
            ]
        ],
    },
}


# response = requests.put(
#     'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/MpdWs2EGshjQXbtJKrccT6xbnOb/values',
#     headers={'Authorization': 'Bearer t-g104c4kaVSPDVLDJF5NGXLTIXGRIQWARQ75IUSSJ', "Content-Type": "application/json"},
#     json=json_data,
# )
# print(response.text)


# 获取文件下载
# headers = {
#     "Authorization": "Bearer t-g104c4kaVSPDVLDJF5NGXLTIXGRIQWARQ75IUSSJ"
# }
# url = "https://open.feishu.cn/open-apis/drive/v1/files/EtWbbPYIFoTs8wxkQiXcvR6qnFg/download"
# response = requests.get(url, headers=headers)

# print(response.text)
# print(response)

# 写入图片
# import base64
#
# # 下载图片
# image_url = "https://usergrowth.com.cn/mago_ai/api/upload/getImg/view?Uri=adsources-console/2a233e78-611a-4937-94d2-3088950b4cac"  # 替换为实际的图片 URL
# response = requests.get(image_url, headers={
#     "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"})
#
# # 确保图片下载成功
# if response.status_code == 200:
#     # 获取图片的二进制数据
#     fb = response.content
#
#     # 处理 Base64 编码的填充
#     misssing_padding = 4 - len(fb) % 4
#     if misssing_padding:
#         fb += b'=' * misssing_padding
#
#     # Base64 编码
#     fb = base64.b64encode(fb).decode('utf-8')
#
#     # 构建请求数据字典
#     data = {
#         'range': '6fc11d!F6:F6',  # 可替换为实际的范围
#         "image": fb,  # Base64 编码后的图片数据
#         "name": "a.png",  # 图片名称
#     }
#
#     # 输出请求数据
#     # print(data)
#     response = requests.post(
#         'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/VRqDsOQGRhbN6jtWNdecTmnynSf/values_image',
#         headers=headers,
#         json=data,
#     )
#     print(response.text)
# else:
#     print(f"图片下载失败，错误代码：{response.status_code}")
#     print(response.headers)


# 写入附件
# 2、将fileToken写入到表格中
# file_path = "/Users/wwf/Downloads/111.mp4"
# file_size = os.path.getsize(file_path)
# json_data = {
#     'valueRange': {
#         'range': '5d75d8!A7:A7',
#         'values': [
#             [
#                 # {
#                 # "fileToken": "XEc7bH7XcoMoJExlOERc5iEFnGg",
#                 # "mimeType": "video/mp4",
#                 # "size": str(file_size),
#                 # "text": "111.mp4",
#                 # "type": "file"
#                 # }
#                 # {
#                 #     "text": "111.mp4",
#                 #     "link": "http://www.dd.com/XEc7bH7XcoMoJExlOERc5iEFnGg",
#                 #     "type": "url"
#                 # }
#             ]
#         ],
#     },
# }

# response = requests.put(
#     'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/WLdfsfZ16hTZaAt0NyqcWK0UnGg/values',
#     headers=headers,
#     json=json_data,
# )
# print(response.text)


# https://wcnuy2f0g7oq.feishu.cn/wiki/ATTcwyFNFiWpCjk0RZ3c8S16nJg?sheet=ac24km
