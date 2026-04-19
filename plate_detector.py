# -*- coding: UTF-8 -*-
"""
车牌检测与识别核心模块（重构版）
支持：本地视频、摄像头实时流、RTSP 流
特性：模型缓存、跳帧检测、暂停/停止控制
"""
import os
import cv2
import time
import copy
import numpy as np
import torch
from PIL import ImageTk
from concurrent.futures import ThreadPoolExecutor

from models.experimental import attempt_load
from utils.datasets import letterbox
from utils.general import check_img_size, non_max_suppression_face, scale_coords
from utils.cv_puttext import cv2ImgAddText
from utils.logger import get_logger
from config import (
    DETECT_MODEL_PATH, REC_MODEL_PATH, IMG_SIZE, CONF_THRES, IOU_THRES,
    SKIP_FRAMES, USE_GPU, VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT
)
from plate_recognition.plate_rec import get_plate_result, init_model, cv_imread
from plate_recognition.double_plate_split_merge import get_split_merge
from resultnumberdoing import PlateDatabaseManager
from utils.plate_tracker import PlateTracker

logger = get_logger(__name__)

clors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
danger = ['危', '险']

_db_manager = PlateDatabaseManager()

# 为跟踪ID分配稳定颜色（循环使用）
TRACK_COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255),
    (255, 0, 255), (128, 0, 128), (255, 165, 0), (0, 128, 128), (128, 128, 0)
]


class ModelCache:
    """模型单例缓存，避免重复加载"""
    _detect_model = None
    _rec_model = None
    _device = None
    _is_color = True

    @classmethod
    def get_device(cls):
        if cls._device is None:
            cls._device = torch.device("cuda" if torch.cuda.is_available() and USE_GPU else "cpu")
            logger.info("使用设备: %s", cls._device)
        return cls._device

    @classmethod
    def get_detect_model(cls, force_reload=False):
        if cls._detect_model is None or force_reload:
            device = cls.get_device()
            logger.info("加载检测模型: %s", DETECT_MODEL_PATH)
            cls._detect_model = attempt_load(DETECT_MODEL_PATH, map_location=device)
            cls._detect_model = cls._detect_model.float().fuse().eval()
            total = sum(p.numel() for p in cls._detect_model.parameters())
            logger.info("检测模型参数量: %.2fM", total / 1e6)
        return cls._detect_model

    @classmethod
    def get_rec_model(cls, is_color=True, force_reload=False):
        if cls._rec_model is None or cls._is_color != is_color or force_reload:
            device = cls.get_device()
            logger.info("加载识别模型: %s", REC_MODEL_PATH)
            cls._rec_model = init_model(device, REC_MODEL_PATH, is_color=is_color)
            cls._is_color = is_color
            total = sum(p.numel() for p in cls._rec_model.parameters())
            logger.info("识别模型参数量: %.2fM", total / 1e6)
        return cls._rec_model

    @classmethod
    def warmup(cls):
        """预热模型，减少首次推理延迟"""
        device = cls.get_device()
        dummy = torch.zeros(1, 3, IMG_SIZE, IMG_SIZE, device=device)
        with torch.no_grad():
            _ = cls.get_detect_model()(dummy)
        logger.info("模型预热完成")


def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def four_point_transform(image, pts):
    rect = pts.astype('float32')
    (tl, tr, br, bl) = rect
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))
    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    return warped


def scale_coords_landmarks(img1_shape, coords, img0_shape, ratio_pad=None):
    if ratio_pad is None:
        gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
        pad = ((img1_shape[1] - img0_shape[1] * gain) / 2, (img1_shape[0] - img0_shape[0] * gain) / 2)
    else:
        gain = ratio_pad[0][0]
        pad = ratio_pad[1]

    coords[:, [0, 2, 4, 6]] -= pad[0]
    coords[:, [1, 3, 5, 7]] -= pad[1]
    coords[:, :8] /= gain
    coords[:, 0].clamp_(0, img0_shape[1])
    coords[:, 1].clamp_(0, img0_shape[0])
    coords[:, 2].clamp_(0, img0_shape[1])
    coords[:, 3].clamp_(0, img0_shape[0])
    coords[:, 4].clamp_(0, img0_shape[1])
    coords[:, 5].clamp_(0, img0_shape[0])
    coords[:, 6].clamp_(0, img0_shape[1])
    coords[:, 7].clamp_(0, img0_shape[0])
    return coords


