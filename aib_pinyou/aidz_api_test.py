import hashlib
import hmac
import json
import time
import uuid
import urllib.request
import urllib.error
from collections import defaultdict
import pandas as pd

# ===== 配置区域 =====
ENVIRONMENTS = {
    "1": {
        "name": "内网",
        "base_url": "https://appalpha1.tingyun.com/appops/rpc.po/deepzore/api/v1",
    },
    "2": {
        "name": "Beta",
        "base_url": "https://wukong1beta.tingyun.com/appops/rpc.po/deepzore/api/v1",
    },
    "3": {
        "name": "线上",
        "base_url": "https://wukong1.tingyun.com/appops/rpc.po/deepzore/api/v1",
    },
}
ACCOUNTS = {
    "1": {
        "name": "品友账号",
        "api_key": "BBKdIpDDxn",
        "api_secret": "a3f8c2d1e4b7096f5a2c8e3d1f4b7096a3f8c2d1e4b7096f5a2c8e3d1f4b709",
    },
    "2": {
        "name": "ceshi_my3",
        "api_key": "mcEjYjVkTJ",
        "api_secret": "5e62ffbe3e460c46182570a91295cc7cc49e6a0902f8dd5d129bf35226c756ee",
    },
}
# ====================

BASE_URL = ENVIRONMENTS["1"]["base_url"]
API_KEY = ACCOUNTS["1"]["api_key"]
API_SECRET = ACCOUNTS["1"]["api_secret"]


# ================================================================== 菜单

MENU = [
    ("切换环境  (内网 / Beta / 线上)", "switch_env"),
    ("切换账号", "switch_account"),
    ("createTask        创建任务", "menu_createTask"),
    ("queryByTaskId     按 taskId 查状态", "menu_queryByTaskId"),
    ("queryByBatch      按 taskId+batchId 查状态", "menu_queryByTaskIdAndBatchId"),
    ("updateTask        取消/更新任务", "menu_updateTask"),
    ("updateTaskByBatch 按 batchId 更新", "menu_updateTaskByBatch"),
    ("getTaskData       获取任务数据", "menu_getTaskData"),
    ("listAllTasks      列出全部任务", "menu_listAllTasks"),
    ("listByStatus      按状态过滤", "menu_listByStatus"),
    ("listByTimeRange   按时间范围过滤", "menu_listByTimeRange"),
    ("listByStatusAndTime 状态+时间范围", "menu_listByStatusAndTimeRange"),
    ("listByTimeRange + askMethod 统计", "menu_statByAskMethod"),
    ("按时间范围统计使用量并导出Excel", "menu_exportUsageByTimeRange"),
    ("loadTasks         Load 任务到系统", "menu_loadTasks"),
    ("testInvalidSign   签名错误测试", "menu_invalidSignature"),
    ("退出", "quit"),
]


def show_menu():
    print("\n" + "=" * 60)
    print(f"  环境: {_current_env_name()}  账号: {_current_account_name()}")
    print(f"  URL: {BASE_URL}")
    print("=" * 60)
    for i, (label, _) in enumerate(MENU, 1):
        print(f"  {i:>2}. {label}")
    print("=" * 60)


def _current_env_name():
    for env in ENVIRONMENTS.values():
        if env["base_url"] == BASE_URL:
            return env["name"]
    return "自定义"


def _current_account_name():
    for acc in ACCOUNTS.values():
        if acc["api_key"] == API_KEY:
            return acc["name"]
    return "自定义"


def prompt(msg, default=None):
    hint = f" [{default}]" if default is not None else ""
    val = input(f"  {msg}{hint}: ").strip()
    return val if val else default


