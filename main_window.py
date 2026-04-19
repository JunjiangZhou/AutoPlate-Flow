import tkinter as tk
import sqlite3
import threading
import stream
from tkinter import filedialog
from detect_plate import plate_detection
from tkinter import ttk

def open_main_window():
    main_window = tk.Tk()
    main_window.title("智能停车场管理系统")
    main_window.geometry("1280x720")

    # 创建左侧的Frame，用于放置标题和按钮
    left_frame = tk.Frame(main_window, width=250, bg="lightgray")
    left_frame.pack(side="left", fill="y")

    # 创建主内容区Frame，用于放置显示内容
    content_frame = tk.Frame(main_window, bg="white")
    content_frame.pack(side="top", expand=True, fill="both")

    # 创建底部的Frame，用于显示数据库内容
    bottom_frame = tk.Frame(main_window, bg="lightgray", height=150)
    bottom_frame.pack(side="bottom", fill="x")

    # 添加功能按钮到菜单Frame中
    def toll():
        for widget in content_frame.winfo_children():
            widget.destroy()  # 清空右侧内容区域


        def detection(mode):
            # 打开文件选择对话框
            if mode == "default":
                file_path= filedialog.askopenfilename(title="汽车进入",
                                                   filetypes=(("MP4视频文件", "*.mp4"),
                                                              ("All files", "*.*")))
                label_text = "车牌识别系统（入库）"
            if mode == "exit":
                file_path = filedialog.askopenfilename(title="汽车出库",
                                                       filetypes=(("MP4视频文件", "*.mp4"),
                                                                  ("All files", "*.*")))
                label_text = "车牌识别系统（出库）"
            if not file_path:
                return  # 如果文件路径为空，则退出函数
            video_container = tk.Frame(content_frame)
            video_container.pack(side="left", padx=10, pady=5)
            tk.Label(video_container, text=label_text, font=("Arial", 16)).pack(side="top", anchor="nw", pady=5)
            video_label = tk.Label(video_container)
            video_label.pack(side="top", anchor="nw")

            # 在单独的线程中运行视频检测，避免阻塞主线程
            def run_detection():
                plate_detection(file_path, video_label,mode)
                
            # 启动run_detection线程
            detection_thread = threading.Thread(target=run_detection)
            detection_thread.start()

        # 刷新显示数据库内容
        def refresh_records():
            # 清除旧的记录
            for widget in bottom_frame.winfo_children():
                if isinstance(widget, ttk.Treeview):
                    widget.destroy()

            # 连接到SQLite数据库并查询记录
            conn = sqlite3.connect('parking_system.db')
            c = conn.cursor()
            c.execute('SELECT * FROM toll_records')
            records = c.fetchall()
            conn.close()

            # 定义表头
            columns = ('ID', 'Plate Number', 'Toll Amount', 'Entry Time', 'Exit Time')
            tree = ttk.Treeview(bottom_frame, columns=columns, show='headings')

            # 设置表头
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=150)

            # 插入数据
            for record in records:
                tree.insert('', tk.END, values=record)

            # 将 Treeview 放置在 bottom_frame 中
            tree.pack(expand=True, fill='both')

            # 每5秒刷新一次
            bottom_frame.after(5000, refresh_records)

        # 开始刷新数据库记录
        refresh_records()

        def parking_monitor():
            # 为容量检测功能创建一个新的视频容器
            video_container = tk.Frame(content_frame)
            video_container.pack(side="left", padx=10, pady=5)

            # 添加标题和视频显示的label
            tk.Label(video_container, text="容量检测系统", font=("Arial", 16)).pack(side="top", anchor="nw", pady=5)
            video_label = tk.Label(video_container)
            video_label.pack(side="top", anchor="nw")

            # 调用 parking_detection 并将 video_label 传递给它
            stream.parking_detection(video_label)

            # 在左侧Frame中添加按钮和标题

        title_label = tk.Label(left_frame, text="车牌识别与智能计费系统", font=("Arial", 16), bg="lightgray")
        title_label.pack(pady=20)

        file_button_enter = tk.Button(left_frame, text="汽车进入", command=lambda: detection(mode="default"), width=20)
        file_button_enter.pack(pady=10)

        file_button_exit = tk.Button(left_frame, text="汽车出库", command=lambda: detection(mode="exit"), width=20)
        file_button_exit.pack(pady=10)

        monitor_button = tk.Button(left_frame, text="容量检测", command=parking_monitor, width=20)
        monitor_button.pack(pady=10)

        exit_button = tk.Button(left_frame, text="退出", command=main_window.destroy, width=20)
        exit_button.pack(pady=10)




    # 直接进入收费管理功能
    toll()

    main_window.mainloop()

# 运行主窗口
if __name__ == "__main__":
    open_main_window()