def get_plate_rec_landmark(img, xyxy, conf, landmarks, class_num, device, plate_rec_model, is_color=False):
    h, w, c = img.shape
    result_dict = {}

    x1 = int(xyxy[0])
    y1 = int(xyxy[1])
    x2 = int(xyxy[2])
    y2 = int(xyxy[3])
    landmarks_np = np.zeros((4, 2))
    rect = [x1, y1, x2, y2]
    for i in range(4):
        point_x = int(landmarks[2 * i])
        point_y = int(landmarks[2 * i + 1])
        landmarks_np[i] = np.array([point_x, point_y])

    class_label = int(class_num)
    roi_img = four_point_transform(img, landmarks_np)
    if class_label:
        roi_img = get_split_merge(roi_img)

    if not is_color:
        plate_number, rec_prob = get_plate_result(roi_img, device, plate_rec_model, is_color=is_color)
    else:
        plate_number, rec_prob, plate_color, color_conf = get_plate_result(
            roi_img, device, plate_rec_model, is_color=is_color
        )

    result_dict['rect'] = rect
    result_dict['detect_conf'] = conf
    result_dict['landmarks'] = landmarks_np.tolist()
    result_dict['plate_no'] = plate_number
    result_dict['rec_conf'] = rec_prob
    result_dict['roi_height'] = roi_img.shape[0]
    result_dict['plate_color'] = ""
    if is_color:
        result_dict['plate_color'] = plate_color
        result_dict['color_conf'] = color_conf
    result_dict['plate_type'] = class_label
    return result_dict


def detect_Recognition_plate(model, orgimg, device, plate_rec_model, img_size, is_color=False):
    conf_thres = CONF_THRES
    iou_thres = IOU_THRES
    dict_list = []
    img0 = copy.deepcopy(orgimg)
    if orgimg is None:
        return dict_list
    h0, w0 = orgimg.shape[:2]
    r = img_size / max(h0, w0)
    if r != 1:
        interp = cv2.INTER_AREA if r < 1 else cv2.INTER_LINEAR
        img0 = cv2.resize(img0, (int(w0 * r), int(h0 * r)), interpolation=interp)

    imgsz = check_img_size(img_size, s=model.stride.max())
    img = letterbox(img0, new_shape=imgsz)[0]
    img = img[:, :, ::-1].transpose(2, 0, 1).copy()

    img = torch.from_numpy(img).to(device)
    img = img.float()
    img /= 255.0
    if img.ndimension() == 3:
        img = img.unsqueeze(0)

    with torch.no_grad():
        pred = model(img)[0]

    pred = non_max_suppression_face(pred, conf_thres, iou_thres)

    for i, det in enumerate(pred):
        if len(det):
            det[:, :4] = scale_coords(img.shape[2:], det[:, :4], orgimg.shape).round()
            det[:, 5:13] = scale_coords_landmarks(img.shape[2:], det[:, 5:13], orgimg.shape).round()

            for j in range(det.size()[0]):
                xyxy = det[j, :4].view(-1).tolist()
                conf = det[j, 4].cpu().numpy()
                landmarks = det[j, 5:13].view(-1).tolist()
                class_num = det[j, 13].cpu().numpy()
                result_dict = get_plate_rec_landmark(
                    orgimg, xyxy, conf, landmarks, class_num, device, plate_rec_model, is_color=is_color
                )
                dict_list.append(result_dict)
    return dict_list


def _get_padding_bbox(rect_area):
    """计算带 padding 的 bbox"""
    x, y = rect_area[0], rect_area[1]
    w, h = rect_area[2] - rect_area[0], rect_area[3] - rect_area[1]
    padding_w = 0.05 * w
    padding_h = 0.11 * h
    x1 = max(0, int(x - padding_w))
    y1 = max(0, int(y - padding_h))
    x2 = min(1920, int(rect_area[2] + padding_w))   # 1920 为安全上限
    y2 = min(1080, int(rect_area[3] + padding_h))
    return x1, y1, x2, y2


def _draw_single_plate(orgimg, result, color=(0, 0, 255), track_id=None):
    """绘制单个车牌结果"""
    rect_area = result['rect']
    landmarks = result.get('landmarks')

    x1, y1, x2, y2 = _get_padding_bbox(rect_area)

    result_p = result['plate_no']
    if result.get('plate_type', 0) == 0:
        result_p += " " + result.get('plate_color', '')
    else:
        result_p += " " + result.get('plate_color', '') + "双层"

    if track_id is not None:
        result_p = f"[{track_id}] {result_p}"

    # 绘制关键点
    if landmarks:
        for i in range(4):
            cv2.circle(orgimg, (int(landmarks[i][0]), int(landmarks[i][1])), 5, clors[i], -1)

    # 绘制检测框
    cv2.rectangle(orgimg, (x1, y1), (x2, y2), color, 2)

    # 绘制文字背景
    labelSize = cv2.getTextSize(result_p, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    text_x = x1
    if text_x + labelSize[0][0] > orgimg.shape[1]:
        text_x = int(orgimg.shape[1] - labelSize[0][0])
    orgimg = cv2.rectangle(
        orgimg,
        (text_x, int(y1 - round(1.6 * labelSize[0][1]))),
        (int(text_x + round(1.2 * labelSize[0][0])), y1 + labelSize[1]),
        (255, 255, 255), cv2.FILLED
    )
    orgimg = cv2ImgAddText(orgimg, result_p, text_x, int(y1 - round(1.6 * labelSize[0][1])), (0, 0, 0), 21)

    return result_p


def draw_result(mode, orgimg, dict_list, is_color=False):
    """原始无跟踪绘制（兼容图片模式）"""
    result_str = ""
    for result in dict_list:
        result_p = _draw_single_plate(orgimg, result)
        result_str += result_p.split('] ')[-1] if '] ' in result_p else result_p
        result_str += " "

    if result_str.strip():
        logger.info("识别结果: %s", result_str.strip())
        _db_manager.submit_plate(result_str.strip(), mode)

    return orgimg


def draw_tracked_result(mode, orgimg, tracker, is_color=False):
    """跟踪模式绘制：给每个跟踪目标分配稳定颜色，显示跟踪ID"""
    active_tracks = tracker.get_active_tracks()

    for trk in active_tracks:
        color = TRACK_COLORS[trk.track_id % len(TRACK_COLORS)]

        result_dict = {
            'rect': trk.bbox,
            'landmarks': trk.landmarks,
            'plate_no': trk.history[-1]['plate_no'] if trk.history else "",
            'plate_color': trk.history[-1]['plate_color'] if trk.history else "",
            'plate_type': trk.plate_type
        }
        _draw_single_plate(orgimg, result_dict, color=color, track_id=trk.track_id)

    # 处理已确认消失的目标
    confirmed = tracker.get_confirmed_plates()
    if confirmed:
        _db_manager.submit_tracked_plates(confirmed, mode)

    return orgimg


def update_image_label(img, label):
    fixed_width, fixed_height = VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT
    img = cv2.resize(img, (fixed_width, fixed_height))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img)
    img_tk = ImageTk.PhotoImage(image=img_pil)
    label.config(image=img_tk)
    label.image = img_tk


