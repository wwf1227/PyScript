#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import requests
from json_to_excel_incremental import append_to_excel
from parser_utils import LogParser

beginTime = "2026-03-20 15:20:00"
endTime = "2026-03-20 15:40:00"


class AibTaskLog:
    def __init__(self, cookie):
        # 创建 Session
        self.session = requests.Session()
        # 把 cookie 字典加入 session
        self.session.cookies.update(cookie)

    def dump_task_data(self, task_id: int) -> list | None:
        url = "https://wukong1.tingyun.com/appops/report-data/export"

        payload = {
            "taskID": task_id,
            "beginTime": beginTime,
            "endTime": endTime,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
        }

        response = self.session.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        try:
            task_data = response.json()
            if task_data["success"]:
                return task_data["data"]

            return None
        except Exception as e:
            print(response.text)
            return None

    def get_step_log(self, data):
        try:
            headers = {
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "origin": "https://wukong1.tingyun.com",
                "referer": "https://wukong1.tingyun.com/aib-web/",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
                "x-requested-with": "XMLHttpRequest",
            }

            url = "https://wukong1.tingyun.com/appops/aib-report-data/scatter-sample-step-logs"

            params = {
                "t": str(int(time.time() * 1000)),
            }

            data = json.dumps(data, separators=(",", ":"))
            response = self.session.post(
                url, headers=headers, cookies=cookies, params=params, data=data
            )
            response.raise_for_status()
            log_data = response.json()
            if log_data["success"]:
                return log_data["data"]["taskLogs"]

            return None
        except Exception as e:
            print(response.text)
            return None

    def main(self, taskId):
        file_path = "aggregated_results.xlsx"
        self.taskId = taskId
        try:
            datas = self.dump_task_data(task_id=taskId)
            print(f"共{len(datas)}条数据")
            if datas is None:
                print("任务数据为空！！！")
                exit(1)
            for index, data in enumerate(datas):
                # print(data)
                taskUID = data["taskUID"]
                appLog = data.get("fileInfo", {}).get("appLogUrl")
                taskLog = data.get("fileInfo", {}).get("taskLogUrl")
                et = data["et"]
                st = data["st"]
                stepList = data["stepList"]

                all_log_json = []
                for step_data in stepList:

                    stepActionTs1 = int(step_data["actionTs1"] / 1000000)
                    stepActionTs2 = int(step_data["actionTs2"] / 1000000)
                    steo_data = {
                        "taskUID": taskUID,
                        "st": st,
                        "et": et,
                        "appLog": appLog,
                        "taskLog": taskLog,
                        "stepActionTs1": stepActionTs1,
                        "stepActionTs2": stepActionTs2,
                    }
                    step_log = self.get_step_log(steo_data)
                    if len(step_log) < 1:
                        continue
                    all_log_json.append(step_log)

                if len(all_log_json) < 1:
                    print(f"-----第{index+1}条，没有日志，data:{data}")
                    continue

                aggregated_results = LogParser.aggregate_from_json_list(all_log_json)
                # print(aggregated_results)

                append_to_excel(
                    aggregated_results,
                    output_path=f"youpin_{beginTime.replace(" ","_")}_{endTime.replace(" ","_")}_{taskId}.xlsx",
                )

        except Exception as e:
            print(f"出现问题！{e}")
        finally:
            print("保存表格")


if __name__ == "__main__":
    # Aib_Task().main()
    # Aib_Task().update_script_main("data/project.json")

    # Aib_Task().update_task_with_start_str("CAFA-", "1")

    # print(AibTask().dump_task_data(8986))
    cookies = {
        "JSESSIONID": "1BEF6A39883F5E98E83F1041F07B908C",
        "wk_appopsweb_uid": "d25fcb95f991e19654fb48eacd9228d3881b01da",
        "wk_uid": "5bdecd96985cc7c3d90c639b8c7b4f79171699b0",
        "CASTGC": "TGT-256288-de5BI5mOu61LTg5U5zgFBKGRt9nffSzf9EEUEIrfdHzaUowpIf-account.tingyun.com"
    }
    AibTaskLog(cookie=cookies).main(9391)
    # AibTaskLog(cookie=cookies).main(9406)
    # AibTaskLog(cookie=cookies).main(9409)
