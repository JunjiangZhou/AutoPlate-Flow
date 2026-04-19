# -*- coding: UTF-8 -*-
"""
停车场容量检测模块（重构版）
特性：线程化运行、停止控制、动态定价
"""
import cv2
import time
import threading
from ultralytics import YOLO
from PIL import Image, ImageTk
from tkinter import filedialog

from utils.logger import get_logger
from utils.database import Database
from config import (
    PARKING_MODEL_PATH, DB_WRITE_INTERVAL, VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT
)

logger = get_logger(__name__)

_db = Database()


def insert_hourly_rate_into_db(hourly_rate):
    _db.insert_hourly_rate(hourly_rate)


def _parking_detection_loop(label, stop_event, pause_event):
    """容量检测循环（在独立线程中运行）"""
    logger.info("加载容量检测模型: %s", PARKING_MODEL_PATH)
    model = YOLO(PARKING_MODEL_PATH)
    class_names = ['empty', 'occupied']

    confidence_threshold = 0.1
    iou_threshold = 0.2
    max_detections = 100

    # 从数据库读取动态费率设置
    base_hourly_rate = _db.get_setting('base_hourly_rate', 10.0)
    rate_high_multiplier = _db.get_setting('rate_high_multiplier', 1.5)
    rate_low_multiplier = _db.get_setting('rate_low_multiplier', 0.8)
    occupancy_high_threshold = _db.get_setting('occupancy_high_threshold', 80.0)
    occupancy_low_threshold = _db.get_setting('occupancy_low_threshold', 50.0)

    hourly_rate = base_hourly_rate
    last_db_write_time = time.time()

    video_path = filedialog.askopenfilename(
        title="选择视频文件",
        filetypes=(("MP4文件", "*.mp4"), ("所有文件", "*.*"))
    )
    if not video_path:
        logger.info("未选择视频文件，取消容量检测")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("无法打开视频: %s", video_path)
        return

    def update_frame():
        nonlocal hourly_rate, last_db_write_time

        if stop_event.is_set():
            cap.release()
            logger.info("容量检测已停止")
            return

        if pause_event.is_set():
            label.after(100, update_frame)
            return

        ret, frame = cap.read()
        if not ret:
            cap.release()
            logger.info("容量检测视频播放结束")
            return

        results = model.predict(frame, conf=confidence_threshold, iou=iou_threshold, max_det=max_detections, verbose=False)

        empty_count = 0
        occupied_count = 0

        for result in results:
            for bbox in result.boxes:
                x1, y1, x2, y2 = map(int, bbox.xyxy[0])
                cls_id = int(bbox.cls[0])
                label_text = class_names[cls_id]
                if label_text == 'empty':
                    empty_count += 1
                elif label_text == 'occupied':
                    occupied_count += 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)

        total_slots = empty_count + occupied_count
        if total_slots > 0:
            occupied_percentage = (occupied_count / total_slots) * 100
        else:
            occupied_percentage = 0

        if occupied_percentage > occupancy_high_threshold:
            hourly_rate = base_hourly_rate * rate_high_multiplier
        elif occupancy_low_threshold < occupied_percentage <= occupancy_high_threshold:
            hourly_rate = base_hourly_rate
        else:
            hourly_rate = base_hourly_rate * rate_low_multiplier

        current_time = time.time()
        if current_time - last_db_write_time >= DB_WRITE_INTERVAL:
            insert_hourly_rate_into_db(hourly_rate)
            logger.info("动态费率更新: %.2f (占用率: %.1f%%)", hourly_rate, occupied_percentage)
            last_db_write_time = current_time

        cv2.putText(frame, f'Occupied: {occupied_percentage:.2f}%', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        cv2.putText(frame, f'Hourly Rate: {hourly_rate:.2f}', (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(frame, f'Empty: {empty_count} / Total: {total_slots}', (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        frame = cv2.resize(frame, (VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)

        label.imgtk = imgtk
        label.configure(image=imgtk)
        label.after(30, update_frame)

    update_frame()


def parking_detection(label, stop_event=None, pause_event=None):
    """
    启动容量检测（线程安全，不阻塞主线程）
    """
    if stop_event is None:
        stop_event = threading.Event()
    if pause_event is None:
        pause_event = threading.Event()

    thread = threading.Thread(
        target=_parking_detection_loop,
        args=(label, stop_event, pause_event),
        daemon=True
    )
    thread.start()
    logger.info("容量检测线程已启动")
    return stop_event, pause_event
