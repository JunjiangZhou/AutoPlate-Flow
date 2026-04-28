# -*- coding: UTF-8 -*-
"""程序入口"""
from login_window import login_window
from utils.database import Database
from utils.logger import get_logger

logger = get_logger(__name__)

if __name__ == "__main__":
    logger.info("系统启动中...")
    # 初始化统一数据库（所有表在一个数据库中）
    Database().init_all_tables()
    logger.info("数据库初始化完成")
    login_window()