def open_video_source(source):
    """统一打开视频源：本地文件、摄像头索引、RTSP URL"""
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        capture = cv2.VideoCapture(int(source))
    elif isinstance(source, str) and (source.startswith('rtsp://') or source.startswith('http://')):
        capture = cv2.VideoCapture(source)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    else:
        capture = cv2.VideoCapture(source)
    return capture


def plate_detection(source, label, mode, stop_event=None, pause_event=None):
    """
    车牌检测主函数（带跟踪与多帧投票）
    :param source: 视频路径、摄像头索引(0,1...)或RTSP地址
    :param label: tkinter Label 控件
    :param mode: 'default' 入库 / 'exit' 出库
    :param stop_event: threading.Event 停止信号
    :param pause_event: threading.Event 暂停信号
    """
    if stop_event is None:
        import threading
        stop_event = threading.Event()
    if pause_event is None:
        import threading
        pause_event = threading.Event()

    device = ModelCache.get_device()
    detect_model = ModelCache.get_detect_model()
    plate_rec_model = ModelCache.get_rec_model(is_color=True)
    ModelCache.warmup()

    capture = open_video_source(source)
    if not capture.isOpened():
        logger.error("无法打开视频源: %s", source)
        return

    tracker = PlateTracker()
    frame_count = 0
    fps_all = 0

    try:
        while not stop_event.is_set():
            if pause_event.is_set():
                time.sleep(0.05)
                continue

            ret, img = capture.read()
            if not ret:
                logger.info("视频读取结束")
                break

            frame_count += 1

            # 跳帧：非检测帧只绘制跟踪结果，不做推理
            if frame_count % SKIP_FRAMES != 0:
                # tracker 状态不变，只绘制当前活跃的跟踪目标
                ori_img = draw_tracked_result(mode, img, tracker, is_color=True)
            else:
                t1 = cv2.getTickCount()
                dict_list = detect_Recognition_plate(
                    detect_model, img, device, plate_rec_model, IMG_SIZE, is_color=True
                )
                # 将检测结果传入跟踪器
                tracker.update(dict_list)
                # 绘制跟踪结果（同时处理已确认消失的 track）
                ori_img = draw_tracked_result(mode, img, tracker, is_color=True)
                t2 = cv2.getTickCount()
                infer_time = (t2 - t1) / cv2.getTickFrequency()
                fps = 1.0 / infer_time if infer_time > 0 else 0
                fps_all += fps
                str_fps = f'fps:{fps:.2f}'
                cv2.putText(ori_img, str_fps, (20, 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            update_image_label(ori_img, label)
            cv2.waitKey(1)

    finally:
        # 视频结束时，处理所有尚未消失的 track
        remaining_confirmed = []
        for trk in tracker.get_active_tracks():
            if not trk.confirmed and trk.is_ready_for_vote():
                voted_plate, voted_color, conf = trk.vote_plate()
                if voted_plate and not tracker._is_in_cooldown(voted_plate):
                    remaining_confirmed.append({
                        'plate_no': voted_plate,
                        'plate_color': voted_color,
                        'confidence': conf,
                        'track_id': trk.track_id,
                        'plate_type': trk.plate_type
                    })
                    tracker._add_to_cooldown(voted_plate)
        if remaining_confirmed:
            _db_manager.submit_tracked_plates(remaining_confirmed, mode)

        capture.release()
        cv2.destroyAllWindows()
        avg_fps = fps_all / frame_count if frame_count > 0 else 0
        logger.info("处理结束: 共 %d 帧, 平均 fps: %.2f, 活跃跟踪目标: %d",
                   frame_count, avg_fps, len(tracker.get_active_tracks()))


# 保持向后兼容
detect_plate = plate_detection
