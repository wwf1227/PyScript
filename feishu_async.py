#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import base64
import json
import os
from datetime import datetime
from typing import List, Optional, Tuple

import aiohttp
from aiohttp import ClientSession, TCPConnector


class FeishuSheetOperatorAsyncV2:
    def __init__(self, start: int, end: int, max_concurrent: int = 10):
        """
        异步飞书表格操作器 V2 - 增强版
        
        Args:
            start: 起始行号
            end: 结束行号
            max_concurrent: 最大并发数（默认10，建议5-15之间）
        """
        # 在实际使用时，需要替换为有效的飞书API凭证
        self.APP_ID = "cli_a8626aaxxx7e101c"
        self.APP_SECRET = "14AXuQE5vqK4Z75FOxxxxxxaUCtTVCR5"
        self.TOKEN_CACHE_FILE = "data/feishu_token_cache.json"
        self.base_url = "https://open.feishu.cn"
        self.start_row = start
        self.end_row = end
        self.table_name = "MpdWs2EGshjQXbtJKrccT6xbnOb"
        self.sheet_name = "wlmPUI"
        self.max_concurrent = max_concurrent
        self.token = None
        
        # 统计信息
        self.success_count = 0
        self.fail_count = 0
        self.total_count = 0
        
        # 失败重试队列
        self.failed_rows = []

    async def get_tenant_access_token(self) -> str:
        """获取飞书租户访问令牌（支持缓存）"""
        # 尝试从缓存读取token
        if os.path.exists(self.TOKEN_CACHE_FILE):
            try:
                with open(self.TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
                    if "token" in cache and "expire_time" in cache:
                        # 检查token是否在有效期内（提前10分钟过期）
                        if datetime.now().timestamp() < cache["expire_time"] - 600:
                            self.token = cache["token"]
                            return self.token
            except Exception:
                pass
        else:
            # 创建缓存文件目录
            os.makedirs(os.path.dirname(self.TOKEN_CACHE_FILE), exist_ok=True)

        # 重新获取token
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {"app_id": self.APP_ID, "app_secret": self.APP_SECRET}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result["code"] == 0:
                        token = result["tenant_access_token"]
                        expire_time = datetime.now().timestamp() + result["expire"]

                        # 缓存token
                        with open(self.TOKEN_CACHE_FILE, "w") as f:
                            json.dump({"token": token, "expire_time": expire_time}, f)

                        self.token = token
                        return token

                text = await response.text()
                raise Exception(f"Failed to get tenant_access_token: {text}")

    async def fetch_sheet_values(self, session: ClientSession) -> Optional[List]:
        """异步获取表格数据"""
        try:
            params = {
                "valueRenderOption": "ToString",
                "dateTimeRenderOption": "FormattedString",
            }
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8"
            }

            url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.table_name}/values/{self.sheet_name}!F{self.start_row}:F{self.end_row}"
            
            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"获取表格数据失败: {text}")

                result = await response.json()
                if result["code"] == 0:
                    return result["data"]["valueRange"]["values"]
                else:
                    raise Exception(f"API返回错误: {result}")

        except Exception as e:
            print(f"❌ 获取表格数据异常: {e}")
            return None

    async def download_image(self, session: ClientSession, image_url: str, retry: int = 3) -> Optional[bytes]:
        """异步下载图片（带重试）"""
        # 添加更完整的请求头，模拟真实浏览器
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "accept-encoding": "gzip, deflate, br",
            "referer": image_url.split('/api/')[0] if '/api/' in image_url else image_url,
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "image",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "same-origin",
        }
        
        for attempt in range(retry):
            try:
                async with session.get(
                    image_url, 
                    headers=headers, 
                    timeout=aiohttp.ClientTimeout(total=60),
                    allow_redirects=True
                ) as response:
                    if response.status == 200:
                        return await response.read()
                    elif response.status == 403:
                        # 403 可能是防盗链，尝试不带referer
                        if attempt == 0:
                            headers_no_referer = headers.copy()
                            headers_no_referer.pop('referer', None)
                            async with session.get(
                                image_url, 
                                headers=headers_no_referer, 
                                timeout=aiohttp.ClientTimeout(total=60)
                            ) as resp2:
                                if resp2.status == 200:
                                    return await resp2.read()
                        print(f"⚠️  图片下载被拒绝 403 (尝试 {attempt + 1}/{retry}): 行号相关")
                    else:
                        print(f"⚠️  图片下载失败 (尝试 {attempt + 1}/{retry}): 状态码 {response.status}")
            except asyncio.TimeoutError:
                print(f"⚠️  图片下载超时 (尝试 {attempt + 1}/{retry})")
            except Exception as e:
                print(f"⚠️  图片下载异常 (尝试 {attempt + 1}/{retry}): {str(e)[:50]}")
            
            if attempt < retry - 1:
                await asyncio.sleep(2 ** attempt)  # 指数退避: 1秒, 2秒, 4秒
        
        return None

    async def upload_image_to_cell(
        self, 
        session: ClientSession, 
        image_data: bytes, 
        cell_range: str,
        retry: int = 3
    ) -> bool:
        """异步上传图片到单元格（带重试和速率限制）"""
        # Base64 编码
        fb = base64.b64encode(image_data).decode("utf-8")

        data = {
            "range": f"{self.sheet_name}!{cell_range}",
            "image": fb,
            "name": "image.png",
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{self.table_name}/values_image"

        for attempt in range(retry):
            try:
                # 增加超时时间，上传可能需要更长时间
                async with session.post(
                    url, 
                    headers=headers, 
                    json=data, 
                    timeout=aiohttp.ClientTimeout(total=90)  # 增加到90秒
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("code") == 0:
                            return True
                        else:
                            print(f"⚠️  上传API错误 (尝试 {attempt + 1}/{retry}): {cell_range}, {result.get('msg', 'unknown')}")
                    else:
                        text = await response.text()
                        print(f"⚠️  上传失败 (尝试 {attempt + 1}/{retry}): {cell_range}, 状态 {response.status}")
            except asyncio.TimeoutError:
                print(f"⚠️  上传超时 (尝试 {attempt + 1}/{retry}): {cell_range}")
            except Exception as e:
                print(f"⚠️  上传异常 (尝试 {attempt + 1}/{retry}): {cell_range}, {str(e)[:50]}")
            
            if attempt < retry - 1:
                # 指数退避，给飞书API更多时间
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        return False

    async def process_single_row(
        self, 
        session: ClientSession, 
        semaphore: asyncio.Semaphore,
        row_index: int, 
        row_data: List
    ) -> bool:
        """处理单行数据（下载并上传图片）"""
        async with semaphore:  # 控制并发数
            try:
                if not row_data or not row_data[0] or "http" not in row_data[0]:
                    return False

                img_url = row_data[0]
                # 处理JSON格式的URL
                if img_url.startswith('["'):
                    img_url = json.loads(img_url)[0]

                cell_range = f"G{row_index}:G{row_index}"

                # 下载图片
                image_data = await self.download_image(session, img_url)
                if not image_data:
                    print(f"❌ 行 {row_index}: 图片下载失败")
                    self.failed_rows.append((row_index, row_data))
                    return False

                # 添加小延迟，避免过快请求飞书API
                await asyncio.sleep(0.15)

                # 上传图片
                success = await self.upload_image_to_cell(session, image_data, cell_range)
                
                if success:
                    print(f"✅ 行 {row_index}: 处理成功")
                    return True
                else:
                    print(f"❌ 行 {row_index}: 上传失败")
                    self.failed_rows.append((row_index, row_data))
                    return False

            except Exception as e:
                print(f"❌ 行 {row_index}: 处理异常 - {e}")
                self.failed_rows.append((row_index, row_data))
                return False

    async def retry_failed_rows(self, session: ClientSession):
        """重试失败的行"""
        if not self.failed_rows:
            return
        
        print(f"\n🔄 开始重试 {len(self.failed_rows)} 个失败的任务...\n")
        
        # 降低并发数，更谨慎地重试
        retry_concurrent = max(3, self.max_concurrent // 2)
        semaphore = asyncio.Semaphore(retry_concurrent)
        
        retry_tasks = []
        failed_copy = self.failed_rows.copy()
        self.failed_rows.clear()  # 清空，重试时会重新添加仍然失败的
        
        for row_index, row_data in failed_copy:
            task = self.process_single_row(session, semaphore, row_index, row_data)
            retry_tasks.append(task)
        
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        
        retry_success = sum(1 for r in retry_results if r is True)
        print(f"\n✨ 重试完成: 成功 {retry_success}/{len(failed_copy)}")

    async def run(self):
        """运行主流程"""
        print(f"🚀 开始处理: 行 {self.start_row} 到 {self.end_row}")
        print(f"⚙️  最大并发数: {self.max_concurrent}")
        
        # 获取访问令牌
        print("🔑 获取访问令牌...")
        await self.get_tenant_access_token()
        print("✅ 令牌获取成功")

        # 创建连接器，增加连接池大小
        connector = TCPConnector(limit=self.max_concurrent * 2, limit_per_host=self.max_concurrent)
        
        async with ClientSession(connector=connector) as session:
            # 获取表格数据
            print("📊 获取表格数据...")
            sheet_data = await self.fetch_sheet_values(session)
            
            if not sheet_data:
                print("❌ 未获取到表格数据")
                return

            self.total_count = len(sheet_data)
            print(f"📝 共获取 {self.total_count} 行数据")

            # 创建信号量控制并发
            semaphore = asyncio.Semaphore(self.max_concurrent)

            # 创建所有任务
            tasks = []
            for idx, row_data in enumerate(sheet_data):
                row_index = idx + self.start_row
                task = self.process_single_row(session, semaphore, row_index, row_data)
                tasks.append(task)

            # 并发执行所有任务
            print(f"\n⏳ 开始并发处理 {len(tasks)} 个任务...\n")
            start_time = datetime.now()
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            for result in results:
                if result is True:
                    self.success_count += 1
                else:
                    self.fail_count += 1

            # 如果有失败的，尝试重试
            if self.failed_rows:
                await self.retry_failed_rows(session)
                
                # 重新统计
                final_failed = len(self.failed_rows)
                final_success = self.total_count - final_failed
                self.success_count = final_success
                self.fail_count = final_failed

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # 输出统计信息
            print(f"\n{'='*60}")
            print(f"✨ 处理完成!")
            print(f"📊 总计: {self.total_count} 条")
            print(f"✅ 成功: {self.success_count} 条")
            print(f"❌ 失败: {self.fail_count} 条")
            print(f"⏱️  耗时: {duration:.2f} 秒")
            print(f"🚀 平均速度: {self.total_count/duration:.2f} 条/秒")
            
            if self.failed_rows:
                print(f"\n⚠️  仍有 {len(self.failed_rows)} 条失败，失败行号:")
                failed_indices = [r[0] for r in self.failed_rows[:10]]
                print(f"   {failed_indices}" + ("..." if len(self.failed_rows) > 10 else ""))
            
            print(f"{'='*60}")


async def main():
    """主函数"""
    start = 2
    end = 1510
    max_concurrent = 10  # 降低并发数以避免超时，可根据实际情况调整为5-15
    
    operator = FeishuSheetOperatorAsyncV2(start, end, max_concurrent)
    await operator.run()


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())