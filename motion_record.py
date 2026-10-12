import cv2
import time
import os

# ====================== 配置区 ======================
CAMERA_INDEX = 0
SENSITIVITY = 25         # 灵敏度越小越敏感
MIN_AREA = 600           # 最小运动面积过滤噪点
SAVE_FOLDER = "motion_videos"
COOLDOWN_SEC = 1         # 两次事件最小间隔
POST_RECORD_SEC = 2      # 运动消失后继续录制多少秒
SHOW_WINDOW = True
FPS = 15                 # 输出视频帧率
VIDEO_RES = (640, 480)   # 输出视频分辨率
# ====================================================

if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

cap = cv2.VideoCapture(CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_RES[0])
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_RES[1])
cap.set(cv2.CAP_PROP_FPS, FPS)

if not cap.isOpened():
    print("无法打开摄像头，尝试修改 CAMERA_INDEX")
    exit(1)

# 初始化背景
ret, background = cap.read()
if not ret:
    print("读取摄像头失败")
    cap.release()
    exit(1)
background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
background = cv2.GaussianBlur(background, (21, 21), 0)

last_trigger_time = 0
recording = False
video_writer = None
motion_lost_time = None

fourcc = cv2.VideoWriter_fourcc(*'mp4v')

print("运动检测录像启动，q键退出")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    diff = cv2.absdiff(background, gray)
    _, thresh = cv2.threshold(diff, SENSITIVITY, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    has_motion = False
    for cnt in contours:
        if cv2.contourArea(cnt) > MIN_AREA:
            has_motion = True
            break

    now = time.time()

    # 检测到运动
    if has_motion:
        motion_lost_time = None
        if not recording and (now - last_trigger_time) > COOLDOWN_SEC:
            # 新建视频文件
            filename = os.path.join(SAVE_FOLDER, f"motion_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
            video_writer = cv2.VideoWriter(filename, fourcc, FPS, VIDEO_RES)
            recording = True
            last_trigger_time = now
            print(f"检测运动，开始录制：{filename}")

        if recording and video_writer is not None:
            video_writer.write(frame)

        # 更新背景，适应光线缓慢变化
        background = gray.copy()

    else:
        # 没有运动，若正在录制，等待 POST_RECORD_SEC 后停止
        if recording:
            if motion_lost_time is None:
                motion_lost_time = now
            elapsed = now - motion_lost_time
            if elapsed < POST_RECORD_SEC:
                # 继续写完剩余几秒
                if video_writer:
                    video_writer.write(frame)
            else:
                # 停止录制
                print("运动消失，结束录像")
                recording = False
                if video_writer is not None:
                    video_writer.release()
                    video_writer = None

    if SHOW_WINDOW:
        cv2.imshow("preview", frame)
        cv2.imshow("motion_mask", thresh)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

# 退出清理
if video_writer is not None:
    video_writer.release()
cap.release()
cv2.destroyAllWindows()
print("程序退出")
