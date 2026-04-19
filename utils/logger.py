# -*- coding: UTF-8 -*-
"""统一日志管理"""
import logging
import sys
from config import LOG_LEVEL, LOG_FORMAT


def get_logger(name):
    """获取配置好的 logger 实例"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    return logger
