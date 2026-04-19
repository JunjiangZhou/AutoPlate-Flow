import sqlite3


def initialize_db():
    conn = sqlite3.connect('parking_system.db')
    c = conn.cursor()

    # 创建车牌记录表，并添加 exit_time 字段
    c.execute('''
        CREATE TABLE IF NOT EXISTS toll_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL,
            toll_amount REAL DEFAULT NULL,
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exit_time TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
