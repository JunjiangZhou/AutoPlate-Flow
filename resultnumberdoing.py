import re
import sqlite3
import threading
from datetime import datetime

# 创建一个全局线程锁
db_lock = threading.Lock()


def insert_plate_if_not_exists(plate_number):
    with db_lock:
        conn = sqlite3.connect('parking_system.db')
        c = conn.cursor()

        try:
            # 查询最近一次的 hourly_rate
            c.execute('''
                SELECT rate FROM hourly_rates
                ORDER BY timestamp DESC LIMIT 1
            ''')
            latest_hourly_rate = c.fetchone()

            if latest_hourly_rate:
                hourly_rate = latest_hourly_rate[0]
            else:
                hourly_rate = 10.0  # 如果没有记录，使用默认的 hourly_rate

            # 查询车牌号最新一条记录
            c.execute('''
                SELECT exit_time FROM toll_records
                WHERE plate_number = ?
                ORDER BY entry_time DESC LIMIT 1
            ''', (plate_number,))

            record = c.fetchone()
            entry_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 如果没有找到记录，或有记录但已出库（exit_time 不为空），则插入新的车牌号信息
            if record is None or record[0] is not None:
                c.execute('''
                    INSERT INTO toll_records (plate_number, entry_time, toll_amount, hourly_rate)
                    VALUES (?, ?, ?, ?)
                ''', (plate_number, entry_time, 0.0, hourly_rate))
                print(f"Inserted: {plate_number} with hourly_rate: {hourly_rate}")
            else:
                print(f"Plate number {plate_number} is already in the parking lot, ignoring insertion.")

            # 提交事务
            conn.commit()
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            # 关闭连接
            conn.close()


def insert_exit_plate(plate_number):
    with db_lock:  # 使用线程锁，确保同一时间只有一个线程访问数据库
        conn = sqlite3.connect('parking_system.db')
        c = conn.cursor()

        try:
            # 查询该车牌号的最新一条入库记录的 ID（exit_time 为 NULL）
            c.execute('''
                SELECT id, entry_time, hourly_rate FROM toll_records
                WHERE plate_number = ? AND exit_time IS NULL
                ORDER BY entry_time DESC LIMIT 1
            ''', (plate_number,))

            record = c.fetchone()

            # 如果没有找到记录，提示没有入库记录
            if record is None:
                print(f"没有找到车牌号 {plate_number} 的入库记录")
            else:
                # 获取入库记录的 id、入库时间和 hourly_rate
                record_id = record[0]
                entry_time = datetime.strptime(record[1], '%Y-%m-%d %H:%M:%S')
                hourly_rate = record[2]

                # 获取当前时间作为离开时间
                exit_time = datetime.now()
                exit_time_str = exit_time.strftime('%Y-%m-%d %H:%M:%S')

                # 计算停车时长（以小时为单位，四舍五入）
                parking_duration = (exit_time - entry_time).total_seconds() / 3600
                parking_duration = round(parking_duration, 2)

                # 计算收费金额（时长 * 每小时的收费标准）
                toll_amount = parking_duration * hourly_rate

                # 使用 ID 更新车辆的离开时间和收费金额
                c.execute('''
                    UPDATE toll_records
                    SET exit_time = ?, toll_amount = ?
                    WHERE id = ?
                ''', (exit_time_str, toll_amount, record_id))

                print(f"车牌号 {plate_number} 的离开时间已记录为 {exit_time_str}")
                print(f"停车时长为 {parking_duration} 小时，收费金额为 {toll_amount} 元")

            # 提交事务并关闭数据库连接
            conn.commit()
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            conn.close()



def numberfilter(result_number, mode, hourly_rate=10):
    data = result_number

    # 正则表达式匹配民用普通车牌号
    pattern = r'[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{4,5}'

    # 使用findall来提取所有匹配的车牌号
    plate_numbers = re.findall(pattern, data)

    for plate_number in plate_numbers:
        if mode == "default":
            # 为每个车牌号创建一个线程，插入入库记录
            db_thread = threading.Thread(target=insert_plate_if_not_exists, args=(plate_number,))
            db_thread.start()
        elif mode == "exit":
            # 为每个车牌号创建一个线程，更新出库记录
            db_thread = threading.Thread(target=insert_exit_plate, args=(plate_number,))
            db_thread.start()

