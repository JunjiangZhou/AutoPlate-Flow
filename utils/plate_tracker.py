# -*- coding: UTF-8 -*-
"""
车牌跟踪与多帧投票模块
解决同一辆车在视频中连续多帧被重复识别、OCR结果不稳定的问题
"""
import time
from collections import Counter
from utils.logger import get_logger
from config import (
    TRACK_IOU_THRESHOLD, TRACK_MAX_LOST,
    TRACK_CONFIRM_MIN_FRAMES, TRACK_COOLDOWN_SECONDS
)

logger = get_logger(__name__)


def compute_iou(box_a, box_b):
    """
    计算两个矩形框的 IoU
    box: [x1, y1, x2, y2]
    """
    x_a = max(box_a[0], box_b[0])
    y_a = max(box_a[1], box_b[1])
    x_b = min(box_a[2], box_b[2])
    y_b = min(box_a[3], box_b[3])

    inter_area = max(0, x_b - x_a) * max(0, y_b - y_a)
    box_a_area = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    box_b_area = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union_area = box_a_area + box_b_area - inter_area

    if union_area == 0:
        return 0.0
    return inter_area / union_area


class Track:
    """单个车牌跟踪目标"""

    _id_counter = 0

    def __init__(self, bbox, plate_no, plate_color="", plate_type=0):
        Track._id_counter += 1
        self.track_id = Track._id_counter
        self.bbox = bbox                      # [x1, y1, x2, y2]
        self.landmarks = None                 # 角点坐标
        self.history = []                     # 历史识别结果 [(plate_no, plate_color, conf), ...]
        self.lost_count = 0                   # 连续丢失帧数
        self.confirmed = False                # 是否已确认（投票后入库）
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.plate_type = plate_type          # 0单层 1双层
        self.detect_conf = 0.0                # 检测置信度

        # 初始化第一条记录
        self._add_record(plate_no, plate_color)

    def _add_record(self, plate_no, plate_color=""):
        """添加一条识别记录"""
        self.history.append({
            'plate_no': plate_no,
            'plate_color': plate_color,
            'timestamp': time.time()
        })
        self.last_seen = time.time()

    def update(self, bbox, plate_no, plate_color="", landmarks=None, detect_conf=0.0):
        """更新跟踪目标状态"""
        self.bbox = bbox
        self.landmarks = landmarks
        self.detect_conf = detect_conf
        self.lost_count = 0
        self._add_record(plate_no, plate_color)

    def mark_lost(self):
        """标记为丢失一帧"""
        self.lost_count += 1

    def is_dead(self):
        """判断跟踪目标是否已消失"""
        return self.lost_count >= TRACK_MAX_LOST

    def is_ready_for_vote(self):
        """判断是否有足够的历史记录进行投票"""
        return len(self.history) >= TRACK_CONFIRM_MIN_FRAMES

    def vote_plate(self):
        """
        对历史识别结果进行多帧投票
        返回: (plate_no, plate_color, confidence_score)
        """
        if not self.history:
            return "", "", 0.0

        plate_nos = [h['plate_no'] for h in self.history]
        plate_colors = [h['plate_color'] for h in self.history if h['plate_color']]

        # 整体频率投票：哪个完整车牌出现次数最多
        if len(plate_nos) >= 3:
            # 字符级投票（更精细）
            voted_plate = self._char_level_vote(plate_nos)
        else:
            # 记录少时直接用频率最高
            counter = Counter(plate_nos)
            voted_plate = counter.most_common(1)[0][0]

        # 颜色投票
        voted_color = ""
        if plate_colors:
            voted_color = Counter(plate_colors).most_common(1)[0][0]

        # 置信度 = 该结果在历史中的出现频率
        freq = plate_nos.count(voted_plate) / len(plate_nos)

        return voted_plate, voted_color, round(freq, 2)

    def _char_level_vote(self, plate_nos):
        """
        字符级投票：对每个位置的字符分别投票
        适用于 "京A12345" 和 "京A1234S" 这种情况
        """
        # 筛选长度一致的车牌（过滤掉明显错误的）
        length_counts = Counter(len(p) for p in plate_nos)
        most_common_len = length_counts.most_common(1)[0][0]
        filtered = [p for p in plate_nos if len(p) == most_common_len]

        if not filtered:
            return plate_nos[0]

        result_chars = []
        for i in range(most_common_len):
            chars_at_pos = [p[i] for p in filtered if i < len(p)]
            result_chars.append(Counter(chars_at_pos).most_common(1)[0][0])

        return "".join(result_chars)

    def __repr__(self):
        return f"Track(id={self.track_id}, lost={self.lost_count}, history={len(self.history)})"


