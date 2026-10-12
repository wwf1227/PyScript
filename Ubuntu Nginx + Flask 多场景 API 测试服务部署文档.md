# Ubuntu Nginx + Flask 多场景 API 测试服务部署文档（完整版）

本文档详细记录在 Ubuntu 上搭建一套支持 **SSL Pinning（单向 TLS）**、**mTLS（双向 TLS）**、**HTTP 状态码模拟**、**超时模拟** 等多种测试场景的 API 测试服务，为 Android App 提供全面的网络测试接口。

---

## 一、服务架构

```
Android App
    │
    ├─ 访问 8453 (SSL Pinning)  ────┐
    └─ 访问 8454 (mTLS)       ────┘
                              │
                          Nginx (反向代理 + 超时控制)
                              │
                          Flask 后端 (127.0.0.1:5000)
                              │
                     /var/www/uploads/   (上传文件存放)
                     /var/www/downloads/ (下载文件存放)
```

---

## 二、Nginx 配置

### 2.1 证书准备

将以下证书文件放置于 `/etc/nginx/ssl/`（需 root 权限）：

- `fullchain.crt` — 服务端证书完整链（含中间证书）
- `server.key` — 服务端私钥
- `ca.crt` — 用于签发客户端证书的根 CA（mTLS 使用）

设置权限：
```bash
sudo chmod 644 /etc/nginx/ssl/*.crt
sudo chmod 600 /etc/nginx/ssl/*.key
```

### 2.2 站点配置文件

编辑 `/etc/nginx/sites-available/tls-demo.conf`：

```nginx
# 端口 8453 - 单向 TLS（SSL Pinning 测试）
server {
    listen 8453 ssl http2;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/fullchain.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    ssl_verify_client off;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # ===== 超时设置（用于测试异常场景） =====
        proxy_connect_timeout 5s;   # 连接超时（后端无响应时触发 504）
        proxy_read_timeout 10s;     # 读取超时（后端处理超时触发 504）
        proxy_send_timeout 10s;     # 发送超时（很少用到）
    }
}

# 端口 8454 - 双向 TLS（mTLS）
server {
    listen 8454 ssl http2;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/fullchain.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    ssl_client_certificate /etc/nginx/ssl/ca.crt;
    ssl_verify_client on;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # ===== 超时设置（与 8453 保持一致） =====
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
        proxy_send_timeout 10s;
    }
}
```

### 2.3 启用配置并重启 Nginx

```bash
sudo ln -s /etc/nginx/sites-available/tls-demo.conf /etc/nginx/sites-enabled/
sudo nginx -t                    # 检查语法
sudo systemctl start nginx       # 启动
sudo systemctl enable nginx      # 开机自启
sudo nginx -s reload             # 重新加载（若已运行）
```

---

## 三、Flask 后端服务

### 3.1 安装依赖

```bash
sudo apt update
sudo apt install python3-pip -y
pip3 install flask flask-cors
```

### 3.2 创建目录

```bash
sudo mkdir -p /var/www/uploads /var/www/downloads
sudo chown -R $USER:$USER /var/www/uploads /var/www/downloads
```

### 3.3 后端代码

保存为 `/home/aib/test_api.py`（根据实际用户调整路径）：

