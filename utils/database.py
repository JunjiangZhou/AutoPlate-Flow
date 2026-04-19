# -*- coding: UTF-8 -*-
"""统一数据库管理模块"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from config import DB_PATH, USER_DB_PATH
from utils.logger import get_logger

logger = get_logger(__name__)


class Database:
    """停车场数据库管理类（线程安全）"""

    _local = threading.local()

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    @contextmanager
    def _connect(self):
        """上下文管理器确保连接自动关闭"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("数据库操作失败: %s", e)
            raise
        finally:
            conn.close()

    # ========== 初始化 ==========
    def init_tables(self):
        with self._connect() as conn:
            c = conn.cursor()
            # 停车记录表
            c.execute('''
                CREATE TABLE IF NOT EXISTS toll_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT NOT NULL,
                    toll_amount REAL DEFAULT NULL,
                    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exit_time TIMESTAMP,
                    hourly_rate REAL DEFAULT 10.0,
                    status TEXT DEFAULT 'in'  -- 'in' 在库, 'out' 已出库
                )
            ''')
            # 动态费率记录表
            c.execute('''
                CREATE TABLE IF NOT EXISTS hourly_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rate REAL NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("停车场数据库表初始化完成")

    # ========== 入库操作 ==========
    def insert_entry(self, plate_number, hourly_rate=10.0):
        with self._connect() as conn:
            c = conn.cursor()
            # 检查是否已在库且未出库
            c.execute('''
                SELECT id FROM toll_records
                WHERE plate_number = ? AND status = 'in'
                ORDER BY entry_time DESC LIMIT 1
            ''', (plate_number,))
            if c.fetchone():
                logger.info("车牌 %s 已在停车场内，忽略重复入库", plate_number)
                return False

            entry_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''
                INSERT INTO toll_records (plate_number, entry_time, toll_amount, hourly_rate, status)
                VALUES (?, ?, ?, ?, 'in')
            ''', (plate_number, entry_time, 0.0, hourly_rate))
            logger.info("入库成功: %s, 费率: %.2f", plate_number, hourly_rate)
            return True

    # ========== 出库操作 ==========
    def insert_exit(self, plate_number):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, entry_time, hourly_rate FROM toll_records
                WHERE plate_number = ? AND status = 'in'
                ORDER BY entry_time DESC LIMIT 1
            ''', (plate_number,))
            record = c.fetchone()

            if not record:
                logger.warning("车牌 %s 无入库记录", plate_number)
                return None

            record_id, entry_time_str, hourly_rate = record
            entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
            exit_time = datetime.now()
            parking_duration = round((exit_time - entry_time).total_seconds() / 3600, 2)
            toll_amount = round(parking_duration * hourly_rate, 2)
            exit_time_str = exit_time.strftime('%Y-%m-%d %H:%M:%S')

            c.execute('''
                UPDATE toll_records
                SET exit_time = ?, toll_amount = ?, status = 'out'
                WHERE id = ?
            ''', (exit_time_str, toll_amount, record_id))

            logger.info("出库成功: %s, 时长: %.2f小时, 费用: %.2f元", plate_number, parking_duration, toll_amount)
            return {
                'plate_number': plate_number,
                'entry_time': entry_time_str,
                'exit_time': exit_time_str,
                'duration': parking_duration,
                'toll_amount': toll_amount
            }

    # ========== 查询操作 ==========
    def get_all_records(self, limit=100):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, plate_number, toll_amount, entry_time, exit_time, status, hourly_rate
                FROM toll_records
                ORDER BY entry_time DESC
                LIMIT ?
            ''', (limit,))
            return c.fetchall()

    def get_records_by_plate(self, plate_number, limit=50):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, plate_number, toll_amount, entry_time, exit_time, status, hourly_rate
                FROM toll_records
                WHERE plate_number = ?
                ORDER BY entry_time DESC
                LIMIT ?
            ''', (plate_number, limit))
            return c.fetchall()

    def get_current_parked(self):
        """获取当前在库车辆"""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, plate_number, entry_time, hourly_rate
                FROM toll_records
                WHERE status = 'in'
                ORDER BY entry_time DESC
            ''')
            return c.fetchall()

    def get_revenue_stats(self, days=7):
        """获取近 N 天的收入统计"""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT DATE(entry_time) as date,
                       COUNT(*) as total_count,
                       SUM(CASE WHEN toll_amount > 0 THEN toll_amount ELSE 0 END) as revenue,
                       COUNT(CASE WHEN status = 'in' THEN 1 END) as current_in
                FROM toll_records
                WHERE entry_time >= date('now', '-{} days')
                GROUP BY DATE(entry_time)
                ORDER BY date DESC
            '''.format(days))
            return c.fetchall()

    def delete_record(self, record_id):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM toll_records WHERE id = ?', (record_id,))
            logger.info("删除记录 ID=%s", record_id)
            return True

    # ========== 动态费率 ==========
    def insert_hourly_rate(self, rate):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO hourly_rates (rate) VALUES (?)', (rate,))
            logger.info("动态费率写入: %.2f", rate)

    def get_latest_hourly_rate(self, default=10.0):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT rate FROM hourly_rates
                ORDER BY timestamp DESC LIMIT 1
            ''')
            row = c.fetchone()
            return row[0] if row else default


class UserDatabase:
    """用户认证数据库管理类"""

    def __init__(self, db_path=USER_DB_PATH):
        self.db_path = db_path

    def init_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logger.info("用户数据库表初始化完成")

    def validate_login(self, username, password_hash):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT password_hash, salt FROM users WHERE username = ?
            ''', (username,))
            row = c.fetchone()
            if not row:
                return False
            stored_hash, salt = row
            import hashlib
            check_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
            return check_hash == stored_hash

    def add_user(self, username, password_hash, salt):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            try:
                c.execute('''
                    INSERT INTO users (username, password_hash, salt)
                    VALUES (?, ?, ?)
                ''', (username, password_hash, salt))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                logger.warning("用户名 %s 已存在", username)
                return False
