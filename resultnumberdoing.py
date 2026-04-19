# -*- coding: UTF-8 -*-
"""
车牌数据库业务逻辑模块（重构版）
特性：线程池管理、统一数据库操作
"""
import re
from concurrent.futures import ThreadPoolExecutor
from utils.database import Database
from utils.logger import get_logger

logger = get_logger(__name__)

# 车牌号正则表达式（支持普通民用、新能源、港澳等）
PLATE_PATTERN = re.compile(
    r'[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{4,5}[A-Z0-9挂学警港澳]?'
)


class PlateDatabaseManager:
    """车牌数据库操作管理器（线程安全）
    支持两种提交模式：
    1. 原始字符串模式（兼容旧代码）：submit_plate(result_str, mode)
    2. 结构化模式（推荐）：submit_tracked_plates(plate_list, mode)
    """

    def __init__(self, max_workers=4):
        self.db = Database()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="plate_db")
        logger.info("车牌数据库管理器初始化完成，线程池大小: %d", max_workers)

    def submit_plate(self, result_number, mode):
        """提交识别结果到线程池处理（兼容旧接口）"""
        plate_numbers = PLATE_PATTERN.findall(result_number)
        if not plate_numbers:
            logger.debug("未识别到有效车牌: %s", result_number)
            return

        for plate_number in plate_numbers:
            if mode == "default":
                self.executor.submit(self._do_entry, plate_number)
            elif mode == "exit":
                self.executor.submit(self._do_exit, plate_number)

    def submit_tracked_plates(self, plate_list, mode):
        """
        提交跟踪确认后的车牌列表（新接口，支持颜色信息）
        :param plate_list: list[dict] 每个元素含 'plate_no', 'plate_color', 'confidence'
        :param mode: 'default' 入库 / 'exit' 出库
        """
        if not plate_list:
            return

        for item in plate_list:
            plate_no = item.get('plate_no', '')
            plate_color = item.get('plate_color', '')
            confidence = item.get('confidence', 0.0)

            if not plate_no:
                continue

            # 置信度太低的不入库（阈值可调）
            if confidence < 0.5:
                logger.warning("车牌 %s 投票置信度 %.0f%% 过低，跳过入库", plate_no, confidence * 100)
                continue

            logger.info("提交跟踪结果: %s [%s] 置信度: %.0f%%", plate_no, plate_color, confidence * 100)

            if mode == "default":
                self.executor.submit(self._do_entry, plate_no)
            elif mode == "exit":
                self.executor.submit(self._do_exit, plate_no)

    def _do_entry(self, plate_number):
        try:
            self.db.insert_entry(plate_number)
        except Exception as e:
            logger.error("入库失败 [%s]: %s", plate_number, e)

    def _do_exit(self, plate_number):
        try:
            result = self.db.insert_exit(plate_number)
            if result:
                logger.info("计费完成: %s, 费用 %.2f 元", plate_number, result['toll_amount'])
        except Exception as e:
            logger.error("出库失败 [%s]: %s", plate_number, e)

    def shutdown(self):
        self.executor.shutdown(wait=True)
        logger.info("车牌数据库管理器已关闭")


# 保持向后兼容的顶层函数
_db_manager = PlateDatabaseManager()


def numberfilter(result_number, mode, hourly_rate=10):
    """向后兼容的入口函数"""
    _db_manager.submit_plate(result_number, mode)
