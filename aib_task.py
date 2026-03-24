#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/11/13
 @Author : wwf
 Description: aib 任务管理器
"""
import json
import time
import zipfile
import os
import requests
import pandas as pd


def modify_json_and_zip(input_path: str, script_id: int, script_name: str, app_id: int, output_dir: str = ".") -> str:
    """
    读取 JSON 文件，修改 id 字段，保存为 project.json，并压缩为 project.zip。
    返回生成的 zip 文件的绝对路径。

    参数：
        input_path (str): 原始 JSON 文件路径
        script_id (int): 要修改成的 script_id
        script_name (str): 脚本名称
        app_id (int): 应用 ID
        output_dir (str): 输出文件保存目录（默认为当前目录）

    返回：
        str: 生成的 project.zip 文件的绝对路径
    """
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    output_json = os.path.join(output_dir, "project.json")
    output_zip = os.path.join(output_dir, "project.zip")

    # 1. 读取 JSON
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. 修改 id
    if isinstance(data, dict):
        data["id"] = script_id
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "id" in item:
                item["id"] = script_id

    # 修改scriptFile中的配置
    if "scriptFile" in data and isinstance(data["scriptFile"], str):
        try:
            # 解析 scriptFile 内部 JSON 字符串
            script_data = json.loads(data["scriptFile"])

            # 修改 scriptId
            if isinstance(script_data, dict):
                script_data["scriptId"] = script_id

            script_data["scriptName"] = script_name
            script_data["appID"] = app_id

            # 转回字符串保存
            data["scriptFile"] = json.dumps(script_data, ensure_ascii=False)
        except json.JSONDecodeError:
            print("⚠️ scriptFile 不是有效的 JSON 字符串，跳过修改。")

    # 3. 保存为 project.json
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    # 4. 压缩为 project.zip
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(output_json, arcname="project.json")

    return os.path.abspath(output_zip)


class AibTask:
    def __init__(self, cookie, excel_path: str = "/Users/wwf/Documents/codes/PycharmProjects/Script/data/banks.xlsx"):
        # 创建 Session
        self.session = requests.Session()
        # 把 cookie 字典加入 session
        self.session.cookies.update(cookie)
        df = pd.read_excel(excel_path)
        self.packages = df["package"].dropna().tolist()

    def main(self):
        for package in self.packages:
            if not package:
                continue
            app_name, app_id = self.get_app_id(package)
            # 创建脚本，获取脚本id
            print("app_name:", app_name)
            print("app_id:", app_id)

            tasks = self.search_tasks(f"CAFA-{app_name}-Android")
            if tasks:
                print(f"CAFA-{app_name}-Android 任务已存在")
                continue

            script_id = self.create_script(app_id, app_name)
            print("script_id:", script_id)
            if script_id == -1:
                print("脚本id 创建失败，script_id:", script_id)
                return

            # 创建任务
            self.create_task(app_name, str(app_id), str(script_id))

    def create_script(self, app_id: str, app_name: str) -> int:
        script_name = f"CAFA-{app_name}-Android"
        exits, script_id = self.search_script(script_name)
        if exits:
            return script_id
        else:
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "no-cache",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://wukong1.tingyun.com/aib-web",
                "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"macOS\"",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
                "x-requested-with": "XMLHttpRequest"
            }
            url = "https://wukong1.tingyun.com/appops/script/create"
            params = {
                "appID": app_id,
                "scriptName": script_name,
                "remark": "CAFA",
                "t": str(int(time.time() * 1000)),
            }
            try:
                response = self.session.get(url, headers=headers, params=params)
                response.raise_for_status()
                # 创建脚本，获取脚本id
                sc_id = int(response.text)
                # 赋值脚本模板
                zip_path = modify_json_and_zip("data/project.json", sc_id, script_name, int(app_id))
                # print("✅ 生成压缩包路径：", zip_path)
                script_id2 = self.upload_script(zip_path)
                if script_id2 != sc_id:
                    print(f"script_id 不一致，{sc_id} {script_id2}")
                    return -1

                return sc_id
            except Exception as e:
                print(e)
                return -1

    def get_app_id(self, package_name: str) -> tuple[str, int] | None:
        if os.path.exists("data/apps.json"):
            with open("data/apps.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "no-cache",
                "content-length": "0",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://wukong1.tingyun.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://wukong1.tingyun.com/aib-web",
                "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"macOS\"",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
                "x-requested-with": "XMLHttpRequest"
            }

            url = "https://wukong1.tingyun.com/appops/app/find/bundle/0"
            params = {
                "t": str(int(time.time() * 1000)),
            }
            response = self.session.post(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            with open("data/apps.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

        for app in data:
            if app["appBundleID"] == package_name and app["type"] == 2:
                appName = app["appName"]
                appId = app["appVersionList"][0]["id"]
                return appName, appId
        return None

    def upload_script(self, zip_path) -> int:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "origin": "https://wukong1.tingyun.com",
            "pragma": "no-cache",
            "referer": "https://wukong1.tingyun.com/aib-web",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "x-requested-with": "XMLHttpRequest"
        }

        url = "https://wukong1.tingyun.com/appops/script/upload"
        files = {
            "project": ("project.zip", open(zip_path, "rb"), "application/zip")
        }

        # 发送 POST 请求
        response = self.session.post(url, headers=headers, cookies=cookies, files=files)
        response.raise_for_status()
        # {"success":true,"data":8464}
        response = response.json()
        if response["success"]:
            return response["data"]
        else:
            return -1

    def create_task(self, app_name: str, app_id: str, script_id: str):
        task_name = f"CAFA-{app_name}-Android"
        tasks = self.search_tasks(task_name)
        if tasks:
            print(f"{task_name} 任务已存在，任务id:{tasks[0]["id"]}")
        else:
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "no-cache",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://wukong1.tingyun.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://wukong1.tingyun.com/aib-web",
                "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"macOS\"",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
                "x-requested-with": "XMLHttpRequest"
            }

            url = "https://wukong1.tingyun.com/appops/task/create/"
            params = {
                "t": str(int(time.time() * 1000)),
            }
            data = {
                "name": task_name,
                "groupID": "1701",
                "appID": app_id,
                "scriptID": script_id,
                "timeout": "60",
                "taskInterval": "600",
                "type": "1",
                "frequency": "0",
                "stime": "2025-11-13 14:51:34",
                "expire": "2025-11-30 14:51:34",
                "expectedPoint": "0",
                "extra": "",
                "clearCache": "0",
                "startType": "0",
                "netDataFetchType": "0",
                "collectFrequency": "1",
                "ipVersion": "0",
                "configUrl": ""
            }
            response = self.session.post(url, headers=headers, params=params, data=data)
            response.raise_for_status()
            print(f"{task_name} 创建成功，id:{response.text}")

    # 检查脚本是否已存在
    def search_script(self, script_name: str) -> tuple[bool, int]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://wukong1.tingyun.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://wukong1.tingyun.com/aib-web",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "x-requested-with": "XMLHttpRequest"
        }
        url = "https://wukong1.tingyun.com/appops/script/list/1/20"
        params = {
            "t": str(int(time.time() * 1000)),
            "frUrl": "https://wukong1.tingyun.com/aib-web#/layout-container/project-list"
        }
        data = {
            "osType": 2,
            "scriptName": script_name,
            "appID": ""
        }
        data = json.dumps(data, separators=(',', ':'))
        response = self.session.post(url, headers=headers, params=params, data=data)
        response.raise_for_status()
        response = response.json()
        if response["success"]:
            if response["data"]["totalCount"] > 0:
                # 已存在，不创建，返回currentPageList, response["data"]["currentPageList"]
                return True, response["data"]["currentPageList"][0]["id"]
            else:
                return False, -1
        else:
            raise Exception("查询脚本失败！")

    def search_tasks(self, task_name: str) -> list[dict]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://wukong1.tingyun.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://wukong1.tingyun.com/aib-web",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "x-requested-with": "XMLHttpRequest"
        }

        url = "https://wukong1.tingyun.com/appops/task/list/1/150"
        params = {
            "t": str(int(time.time() * 1000)),
            "frUrl": "https://wukong1.tingyun.com/aib-web#/layout-container/task-manager"
        }
        data = {
            "osType": 2,
            "taskName": task_name,
            "appID": None,
            "status": None,
            "frequency": 0
        }
        data = json.dumps(data, separators=(',', ':'))
        response = self.session.post(url, headers=headers, params=params, data=data)

        response.raise_for_status()
        response = response.json()
        if response["success"]:
            return response["data"]["currentPageList"]
        else:
            raise Exception("查询任务失败！")

    # 批量更新用例
    def update_script_main(self, script_temp_path: str):
        for package in self.packages:
            if not package:
                continue

            app_name, app_id = self.get_app_id(package)
            # 创建脚本，获取脚本id
            print("app_name:", app_name)
            print("app_id:", app_id)

            script_name = f"CAFA-{app_name}-Android"
            exits, script_id = self.search_script(script_name)
            if exits:
                zip_path = modify_json_and_zip(script_temp_path, script_id, script_name, app_id)
                # print("✅ 生成压缩包路径：", zip_path)
                res = self.upload_script(zip_path)
                if res != -1:
                    print(f"{script_name} 用例更新完成")
                else:
                    raise Exception(f"{script_name} 用例更新失败 ！！！！！！！")


            else:
                raise Exception(f"未找到{script_name}的脚本id")

    # 更新任务状态
    def update_task_status(self, task_name: str, task_id: str, status: str):
        # status 1 开启任务  0关闭任务
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://wukong1.tingyun.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://wukong1.tingyun.com/aib-web",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "x-requested-with": "XMLHttpRequest"
        }

        url = "https://wukong1.tingyun.com/appops/task/status"
        params = {
            "t": str(int(time.time() * 1000)),
        }

        data = {
            "ids": task_id,
            "status": status
        }
        response = self.session.post(url, headers=headers, params=params, data=data)
        response.raise_for_status()
        if response.text == "1" or response.text == 1:
            print(f"{task_name} 任务状态更新完成")

    def update_task_with_start_str(self, task_start_str: str, status: str):
        """
        启动指定前缀（task_start_str）的任务。
        会根据包名匹配任务的 appBundleID，若该任务的状态不是 "1"，则更新为 "1"。
        """
        tasks = self.search_tasks(task_start_str)
        if not tasks:
            return  # 没有匹配任务，直接返回

        # 构建 {bundle_id: task} 映射，方便快速查找
        task_map = {
            task["appBundleID"]: task
            for task in tasks
            if "appBundleID" in task and "id" in task
        }

        for package in filter(None, self.packages):  # 跳过空包名
            task = task_map.get(package)
            if not task:
                continue

            # 已经是启动状态，跳过
            if str(task.get("status")) == status:
                print(f"{task['name']}已{'开启' if status == '1' else '关闭'}，跳过！")
                continue

            # 更新任务
            self.update_task_status(task['name'], task["id"], status)

    def dump_task_data(self, task_id: int) -> dict | None:
        url = "https://wukong1.tingyun.com/appops/report-data/export"

        payload = {
            "taskID": task_id,
            "beginTime": "2025-11-12 00:00:00",
            "endTime": "2025-11-17 00:00:00"
        }

        headers = {
            'Content-Type': "application/json",
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
        }

        response = self.session.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        try:
            task_data = response.json()
            if task_data["success"]:
                datas = task_data["data"]

                launchs = []
                cpus = []
                mems = []
                uploadTraffics = []
                downloadTraffics = []
                step_ut = []
                uts = []

                for data in datas:
                    if data["status"] == 0:
                        launch = data["launch"]
                        cpu = data["cpu"]
                        mem = data["mem"]
                        uploadTraffic = data["uploadTraffic"]
                        downloadTraffic = data["downloadTraffic"]
                        ut = data["stepList"][0]["ut"]
                        launchs.append(launch)
                        cpus.append(cpu)
                        mems.append(mem)
                        uploadTraffics.append(uploadTraffic)
                        downloadTraffics.append(downloadTraffic)
                        uts.append(ut)
                        step_ut.append(launch + ut)

                launch = round(sum(launchs) / len(launchs), 2)
                cpu = round(sum(cpus) / len(cpus), 2)
                mem = round(sum(mems) / len(mems), 2)
                uploadTraffic = round(sum(uploadTraffics) / len(uploadTraffics) / 1024, 2)
                downloadTraffic = round(sum(downloadTraffics) / len(downloadTraffics) / 1024, 2)
                step_ut = round(sum(step_ut) / len(step_ut), 2)
                return {"launch": launch, "cpu": cpu, "mem": mem, "uploadTraffic": uploadTraffic,
                        "downloadTraffic": downloadTraffic, "step_ut": step_ut, "uts": uts, "launchs": launchs}
        except Exception as e:
            print(response.text)
            return None

    def dump_all_task_data(self):
        tasks = self.search_tasks("CAFA-")
        if not tasks:
            return  # 没有匹配任务，直接返回

        # 构建 {bundle_id: task} 映射，方便快速查找
        task_map = {
            task["appBundleID"]: task
            for task in tasks
            if "appBundleID" in task and "id" in task
        }

        results = []
        try:
            for package in filter(None, self.packages):  # 跳过空包名

                app_name, app_id = self.get_app_id(package)
                # 创建脚本，获取脚本id
                print("app_name:", app_name)

                task = task_map.get(package)
                if not task:
                    print(f"{app_name} 没有对应的任务")
                    data = {
                        "Package": package,
                        "AppName": app_name,
                        "launch": None,
                        "cpu": None,
                        "mem": None,
                        "uploadTraffic": None,
                        "downloadTraffic": None,
                        "step_ut": None,
                        "err": None
                    }
                    results.append(data)
                    continue

                task_id = task["id"]
                task_data = self.dump_task_data(int(task_id))
                if not task_data:
                    print(f"{app_name} 获取任务失败")
                    data = {
                        "Package": package,
                        "AppName": app_name,
                        "launch": None,
                        "cpu": None,
                        "mem": None,
                        "uploadTraffic": None,
                        "downloadTraffic": None,
                        "step_ut": None,
                        "err": None
                    }
                    results.append(data)
                    continue

                print(task_data["uts"])
                inp = input("请根据第一步骤耗时，判断该数据是否有问题y/n")
                err = None
                if inp == "y":
                    err = 1
                    adt = int(input("输入广告时间"))
                    uts = []
                    for i, ut in enumerate(task_data["uts"]):
                        launch_t = task_data["launchs"][i]
                        if ut > adt:
                            uts.append(launch_t + ut - adt)
                        else:
                            uts.append(launch_t + ut)
                    task_data["step_ut"] = round(sum(uts) / len(uts), 2)
                # 把数据写入到表格
                data = {
                    "Package": package,
                    "AppName": app_name,
                    "launch": task_data["launch"],
                    "cpu": task_data["cpu"],
                    "mem": task_data["mem"],
                    "uploadTraffic": task_data["uploadTraffic"],
                    "downloadTraffic": task_data["downloadTraffic"],
                    "step_ut": task_data["step_ut"],
                    "err": err
                }
                results.append(data)
        except Exception as e:
            print(e)
        finally:
            # 保存结果到 Excel
            file_name = f"dump_datas_{int(time.time())}.xlsx"
            output_file = os.path.join("data", file_name)
            pd.DataFrame(results).to_excel(output_file, index=False)
            print(f"\n✅ 测试完成！结果已保存到：{output_file}")

    def dump_task_data_by_name(self, task_name, ad=None):
        tasks = self.search_tasks(task_name)
        if not tasks:
            return None

        if len(tasks) > 1:
            print("任务匹配到多个：")
            for task in tasks:
                print(f"task_name:{task['name']} ,任务id:{task['id']}")

        task_id = tasks[0]["id"]
        url = "https://wukong1.tingyun.com/appops/report-data/export"

        payload = {
            "taskID": task_id,
            "beginTime": "2025-11-12 00:00:00",
            "endTime": "2025-11-17 00:00:00"
        }

        headers = {
            'Content-Type': "application/json",
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
        }

        response = self.session.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        try:
            task_data = response.json()
            if task_data["success"]:
                datas = task_data["data"]

                launchs = []
                cpus = []
                mems = []
                uploadTraffics = []
                downloadTraffics = []
                step_ut = []

                for data in datas:
                    if data["status"] == 0:
                        launch = data["launch"]
                        cpu = data["cpu"]
                        mem = data["mem"]
                        uploadTraffic = data["uploadTraffic"]
                        downloadTraffic = data["downloadTraffic"]
                        ut = data["stepList"][0]["ut"]
                        launchs.append(launch)
                        cpus.append(cpu)
                        mems.append(mem)
                        uploadTraffics.append(uploadTraffic)
                        downloadTraffics.append(downloadTraffic)
                        step_ut.append(launch + ut)

                launch = round(sum(launchs) / len(launchs), 2)
                cpu = round(sum(cpus) / len(cpus), 2)
                mem = round(sum(mems) / len(mems), 2)
                uploadTraffic = round(sum(uploadTraffics) / len(uploadTraffics) / 1024, 2)
                downloadTraffic = round(sum(downloadTraffics) / len(downloadTraffics) / 1024, 2)
                print(f"step_ut:{step_ut}")
                if ad:
                    step_uts = []
                    for step in step_ut:
                        if step > ad:
                            step_uts.append(step - ad)
                        else:
                            step_uts.append(step)

                    print(f"step_uts:{step_uts}")
                    step_ut_t = round(sum(step_uts) / len(step_uts), 2)
                else:
                    step_ut_t = round(sum(step_ut) / len(step_ut), 2)
                return {"launch": launch, "cpu": cpu, "mem": mem, "uploadTraffic": uploadTraffic,
                        "downloadTraffic": downloadTraffic, "step_ut(s)": round(step_ut_t / 1000, 2)}
        except Exception as e:
            print(response.text)
            return None


if __name__ == '__main__':
    # Aib_Task().main()
    # Aib_Task().update_script_main("data/project.json")

    # Aib_Task().update_task_with_start_str("CAFA-", "1")

    # print(AibTask().dump_task_data(8986))
    cookies = {
        "JSESSIONID": "2DBEA5C11FCF4DCBA5A22645B38F9CAC",
        "wk_appopsweb_uid": "eb842f664856db23e78d372401827285631d3f9d",
        "wk_uid": "5bdecd96985cc7c3d90c639b8c7b4f79171699b0",
        "CASTGC": "TGT-363860-Uy7vnamqvPijTbLQozzdpReA0WP4cOBmJiUfiziKmjYl5vmIQo-account.tingyun.com"
    }

    # AibTask(cookie=cookies, excel_path="/Users/wwf/Desktop/ss_87.xlsx").dump_all_task_data()
    print(AibTask(cookie=cookies).dump_task_data_by_name("CAFA-锦州银行-Android"))
