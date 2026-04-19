import sqlite3


def initialize_db():
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()

    # 创建用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    # 插入一个示例用户
    c.execute('''
        INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)
    ''', ("admin", "password"))

    conn.commit()
    conn.close()
