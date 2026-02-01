#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Time : 2025/10/12
@Author : wwf
Description: 优化版飞书表格图片处理工具（同步版本）
"""
import base64
import json
import os
import time
from datetime import datetime
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FeishuSheetOperator:
    def __init__(self, start, end):
        """
        初始化飞书表格操作器
        
        Args:
            start: 起始行号
            end: 结束行号
        """
        # 在实际使用时，需要替换为有效的飞书API凭证
        self.APP_ID = "cli_a9be44c67238dbc6"
        self.APP_SECRET = "ZJtXV2OVBGPJ1pmQCBF9Me1CsgSeyMqh"
        self.TOKEN_CACHE_FILE = "data/feishu_token_cache.json"
        self.headers = {}
        self.base_url = "https://open.feishu.cn"
        # 读取列
        self.read_column = "F"
        # 写入列
        self.write_column = "B"

        # 行范围
        self.start_row = start
        self.end_row = end
        # 目标表格和工作表
        self.table_name = "GfcUsbunHhotyJteMorcJZJbnye"
        self.sheet_name = "4c55b7"
        
        # 统计信息
        self.success_count = 0
        self.fail_count = 0
        self.skip_count = 0
        
        # 创建带重试机制的session
        self.session = self._create_session()
        
        # 获取token
        self.get_tenant_access_token()

    def _create_session(self) -> requests.Session:
        """创建带有重试机制和超时控制的session"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 总共重试3次
            backoff_factor=1,  # 重试间隔：1秒, 2秒, 4秒
            status_forcelist=[429, 500, 502, 503, 504],  # 这些状态码会触发重试
            allowed_methods=["GET", "POST"]  # 允许GET和POST重试
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    def get_tenant_access_token(self) -> str:
        """获取飞书租户访问令牌（支持缓存）"""
        # 尝试从缓存读取token
        if os.path.exists(self.TOKEN_CACHE_FILE):
            try:
                with open(self.TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
                    if "token" in cache and "expire_time" in cache:
                        # 检查token是否在有效期内（提前10分钟过期）
                        if datetime.now().timestamp() < cache["expire_time"] - 600:
                            self.headers["Authorization"] = f"Bearer {cache['token']}"
                            self.headers["Content-Type"] = "application/json; charset=utf-8"
                            print("✅ 使用缓存的访问令牌")
                            return cache["token"]
            except Exception as e:
                print(f"⚠️  读取token缓存失败: {e}")
        else:
            # 创建缓存文件目录
            os.makedirs(os.path.dirname(self.TOKEN_CACHE_FILE), exist_ok=True)

        # 重新获取token
        print("🔑 正在获取新的访问令牌...")
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
        }
        data = {"app_id": self.APP_ID, "app_secret": self.APP_SECRET}

        try:
            response = self.session.post(url, headers=headers, json=data, timeout=10)
            
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
                    
                    print("✅ 访问令牌获取成功")
                    return token
            
            raise Exception(f"获取token失败: {response.text}")
        except Exception as e:
            raise Exception(f"获取token异常: {e}")

    def sheet_value(self) -> Optional[List]:
        """获取表格数据"""
        try:
            print(f"📊 正在获取表格数据 (行 {self.start_row}-{self.end_row})...")
            
            params = {
                "valueRenderOption": "ToString",
                "dateTimeRenderOption": "FormattedString",
            }

            response = self.session.get(
                f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.table_name}/values/{self.sheet_name}!{self.read_column}{self.start_row}:{self.read_column}{self.end_row}",
                params=params,
                headers=self.headers,
                timeout=30  # 30秒超时
            )
            
            if response.status_code != 200:
                print(f"❌ 获取表格数据失败: {response.text}")
                raise Exception("响应状态码异常！")

            if response.json()["code"] == 0:
                res = response.json()["data"]["valueRange"]["values"]
                print(f"✅ 成功获取 {len(res)} 行数据")
                return res
            else:
                print(f"❌ API返回错误: {response.json()}")
                return None

        except Exception as e:
            print(f"❌ 获取表格数据异常: {e}")
            return None

    def download_image(self, image_url: str, max_retries: int = 3) -> Optional[bytes]:
        """
        下载图片（带重试和超时控制）
        
        Args:
            image_url: 图片URL
            max_retries: 最大重试次数
            
        Returns:
            图片二进制数据，失败返回None
        """
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "accept-encoding": "gzip, deflate, br",
            "referer": image_url.split('/api/')[0] if '/api/' in image_url else image_url,
        }
        
        for attempt in range(max_retries):
            try:
                # 添加超时控制：连接超时10秒，读取超时60秒
                response = self.session.get(
                    image_url,
                    headers=headers,
                    timeout=(10, 60),
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    return response.content
                elif response.status_code == 403:
                    # 403可能是防盗链，尝试不带referer
                    if attempt == 0:
                        headers_no_referer = headers.copy()
                        headers_no_referer.pop('referer', None)
                        response = self.session.get(
                            image_url,
                            headers=headers_no_referer,
                            timeout=(10, 60)
                        )
                        if response.status_code == 200:
                            return response.content
                    
                    print(f"⚠️  图片下载失败 (尝试 {attempt + 1}/{max_retries}): 403 Forbidden")
                else:
                    print(f"⚠️  图片下载失败 (尝试 {attempt + 1}/{max_retries}): 状态码 {response.status_code}")
                    
            except requests.Timeout:
                print(f"⚠️  图片下载超时 (尝试 {attempt + 1}/{max_retries})")
            except requests.RequestException as e:
                print(f"⚠️  图片下载异常 (尝试 {attempt + 1}/{max_retries}): {str(e)[:50]}")
            except Exception as e:
                print(f"⚠️  未知错误 (尝试 {attempt + 1}/{max_retries}): {str(e)[:50]}")
            
            # 重试前等待，使用指数退避
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1秒, 2秒, 4秒
                time.sleep(wait_time)
        
        return None

    def upload_image(self, image_data: bytes, cell_range: str, max_retries: int = 3) -> bool:
        """
        上传图片到单元格（带重试和超时控制）
        
        Args:
            image_data: 图片二进制数据
            cell_range: 单元格范围，如 "G10:G10"
            max_retries: 最大重试次数
            
        Returns:
            是否上传成功
        """
        # Base64 编码
        fb = base64.b64encode(image_data).decode("utf-8")

        # 构建请求数据
        data = {
            "range": f"{self.sheet_name}!{cell_range}",
            "image": fb,
            "name": "image.png",
        }

        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.table_name}/values_image"

        for attempt in range(max_retries):
            try:
                # 上传可能需要较长时间，设置90秒超时
                response = self.session.post(
                    url,
                    headers=self.headers,
                    json=data,
                    timeout=(10, 90)  # 连接10秒，读取90秒
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 0:
                        return True
                    else:
                        print(f"⚠️  上传API错误 (尝试 {attempt + 1}/{max_retries}): {result.get('msg', 'unknown')}")
                else:
                    print(f"⚠️  上传失败 (尝试 {attempt + 1}/{max_retries}): 状态码 {response.status_code}")
                    
            except requests.Timeout:
                print(f"⚠️  上传超时 (尝试 {attempt + 1}/{max_retries}): {cell_range}")
            except requests.RequestException as e:
                print(f"⚠️  上传异常 (尝试 {attempt + 1}/{max_retries}): {str(e)[:50]}")
            except Exception as e:
                print(f"⚠️  未知错误 (尝试 {attempt + 1}/{max_retries}): {str(e)[:50]}")
            
            # 重试前等待
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
        
        return False

    def write_img_to_excel(self, image_url: str, cell_range: str) -> bool:
        """
        下载图片并写入Excel（整合版）
        
        Args:
            image_url: 图片URL
            cell_range: 单元格范围
            
        Returns:
            是否处理成功
        """
        # 下载图片
        # print(f"  📥 下载图片: {image_url[:60]}...")
        image_data = self.download_image(image_url)
        
        if not image_data:
            print(f"  ❌ 图片下载失败")
            return False
        
        # print(f"  ✅ 下载成功 ({len(image_data)} bytes)")
        
        # 上传图片
        # print(f"  📤 上传到 {cell_range}...")
        success = self.upload_image(image_data, cell_range)
        
        if success:
            # print(f"  ✅ 上传成功")
            return True
        else:
            print(f"  ❌ 上传失败")
            return False

    def run(self):
        """运行主流程"""
        print(f"\n{'='*60}")
        print(f"🚀 开始处理飞书表格图片")
        print(f"📍 行范围: {self.start_row} - {self.end_row}")
        print(f"{'='*60}\n")
        
        start_time = time.time()
        
        # 获取表格数据
        res = self.sheet_value()
        if res is None:
            print("❌ 无法获取表格数据，程序退出")
            return
        
        print(f"\n开始处理 {len(res)} 行数据...\n")
        
        # 逐行处理
        for idx, r in enumerate(res):
            row_index = idx + self.start_row
            # print(f"\n[{idx + 1}/{len(res)}] 处理行 {row_index}:")
            
            # 检查是否有图片URL
            if not r or not r[0] or "http" not in r[0]:
                print(f"  ⏭️  跳过 (无图片URL)")
                self.skip_count += 1
                continue
            
            # 获取图片URL
            img_url = r[0]
            if img_url.startswith('["'):
                try:
                    img_url = json.loads(img_url)[0]
                except:
                    print(f"  ❌ 解析URL失败: {img_url[:50]}")
                    self.fail_count += 1
                    continue
            
            # 处理图片
            cell_range = f"{self.write_column}{row_index}:{self.write_column}{row_index}"
            success = self.write_img_to_excel(img_url, cell_range)
            
            if success:
                self.success_count += 1
            else:
                self.fail_count += 1
            
            # 添加小延迟，避免请求过快
            time.sleep(0.2)
        
        # 统计结果
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n{'='*60}")
        print(f"✨ 处理完成!")
        print(f"{'='*60}")
        print(f"📊 总计: {len(res)} 行")
        print(f"✅ 成功: {self.success_count} 行")
        print(f"❌ 失败: {self.fail_count} 行")
        print(f"⏭️  跳过: {self.skip_count} 行")
        print(f"⏱️  总耗时: {duration:.2f} 秒")
        print(f"🚀 平均速度: {len(res)/duration:.2f} 行/秒")
        print(f"{'='*60}\n")
        
        # 关闭session
        self.session.close()


if __name__ == "__main__":
    start = 2
    end = 4
    
    try:
        operator = FeishuSheetOperator(start, end)
        operator.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  程序被用户中断")
    except Exception as e:
        print(f"\n\n❌ 程序异常退出: {e}")
