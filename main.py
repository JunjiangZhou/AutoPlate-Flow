# -*- coding: UTF-8 -*-
"""程序入口"""
from login_window import login_window
from utils.database import Database, UserDatabase
from utils.logger import get_logger

logger = get_logger(__name__)

if __name__ == "__main__":
    logger.info("系统启动中...")
    # 初始化数据库表
    db = Database()
    db.init_tables()
    db.init_settings_table()
    UserDatabase().init_tables()
    logger.info("数据库初始化完成")
    login_window()