class PlateTracker:
    """车牌跟踪管理器"""

    def __init__(self):
        self.tracks = []          # 当前活跃的跟踪目标
        self.confirmed_plates = []  # 本轮已确认的车牌（待入库）
        self._cooldown_map = {}   # 冷却记录: {plate_no: timestamp}

    def _is_in_cooldown(self, plate_no):
        """检查车牌是否处于冷却期"""
        if plate_no not in self._cooldown_map:
            return False
        elapsed = time.time() - self._cooldown_map[plate_no]
        return elapsed < TRACK_COOLDOWN_SECONDS

    def _add_to_cooldown(self, plate_no):
        """将车牌加入冷却"""
        self._cooldown_map[plate_no] = time.time()

    def _cleanup_cooldown(self):
        """清理已过期的冷却记录"""
        now = time.time()
        expired = [p for p, t in self._cooldown_map.items() if now - t > TRACK_COOLDOWN_SECONDS * 2]
        for p in expired:
            del self._cooldown_map[p]

    def update(self, detections):
        """
        更新跟踪器
        :param detections: list[dict] 每帧检测结果，每个元素包含 'rect', 'plate_no', 'plate_color', 'landmarks', 'detect_conf', 'plate_type'
        :return: list[Track] 当前活跃跟踪目标
        """
        self.confirmed_plates = []
        self._cleanup_cooldown()

        # 标记所有 track 为待匹配
        matched_track_indices = set()
        matched_det_indices = set()

        # 1. 计算所有 detection 与所有 track 的 IoU
        iou_matrix = []
        for det_idx, det in enumerate(detections):
            row = []
            for trk_idx, trk in enumerate(self.tracks):
                iou = compute_iou(det['rect'], trk.bbox)
                row.append((iou, det_idx, trk_idx))
            iou_matrix.extend(row)

        # 2. 按 IoU 降序贪心匹配
        iou_matrix.sort(reverse=True, key=lambda x: x[0])

        for iou, det_idx, trk_idx in iou_matrix:
            if iou < TRACK_IOU_THRESHOLD:
                break
            if det_idx in matched_det_indices or trk_idx in matched_track_indices:
                continue

            det = detections[det_idx]
            trk = self.tracks[trk_idx]
            trk.update(
                bbox=det['rect'],
                plate_no=det['plate_no'],
                plate_color=det.get('plate_color', ''),
                landmarks=det.get('landmarks'),
                detect_conf=det.get('detect_conf', 0.0)
            )
            matched_det_indices.add(det_idx)
            matched_track_indices.add(trk_idx)

        # 3. 未匹配的 track 标记为丢失
        for trk_idx, trk in enumerate(self.tracks):
            if trk_idx not in matched_track_indices:
                trk.mark_lost()

        # 4. 处理消失的 track（丢失过多帧）
        dead_tracks = [t for t in self.tracks if t.is_dead()]
        for trk in dead_tracks:
            if not trk.confirmed and trk.is_ready_for_vote():
                voted_plate, voted_color, conf = trk.vote_plate()
                if voted_plate and not self._is_in_cooldown(voted_plate):
                    self.confirmed_plates.append({
                        'plate_no': voted_plate,
                        'plate_color': voted_color,
                        'confidence': conf,
                        'track_id': trk.track_id,
                        'plate_type': trk.plate_type
                    })
                    self._add_to_cooldown(voted_plate)
                    logger.info("[Track #%d] 投票确认车牌: %s (置信度: %.0f%%), 历史记录数: %d",
                               trk.track_id, voted_plate, conf * 100, len(trk.history))
            elif not trk.confirmed:
                logger.debug("[Track #%d] 历史记录不足(%d条)，丢弃", trk.track_id, len(trk.history))

        # 移除死亡的 track
        self.tracks = [t for t in self.tracks if not t.is_dead()]

        # 5. 未匹配的 detection 创建新 track
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_det_indices:
                new_track = Track(
                    bbox=det['rect'],
                    plate_no=det['plate_no'],
                    plate_color=det.get('plate_color', ''),
                    plate_type=det.get('plate_type', 0)
                )
                new_track.landmarks = det.get('landmarks')
                new_track.detect_conf = det.get('detect_conf', 0.0)
                self.tracks.append(new_track)
                logger.debug("[Track #%d] 新目标创建: %s", new_track.track_id, det['plate_no'])

        return self.tracks

    def get_confirmed_plates(self):
        """获取本轮已确认的车牌（应被写入数据库）"""
        return self.confirmed_plates

    def get_active_tracks(self):
        """获取当前活跃的跟踪目标"""
        return self.tracks

    def reset(self):
        """重置跟踪器（如视频切换时）"""
        self.tracks = []
        self.confirmed_plates = []
        self._cooldown_map = {}
        Track._id_counter = 0
        logger.info("跟踪器已重置")