```python
import os
import json
import time
import random
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__)

UPLOAD_DIR = "/var/www/uploads"
DOWNLOAD_DIR = "/var/www/downloads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024   # 100MB

# ------------------- 基础接口 -------------------
@app.route('/api/hello', methods=['GET'])
def hello():
    port = request.headers.get('X-Forwarded-Port', 'unknown')
    tls_mode = "mTLS" if port == "8454" else "SSL Pinning"
    return jsonify({
        "msg": "ok",
        "port": port,
        "method": "GET",
        "tls_mode": tls_mode
    })

@app.route('/api/echo', methods=['POST', 'PUT', 'DELETE'])
def echo():
    port = request.headers.get('X-Forwarded-Port', 'unknown')
    data = {
        "method": request.method,
        "headers": dict(request.headers),
        "args": request.args.to_dict(),
        "form": request.form.to_dict(),
        "json": request.json if request.is_json else None,
        "port": port
    }
    return jsonify(data)

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    safe_name = os.path.basename(file.filename)
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    file.save(save_path)
    return jsonify({
        "result": "upload ok",
        "filename": safe_name,
        "size": os.path.getsize(save_path),
        "port": request.headers.get('X-Forwarded-Port', 'unknown')
    })

@app.route('/api/download/<filename>', methods=['GET'])
def download(filename):
    safe_name = os.path.basename(filename)
    file_path = os.path.join(DOWNLOAD_DIR, safe_name)
    if not os.path.exists(file_path):
        abort(404)
    return send_from_directory(DOWNLOAD_DIR, safe_name, as_attachment=True)

@app.route('/api/generate/<int:size_mb>', methods=['GET'])
def generate_file(size_mb):
    if size_mb <= 0 or size_mb > 100:
        return jsonify({"error": "Size must be 1-100 MB"}), 400
    filename = f"test_{size_mb}MB.bin"
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    os.system(f"dd if=/dev/zero of={file_path} bs=1M count={size_mb} 2>/dev/null")
    return jsonify({"result": "generated", "filename": filename, "size_mb": size_mb})

# ------------------- 异常模拟接口 -------------------
@app.route('/api/status/<int:code>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def status_code(code):
    """返回指定的 HTTP 状态码（400-599）"""
    if 400 <= code <= 599:
        return jsonify({
            "error": True,
            "status": code,
            "message": f"Simulated HTTP {code} error"
        }), code
    else:
        return jsonify({"error": "Status code must be between 400 and 599"}), 400

@app.route('/api/delay/<int:seconds>', methods=['GET'])
def delay(seconds):
    """模拟响应延迟（1-60秒），用于测试读取超时"""
    if seconds <= 0 or seconds > 60:
        return jsonify({"error": "Delay must be 1-60 seconds"}), 400
    time.sleep(seconds)
    return jsonify({
        "result": "ok",
        "delayed_seconds": seconds,
        "message": f"Response delayed by {seconds} seconds"
    })

@app.route('/api/random-error', methods=['GET'])
def random_error():
    """随机返回 200、404、500、502 或延迟 20 秒（触发超时）"""
    choice = random.choice(['200', '404', '500', '502', 'delay'])
    if choice == '200':
        return jsonify({"result": "ok", "status": 200})
    elif choice == '404':
        return jsonify({"error": "Not Found", "status": 404}), 404
    elif choice == '500':
        return jsonify({"error": "Internal Server Error", "status": 500}), 500
    elif choice == '502':
        return jsonify({"error": "Bad Gateway", "status": 502}), 502
    else:  # delay
        time.sleep(20)   # 大于 Nginx proxy_read_timeout（10s），触发 504
        return jsonify({"result": "ok", "status": 200})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, threaded=True)
```

### 3.4 测试手动运行

```bash
cd /home/aib
python3 test_api.py &
curl http://127.0.0.1:5000/api/hello
# 应返回 JSON
```

---

## 四、配置 Flask 为系统服务（开机自启）

### 4.1 创建 systemd 单元

使用 `sudo` 编辑 `/etc/systemd/system/flask-test-api.service`：

```ini
[Unit]
Description=Flask Test API for SSL Pinning and mTLS
After=network.target

[Service]
User=aib                          # 替换为实际用户名
WorkingDirectory=/home/aib
Environment="PATH=/home/aib/miniconda3/envs/agent/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/aib/miniconda3/envs/agent/bin/python3 /home/aib/test_api.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> **注意**：`User`、`WorkingDirectory`、`ExecStart` 中的路径必须与实际一致，特别是 Python 解释器路径（若使用 conda 环境）。

### 4.2 启动并启用

```bash
sudo systemctl daemon-reload
sudo systemctl enable flask-test-api.service
sudo systemctl start flask-test-api.service
sudo systemctl status flask-test-api.service   # 检查状态
```

### 4.3 常用管理命令

```bash
sudo systemctl restart flask-test-api   # 修改代码后重启
sudo journalctl -u flask-test-api -f    # 查看实时日志
```

---

## 五、Android 端 `CommonNetHelper` 完整代码

已在项目中集成，支持：
- GET / POST JSON / 文件上传 / 文件下载
- 证书校验控制（忽略证书、SSL‑Pinning、mTLS）
- HTTP 版本可选（自动协商、仅 HTTP/1.1、仅 HTTP/2）
- 进度回调（上传/下载）
- 异常状态码捕获（`HttpStatusException`）

关键 API：
```kotlin
val config = helper.buildConfig(
    useHttpDefault = true/false,
    useHttp11 = true/false,
    useHttp2 = true/false,
    ignoreCert = true/false,
    sslPinning = Pair(host, pin) or null,
    mtls = MTLSConfig(...) or null,
    context = this
)

