# -*- coding: UTF-8 -*-
"""项目统一配置文件"""
import os

# ================== 模型配置 ==================
DETECT_MODEL_PATH = os.environ.get("DETECT_MODEL", "weights/plate_detect.pt")
REC_MODEL_PATH = os.environ.get("REC_MODEL", "weights/plate_rec_color.pth")
PARKING_MODEL_PATH = os.environ.get("PARKING_MODEL", "best.pt")
IMG_SIZE = 640
CONF_THRES = 0.3
IOU_THRES = 0.5

# ================== 推理优化 ==================
SKIP_FRAMES = 3               # 每 N 帧检测一次（跳帧）
USE_GPU = True                # 是否优先使用 GPU

# ================== 数据库配置 ==================
DB_PATH = "parking_system.db"

# ================== 停车场计费 ==================
BASE_HOURLY_RATE = 10.0       # 基础每小时收费
RATE_HIGH_MULTIPLIER = 1.5    # 占用率>80%时的倍率
RATE_LOW_MULTIPLIER = 0.8     # 占用率<50%时的倍率
DB_WRITE_INTERVAL = 10        # 动态费率写入数据库间隔(秒)

# ================== 视频与摄像头 ==================
DEFAULT_VIDEO_PATH = ""
RTSP_TIMEOUT = 5              # RTSP 流连接超时(秒)

# ================== 日志配置 ==================
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ================== 跟踪与去重配置 ==================
TRACK_IOU_THRESHOLD = 0.35       # IoU 匹配阈值（小于此值视为不同目标）
TRACK_MAX_LOST = 8               # 连续丢失 N 帧后目标消失
TRACK_CONFIRM_MIN_FRAMES = 4     # 至少积累 N 帧识别记录才做投票确认
TRACK_COOLDOWN_SECONDS = 5       # 同一车牌确认后的冷却时间（秒）

# ================== GUI 配置 ==================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
VIDEO_DISPLAY_WIDTH = 400
VIDEO_DISPLAY_HEIGHT = 300
REFRESH_INTERVAL = 5000       # 数据库表格刷新间隔(ms)
