import cv2
from ultralytics import YOLO
from PIL import Image, ImageTk
from tkinter import filedialog
import time
import sqlite3


def insert_hourly_rate_into_db(hourly_rate):
    conn = sqlite3.connect('parking_system.db')
    c = conn.cursor()

    # 插入新的 hourly_rate 记录
    c.execute('''
        INSERT INTO hourly_rates (rate)
        VALUES (?)
    ''', (hourly_rate,))

    conn.commit()
    conn.close()


def parking_detection(label):
    # 加载模型
    model = YOLO('best.pt')
    class_names = ['empty', 'occupied']

    # 参数设置
    confidence_threshold = 0.1  # 低置信度阈值
    iou_threshold = 0.2  # 高IoU阈值
    max_detections = 100  # 最大检测数

    # 动态定价相关参数
    base_hourly_rate = 10  # 基础每小时收费
    hourly_rate = base_hourly_rate  # 每小时收费（可变）
    last_db_write_time = time.time()  # 用于记录上一次写入数据库的时间

    # 打开文件选择对话框，让用户选择视频文件
    video_path = filedialog.askopenfilename(title="选择视频文件",
                                            filetypes=(("MP4文件", "*.mp4"), ("所有文件", "*.*")))
    if not video_path:
        print("未选择文件，操作取消。")
        return

    # 打开选择的视频文件
    cap = cv2.VideoCapture(video_path)

    def update_frame():
        nonlocal hourly_rate, last_db_write_time  # 让内部函数能够修改外部的 hourly_rate 和 last_db_write_time

        ret, frame = cap.read()
        if not ret:
            cap.release()
            return

        # 对帧进行检测
        results = model.predict(frame, conf=confidence_threshold, iou=iou_threshold, max_det=max_detections)

        # 记录空车位和被占车位的数量
        empty_count = 0
        occupied_count = 0

        # 解析结果并绘制检测框
        for result in results:
            for bbox in result.boxes:
                x1, y1, x2, y2 = map(int, bbox.xyxy[0])
                cls_id = int(bbox.cls[0])
                label_text = class_names[cls_id]  # 用另一个名字避免与 `label` 参数冲突
                # 根据检测类别计数
                if label_text == 'empty':
                    empty_count += 1
                elif label_text == 'occupied':
                    occupied_count += 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)

        # 计算被占车位百分比
        total_slots = empty_count + occupied_count
        if total_slots > 0:
            occupied_percentage = (occupied_count / total_slots) * 100
        else:
            occupied_percentage = 0

        # 动态调整收费标准
        if occupied_percentage > 80:
            hourly_rate = base_hourly_rate * 1.5  # 占用率 > 80%，增加50%的收费
        elif 50 < occupied_percentage <= 80:
            hourly_rate = base_hourly_rate  # 占用率在 50%-80% 之间，保持标准收费
        else:
            hourly_rate = base_hourly_rate * 0.8  # 占用率 < 50%，降低收费到80%

        # 检查是否已经过了10秒，决定是否写入数据库
        current_time = time.time()
        if current_time - last_db_write_time >= 10:
            insert_hourly_rate_into_db(hourly_rate)
            print(f"Hourly rate {hourly_rate} written to database.")
            last_db_write_time = current_time  # 更新上次写入数据库的时间

        # 在画面上显示当前的占用百分比和动态每小时收费
        cv2.putText(frame, f'Occupied: {occupied_percentage:.2f}%', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (255, 0, 0), 2)
        cv2.putText(frame, f'Hourly Rate: {hourly_rate:.2f}', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 255, 255), 2)

        # 将帧缩放到固定大小
        fixed_width, fixed_height = 400, 300
        frame = cv2.resize(frame, (fixed_width, fixed_height))

        # 将帧从 BGR 转换为 RGB 格式
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # 将帧转换为 Image 对象
        img = Image.fromarray(frame)

        # 将 Image 对象转换为 ImageTk 对象
        imgtk = ImageTk.PhotoImage(image=img)

        # 在 Label 中显示
        label.imgtk = imgtk
        label.configure(image=imgtk)

        # 继续更新帧
        label.after(10, update_frame)

    update_frame()