helper.get(url, config, callback)
helper.postJson(url, json, config, callback)
helper.uploadFile(url, file, fieldName, config, callback)
helper.downloadFile(url, targetFile, config, callback)
```

---

## 六、Activity 界面设计（`TlsTestActivity`）

### 6.1 UI 功能布局

- **URL 输入**（支持任意路径）
- **请求方法**：GET / POST JSON / 上传 / 下载
- **认证模式**：普通 HTTPS / 忽略证书 / SSL‑Pinning / mTLS
  - 选择 SSL‑Pinning 时显示 Pin 输入框
  - 选择 mTLS 时显示已加载证书信息
- **HTTP 版本**：自动协商 / 仅 HTTP/1.1 / 仅 HTTP/2
- **参数输入**：JSON 体（POST）、文件选择（上传）、保存路径（下载）
- **操作按钮**：发起请求、清空日志
- **进度条**：上传/下载进度
- **日志区域**：显示状态码、响应体、错误详情

### 6.2 核心逻辑

- 根据 UI 选项构建 `NetConfig`
- 调用 `CommonNetHelper` 对应方法
- 处理回调更新 UI（成功/失败/进度）
- 支持文件选择（通过 `ActivityResultContracts.GetContent`）

---

## 七、API 调用示例与测试场景

### 7.1 基础功能接口

| 功能 | 方法 | URL 示例 | 说明 |
|------|------|----------|------|
| Hello | GET | `/api/hello` | 返回服务端口和 TLS 模式 |
| Echo | POST/PUT/DELETE | `/api/echo?foo=bar` | 回显请求详情 |
| 上传 | POST | `/api/upload` | 上传文件（multipart） |
| 下载 | GET | `/api/download/filename` | 下载指定文件 |
| 生成测试文件 | GET | `/api/generate/10` | 生成 10MB 零填充文件 |

### 7.2 异常模拟接口

| 场景 | 方法 | URL 示例 | 预期结果 |
|------|------|----------|----------|
| 404 Not Found | GET | `/api/status/404` | 返回 404 JSON，Android 捕获 `HttpStatusException(404)` |
| 500 Internal Error | GET | `/api/status/500` | 返回 500 JSON，捕获 `HttpStatusException(500)` |
| 502 Bad Gateway | GET | `/api/status/502` | 返回 502 JSON，捕获 `HttpStatusException(502)` |
| 响应延迟（超时） | GET | `/api/delay/20` | 延迟 20 秒，Nginx 10 秒后返回 504，捕获 `HttpStatusException(504)` 或 `SocketTimeoutException` |
| 随机错误 | GET | `/api/random-error` | 随机返回 200/404/500/502 或触发超时，测试鲁棒性 |

### 7.3 超时触发机制

- **连接超时**（`proxy_connect_timeout=5s`）：停止 Flask 服务，请求任意 `/api/` 路径，5 秒后返回 504。
- **读取超时**（`proxy_read_timeout=10s`）：调用 `/api/delay/20`，10 秒后返回 504。

### 7.4 完整测试脚本（curl）

```bash
#!/bin/bash
SERVER="https://your-server-ip"
PORT_SSL=8453
PORT_MTLS=8454

# 普通 GET
curl -k "$SERVER:$PORT_SSL/api/hello"

# 404 测试
curl -k "$SERVER:$PORT_SSL/api/status/404"

# 超时测试
curl -k "$SERVER:$PORT_SSL/api/delay/20"

# 上传测试
curl -k -X POST -F "file=@test.bin" "$SERVER:$PORT_SSL/api/upload"

# mTLS 下载
curl -k --cert client.crt --key client.key -O "$SERVER:$PORT_MTLS/api/download/test_5MB.bin"
```

---

## 八、故障排查

| 问题现象 | 可能原因 | 解决方法 |
|---------|---------|----------|
| Nginx 无法启动 | 证书路径错误 / 端口占用 | `sudo nginx -t` 检查，查看 `/var/log/nginx/error.log` |
| Flask 服务启动失败 | 用户不存在 / 路径错误 | 检查 systemd 中的 `User` 和 `ExecStart`，`sudo journalctl -u flask-test-api` |
| 上传 413 错误 | 文件超过 100MB | 检查 Nginx `client_max_body_size` 和后端 `MAX_CONTENT_LENGTH` |
| mTLS 返回 400 | 客户端证书无效或未提供 | 确认证书由 `ca.crt` 签发，且请求携带 `--cert` |
| 下载 404 | 文件不存在 | 先调用 `/api/generate` 生成文件 |
| 504 Gateway Timeout | 后端延迟或未启动 | 检查 Flask 状态，调整 `proxy_*_timeout` |
| SSL 错误（Trust anchor） | 自签名证书未被信任 | 在 App 中选择“忽略证书”或“SSL‑Pinning”模式 |

---

## 九、文件目录结构

```
/
├── etc/
│   └── nginx/
│       ├── sites-available/tls-demo.conf
│       └── ssl/
│           ├── fullchain.crt
│           ├── server.key
│           └── ca.crt
├── home/aib/
│   └── test_api.py
├── var/www/
│   ├── uploads/        (上传文件存放)
│   └── downloads/      (下载文件存放)
└── etc/systemd/system/
    └── flask-test-api.service
```

---

## 十、总结

通过本部署，您获得了一套功能全面的网络测试服务：

- **两个端口**（8453/8454）分别提供 SSL Pinning 和 mTLS 认证，便于 App 对比测试。
- **丰富的 API 端点**：支持 GET、POST、上传、下载、回显、文件生成。
- **异常模拟**：覆盖 4xx/5xx 状态码和超时场景，帮助完善 App 错误处理。
- **灵活配置**：Android 端可自由组合认证模式、HTTP 版本、证书校验。
- **自动化**：Flask 作为 systemd 服务开机自启，稳定可靠。

您可以根据测试需求随时扩展后端接口或调整 Nginx 参数，满足各种网络测试场景。

---

**文档版本**：2.0  
**更新日期**：2026-09-09  
**更新内容**：新增异常模拟接口、Nginx 超时配置、Android 完整实现。