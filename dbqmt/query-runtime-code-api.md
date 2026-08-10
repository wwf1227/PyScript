# 查询运行时股票代码 API 文档

## 1. 基本信息

| 项 | 内容 |
|---|---|
| 接口名称 | 查询运行时股票代码 |
| 接口路径 | `/apptasksvr/stock-manager/query-runtime-code` |
| 请求方式 | `GET` |
| 请求格式 | — |
| 响应格式 | `application/json` |
| 是否需要鉴权 | 待确认 |
| 接口描述 | 获取当前运行时生效的股票代码列表，以及该列表的最后更新时间 |

---

## 2. 请求参数

### 2.1 Path 参数

无。

### 2.2 Query 参数

无。

### 2.3 Header 参数

无（如服务端有统一鉴权，请补充 `Authorization` 等字段）。

---

## 3. 响应参数

### 3.1 外层结构

| 字段 | 类型 | 必返 | 说明 |
|---|---|---|---|
| `success` | boolean | 是 | 请求是否成功。`true` 表示业务处理成功 |
| `message` | string | 是 | 提示信息。成功时为空字符串，失败时为错误原因 |
| `data` | object | 是 | 业务数据对象，失败时可能为 `null` |

### 3.2 `data` 对象

| 字段 | 类型 | 必返 | 说明 |
|---|---|---|---|
| `lastUpdateTime` | long | 是 | 股票代码列表最后一次更新的时间戳（毫秒） |
| `stockCode` | string[] | 是 | 股票代码列表。无数据时返回空数组 `[]`，不返回 `null` |

---

## 4. 响应示例

### 4.1 成功

```json
{
    "success": true,
    "message": "",
    "data": {
        "lastUpdateTime": 1754784000000,
        "stockCode": [
            "600519.SH",
            "000001.SZ"
        ]
    }
}
```

### 4.2 成功（列表为空）

```json
{
    "success": true,
    "message": "",
    "data": {
        "lastUpdateTime": 1754784000000,
        "stockCode": []
    }
}
```

### 4.3 失败

```json
{
    "success": false,
    "message": "runtime code not initialized",
    "data": null
}
```

---

## 5. 调用示例

```python
import requests

resp = requests.get(
    "http://{host}/apptasksvr/stock-manager/query-runtime-code",
    timeout=5,
)
result = resp.json()

if result.get("success"):
    data = result["data"]
    last_update_time = data["lastUpdateTime"]
    stock_codes = data["stockCode"]
else:
    raise RuntimeError(result.get("message"))
```
