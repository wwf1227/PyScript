import cv2
import time
import os

# ----------------配置参数----------------
CAMERA_INDEX = 0          # USB摄像头编号，多个摄像头就改成1,2
SENSITIVITY = 25          # 运动灵敏度，数值越小越敏感(0‑255)
MIN_AREA = 500            # 触发变化的最小物体面积，过滤小噪点
SAVE_FOLDER = "motion_photos"  # 照片保存文件夹
COOLDOWN_SEC = 2          # 连拍冷却，避免一秒拍很多张
SHOW_WINDOW = True        # 是否显示预览窗口
# ----------------------------------------

# 创建保存目录
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print("无法打开摄像头，请检查USB接口，CAMERA_INDEX是否正确")
    exit(1)

# 读取第一帧作为背景参考
ret, background = cap.read()
if not ret:
    print("读取摄像头画面失败")
    cap.release()
    exit(1)

background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
background = cv2.GaussianBlur(background, (21, 21), 0)

last_capture_time = 0

print("开始运动检测，按 q 退出程序")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    # 计算帧差异
    diff = cv2.absdiff(background, gray)
    _, thresh = cv2.threshold(diff, SENSITIVITY, 255, cv2.THRESH_BINARY)

    # 膨胀，消除噪点
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    motion_detected = False
    for cnt in contours:
        if cv2.contourArea(cnt) > MIN_AREA:
            motion_detected = True
            break

    now = time.time()
    if motion_detected and (now - last_capture_time) > COOLDOWN_SEC:
        # 发生运动，保存图片
        filename = os.path.join(SAVE_FOLDER, f"motion_{time.strftime('%Y%m%d_%H%M%S')}.jpg")
        cv2.imwrite(filename, frame)
        print(f"检测到变化，已拍照：{filename}")
        last_capture_time = now

        # 更新背景帧，适应光线缓慢变化
        background = gray.copy()

    if SHOW_WINDOW:
        cv2.imshow("preview", frame)
        cv2.imshow("diff", thresh)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()
print("程序结束")