def prompt_int(msg, default=None):
    raw = prompt(msg, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        print(f"  ⚠ 输入无效，使用默认值 {default}")
        return default


def print_result_pretty(body):
    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        print(body)
        return body


# ================================================================== 菜单处理函数


def switch_env():
    global BASE_URL
    print()
    for k, v in ENVIRONMENTS.items():
        mark = " ◀ 当前" if v["base_url"] == BASE_URL else ""
        print(f"    {k}. {v['name']:<6}  {v['base_url']}{mark}")
    choice = prompt("请选择环境编号").strip()
    if choice in ENVIRONMENTS:
        BASE_URL = ENVIRONMENTS[choice]["base_url"]
        print(f"  ✅ 已切换到: {ENVIRONMENTS[choice]['name']}  ({BASE_URL})")
    else:
        print("  ⚠ 无效选择，环境未切换")


def switch_account():
    global API_KEY, API_SECRET
    print()
    for k, v in ACCOUNTS.items():
        mark = " ◀ 当前" if v["api_key"] == API_KEY else ""
        print(f"    {k}. {v['name']}  (key={v['api_key']}){mark}")
    choice = prompt("请选择账号编号").strip()
    if choice in ACCOUNTS:
        API_KEY = ACCOUNTS[choice]["api_key"]
        API_SECRET = ACCOUNTS[choice]["api_secret"]
        print(f"  ✅ 已切换到: {ACCOUNTS[choice]['name']}")
    else:
        print("  ⚠ 无效选择，账号未切换")


def menu_createTask():
    task_id = prompt("task_id", "0511")
    batch_id = prompt("batch_id", "001")
    question = prompt("question", "今天哪些股票涨得好？")
    repeat_count = prompt_int("repeat_count", 10)
    platform = prompt("platform_group", "doubao_app")
    device_type = prompt("device_type", "ios")
    ask_method = prompt("ask_method", "thinking")

    scope = {
        "platform_group": [platform],
        "region": [],
        "device_type": device_type,
        "ask_method": ask_method,
    }
    body = {
        "task_id": task_id,
        "batch_id": batch_id,
        "question": question,
        "scope": scope,
        "repeat_count": repeat_count,
        "priority": 2,
    }
    resp = send("POST", "/tasks/create", json.dumps(body, ensure_ascii=False))
    print_result_pretty(resp)


def menu_queryByTaskId():
    task_id = prompt("task_id", "0511")
    resp = send("GET", f"/tasks/{task_id}/status", "")
    print_result_pretty(resp)


def menu_queryByTaskIdAndBatchId():
    task_id = prompt("task_id", "0511")
    batch_id = prompt("batch_id", "001")
    query = f"?task_id={task_id}&batch_id={batch_id}"
    resp = send("GET", f"/tasks/status{query}", "")
    print_result_pretty(resp)


def menu_updateTask():
    task_id = prompt("task_id", "0511")
    status = prompt("status (cancel/pending/...)", "cancel")
    priority = prompt_int("priority", 0)
    message = prompt("message", "测试取消")
    body = {"status": status, "priority": priority, "message": message}
    resp = send("PUT", f"/tasks/{task_id}/update", json.dumps(body, ensure_ascii=False))
    print_result_pretty(resp)


def menu_updateTaskByBatch():
    task_id = prompt("task_id", "0511")
    batch_id = prompt("batch_id", "001")
    status = prompt("status (cancel/pending/...)", "cancel")
    priority = prompt_int("priority", 0)
    message = prompt("message", "测试按 batchId 取消")
    body = {"status": status, "priority": priority, "message": message}
    resp = send(
        "PUT",
        f"/tasks/{task_id}/{batch_id}/update",
        json.dumps(body, ensure_ascii=False),
    )
    print_result_pretty(resp)


def menu_getTaskData():
    task_id = prompt("task_id", "0511")
    batch_id = prompt("batch_id", "001")
    query = f"?batch_id={batch_id}"
    resp = send("GET", f"/tasks/{task_id}/data{query}", "")
    print_result_pretty(resp)


def menu_listAllTasks():
    resp = send("GET", "/tasks", "")
    print_result_pretty(resp)


def menu_listByStatus():
    status = prompt("status (pending/in_progress/completed/failed/cancel)", "completed")
    resp = send("GET", f"/tasks?status={status}", "")
    print_result_pretty(resp)


def menu_listByTimeRange():
    start = prompt("start_time (ms 时间戳)", "1779638400000")
    end = prompt("end_time   (ms 时间戳)", "1779984000000")
    query = f"?start_time={start}&end_time={end}"
    resp = send("GET", f"/tasks{query}", "")
    try:
        data = json.loads(resp)
    except Exception:
        print(resp)
        return
    # print_result_pretty(resp)
    tasks = data.get("data") or []
    # 按 askMethod 分组
    by_ask_method = {}

    for task in tasks:
        method = task.get("askMethod", "unknown")
        by_ask_method.setdefault(method, []).append(task)

    print("\n========== 按 askMethod 汇总 ==========")
    for method, group in by_ask_method.items():
        task_count = 0
        repeat_count = 0
        total_data_count = 0

        for task in group:
            task_id = task.get("taskId", "")
            batch_id = task.get("batchId", "")

            task_resp = send("GET", f"/tasks/{task_id}/data?batch_id={batch_id}", "")
            try:
                task_data = json.loads(task_resp)
            except Exception:
                task_data = {}

            data_count = 0
            if task_data.get("code") == 0:
                for item in task_data.get("data") or []:
                    data_count += len(item.get("data") or [])

            if data_count > 0:
                task_count += 1
                repeat_count += task.get("repeatCount", 0)
                total_data_count += data_count

        print(
            f"askMethod={method:<12} 任务数={task_count}  客户下发任务数量={repeat_count}  实际上报数量={total_data_count}"
        )


def menu_listByStatusAndTimeRange():
    status = prompt("status", "completed")
    start = prompt("start_time (ms)", "1779638400000")
    end = prompt("end_time   (ms)", "1779984000000")
    query = f"?status={status}&start_time={start}&end_time={end}"
    resp = send("GET", f"/tasks{query}", "")
    print_result_pretty(resp)


def menu_statByAskMethod():
    start = prompt("start_time (ms 时间戳)", "1779638400000")
    end = prompt("end_time   (ms 时间戳)", "1779984000000")

    query = f"?start_time={start}&end_time={end}"
    result = send("GET", f"/tasks{query}", "")
    data = json.loads(result)
    tasks = data.get("data", [])

    by_ask_method = defaultdict(list)
    for task in tasks:
        by_ask_method[task.get("askMethod", "")].append(task)

    print("\n========== 按 askMethod 统计 ==========")
    for ask_method, group in by_ask_method.items():
        task_count = repeat_count = total_data_count = 0
        for task in group:
            task_data_result = send(
                "GET",
                f"/tasks/{task.get('taskId')}/data?batch_id={task.get('batchId')}",
                "",
            )
            data_json = json.loads(task_data_result)
            data_count = 0
            if data_json.get("code") == 0:
                data_count = sum(
                    len(item.get("data", [])) for item in data_json.get("data", [])
                )
            print(
                f"  id={task.get('id')} taskId={task.get('taskId')} batchId={task.get('batchId')} "
                f"question={task.get('question')} askMethod={task.get('askMethod')} "
                f"repeatCount={task.get('repeatCount')} dataCount={data_count} ctime={task.get('ctime')}"
            )
            if data_count > 0:
                task_count += 1
                repeat_count += task.get("repeatCount", 0)
                total_data_count += data_count

        print()
        print(
            f"  askMethod={ask_method:<12} 任务数={task_count}  "
            f"repeatCount数={repeat_count}  totalDataCount总数={total_data_count}"
        )


# ================================================================== 新增：发送请求并返回二进制（用于下载Excel）
def send_raw(method, path, body_json, override_signature=None):
    sign_path = BASE_URL.split("://", 1)[1].split("/", 1)[1]
    sign_path = "/" + sign_path + path
    query_idx = sign_path.find("?")
    if query_idx > 0:
        sign_path = sign_path[:query_idx]

    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    body_bytes = body_json.encode("utf-8")
    body_sha256 = sha256_hex(body_bytes)

    string_to_sign = (
        method.upper()
        + "\n"
        + sign_path
        + "\n"
        + timestamp
        + "\n"
        + nonce
        + "\n"
        + body_sha256
    )

    signature = (
        override_signature
        if override_signature is not None
        else hmac_sha256_hex(API_SECRET, string_to_sign)
    )

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "X-Api-Key": API_KEY,
        "X-Api-Timestamp": timestamp,
        "X-Api-Nonce": nonce,
        "X-Api-Signature": signature,
    }

    data = body_bytes if method.upper() != "GET" and len(body_bytes) > 0 else None
    req = urllib.request.Request(
        BASE_URL + path, data=data, headers=headers, method=method.upper()
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read()  # 直接返回二进制，不 decode
    except urllib.error.HTTPError as e:
        return e.read()
    
def menu_exportUsageByTimeRange():
    # 提示用户输入时间范围
    start_time = prompt("start_time (ms 时间戳)", "1779638400000")
    end_time = prompt("end_time   (ms 时间戳)", "1779984000000")
    
    # 构建请求参数
    query_params = f"?start_time={start_time}&end_time={end_time}"
    print(f"\n  正在请求使用量数据: GET /usage/export{query_params}")
    
    # 直接获取二进制内容（不解析JSON，不解码utf-8）
    excel_content = send_raw("GET", f"/usage/export{query_params}", "")
    
    if not excel_content:
        print("  ⚠ 未获取到数据")
        return

    # 保存为 Excel 文件
    file_timestamp = int(time.time())
    excel_file = f"./使用量统计_{file_timestamp}.xlsx"
    
    with open(excel_file, "wb") as f:
        f.write(excel_content)
    
    print(f"\n✅ 导出成功！文件已保存到：\n{excel_file}")


def menu_loadTasks():
    task_id = prompt("task_id", "6418")
    count = prompt_int("repeatCount", 30)
    load_base = "https://wkat1.tingyun.com/apptasksvr/aidz-manager/load"
    url_str = f"{load_base}/{task_id}?repeatCount={count}"
    while True:
        print(f"  POST {url_str}")
        try:
            req = urllib.request.Request(url_str, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                http_status = response.getcode()
                resp_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            http_status = e.code
            resp_body = e.read().decode("utf-8")
        except Exception as e:
            print(f"  Request error: {e}, retrying in 30s...")
            time.sleep(30)
            continue

        print(f"  HTTP {http_status} -> {resp_body}")
        success = False
        try:
            parsed = json.loads(resp_body)
            if isinstance(parsed, dict):
                success = bool(parsed.get("success"))
        except Exception:
            pass

        if success:
            break
        print("  load failed, retrying in 30s...")
        time.sleep(30)
    print("  ✅ load 成功")


def menu_invalidSignature():
    task_id = prompt("task_id", "0511")
    resp = send(
        "GET",
        f"/tasks/{task_id}/status",
        "",
        override_signature="invalid_signature_xyz",
    )
    print_result_pretty(resp)


# ================================================================== 路由

_HANDLERS = {
    action: globals()[action]
    for _, action in MENU
    if action != "quit" and action in dir()
}


def run_menu():
    actions = [action for _, action in MENU]
    while True:
        show_menu()
        choice = input("  请输入序号: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(MENU)):
            print("  ⚠ 无效输入，请重新选择")
            continue
        idx = int(choice) - 1
        action = actions[idx]
        if action == "quit":
            print("  👋 退出")
            break
        handler = globals().get(action)
        if handler:
            print()
            try:
                handler()
            except KeyboardInterrupt:
                print("\n  ↩ 已取消，返回主菜单")
        else:
            print(f"  ⚠ 未找到处理函数: {action}")


# ================================================================== HTTP 工具


def send(method, path, body_json, override_signature=None):
    sign_path = BASE_URL.split("://", 1)[1].split("/", 1)[1]
    sign_path = "/" + sign_path + path
    query_idx = sign_path.find("?")
    if query_idx > 0:
        sign_path = sign_path[:query_idx]

    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    body_bytes = body_json.encode("utf-8")
    body_sha256 = sha256_hex(body_bytes)

    string_to_sign = (
        method.upper()
        + "\n"
        + sign_path
        + "\n"
        + timestamp
        + "\n"
        + nonce
        + "\n"
        + body_sha256
    )

    signature = (
        override_signature
        if override_signature is not None
        else hmac_sha256_hex(API_SECRET, string_to_sign)
    )

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "X-Api-Key": API_KEY,
        "X-Api-Timestamp": timestamp,
        "X-Api-Nonce": nonce,
        "X-Api-Signature": signature,
    }

    data = body_bytes if method.upper() != "GET" and len(body_bytes) > 0 else None
    req = urllib.request.Request(
        BASE_URL + path, data=data, headers=headers, method=method.upper()
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8") if e.fp else ""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hmac_sha256_hex(secret: str, data: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ================================================================== 入口

if __name__ == "__main__":
    run_menu()