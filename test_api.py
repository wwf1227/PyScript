import os
import json
import random
import time
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__)

UPLOAD_DIR = "/var/www/uploads"
DOWNLOAD_DIR = "/var/www/downloads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

@app.route('/api/hello', methods=['GET'])
def hello():
    return jsonify({"msg": "ok", "port": request.environ.get('SERVER_PORT'), "method": "GET"})

@app.route('/api/echo', methods=['POST', 'PUT', 'DELETE'])
def echo():
    data = {
        "method": request.method,
        "headers": dict(request.headers),
        "args": request.args.to_dict(),
        "form": request.form.to_dict(),
        "json": request.json if request.is_json else None,
        "port": request.environ.get('SERVER_PORT')
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
        "port": request.environ.get('SERVER_PORT')
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

# 模拟状态码
@app.route('/api/status/<int:code>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def status_code(code):
    if 400 <= code <= 599:
        return jsonify({
            "error": True,
            "status": code,
            "message": f"Simulated HTTP {code} error"
        }), code
    else:
        return jsonify({"error": "Status code must be between 400 and 599"}), 400

# 模拟延迟
@app.route('/api/delay/<int:seconds>', methods=['GET'])
def delay(seconds):
    if seconds <= 0 or seconds > 60:
        return jsonify({"error": "Delay must be 1-60 seconds"}), 400
    time.sleep(seconds)
    return jsonify({
        "result": "ok",
        "delayed_seconds": seconds,
        "message": f"Response delayed by {seconds} seconds"
    })

# 随机错误（支持 200, 404, 500, 502, 超时）
@app.route('/api/random-error', methods=['GET'])
def random_error():
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
        time.sleep(20)  # 需大于 Nginx 的 proxy_read_timeout
        return jsonify({"result": "ok", "status": 200})
    
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, threaded=True)