# -*- coding: UTF-8 -*-
"""
智能停车场管理系统主界面（重构版）
特性：完善的数据库管理、视频暂停/停止控制、摄像头支持
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time

from utils.logger import get_logger
from utils.database import Database
from config import REFRESH_INTERVAL, VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT

logger = get_logger(__name__)
_db = Database()

# 控制信号存储（按视频标签管理）
_video_controls = {}


def open_main_window():
    main_window = tk.Tk()
    main_window.title("智能停车场管理系统")
    main_window.geometry("1280x720")

    # ========== 左侧菜单栏 ==========
    left_frame = tk.Frame(main_window, width=250, bg="#2c3e50")
    left_frame.pack(side="left", fill="y")
    left_frame.pack_propagate(False)

    # ========== 主内容区 ==========
    content_frame = tk.Frame(main_window, bg="#ecf0f1")
    content_frame.pack(side="top", expand=True, fill="both")

    # ========== 底部数据库面板（Notebook 多标签页） ==========
    bottom_frame = tk.Frame(main_window, bg="#bdc3c7", height=220)
    bottom_frame.pack(side="bottom", fill="x")
    bottom_frame.pack_propagate(False)

    # 多标签页：停车记录 / 当前在库 / 收入统计
    notebook = ttk.Notebook(bottom_frame)
    notebook.pack(fill="both", expand=True)

    # --- 标签页1：停车记录 ---
    tab_records = tk.Frame(notebook)
    notebook.add(tab_records, text="停车记录")

    records_tree = ttk.Treeview(
        tab_records,
        columns=('ID', 'Plate', 'Amount', 'Entry', 'Exit', 'Status', 'Rate'),
        show='headings'
    )
    for col, text, width in [
        ('ID', 'ID', 50), ('Plate', '车牌号', 120), ('Amount', '费用(元)', 80),
        ('Entry', '入库时间', 150), ('Exit', '出库时间', 150),
        ('Status', '状态', 60), ('Rate', '费率', 60)
    ]:
        records_tree.heading(col, text=text)
        records_tree.column(col, width=width, anchor='center')
    records_tree.pack(side="left", fill="both", expand=True)

    scrollbar = ttk.Scrollbar(tab_records, orient="vertical", command=records_tree.yview)
    records_tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")

    # 搜索框
    search_frame = tk.Frame(tab_records)
    search_frame.pack(fill="x", padx=5, pady=2)
    tk.Label(search_frame, text="搜索车牌:").pack(side="left")
    search_entry = tk.Entry(search_frame, width=15)
    search_entry.pack(side="left", padx=5)

    def do_search():
        plate = search_entry.get().strip()
        if plate:
            records = _db.get_records_by_plate(plate)
        else:
            records = _db.get_all_records()
        refresh_tree(records_tree, records)

    tk.Button(search_frame, text="搜索", command=do_search).pack(side="left", padx=2)
    tk.Button(search_frame, text="重置", command=lambda: refresh_tree(records_tree, _db.get_all_records())).pack(side="left", padx=2)

    # --- 标签页2：当前在库车辆 ---
    tab_current = tk.Frame(notebook)
    notebook.add(tab_current, text="当前在库")

    current_tree = ttk.Treeview(tab_current, columns=('ID', 'Plate', 'Entry', 'Rate'), show='headings')
    for col, text, width in [('ID', 'ID', 50), ('Plate', '车牌号', 150), ('Entry', '入库时间', 200), ('Rate', '费率', 80)]:
        current_tree.heading(col, text=text)
        current_tree.column(col, width=width, anchor='center')
    current_tree.pack(side="left", fill="both", expand=True)
    scrollbar2 = ttk.Scrollbar(tab_current, orient="vertical", command=current_tree.yview)
    current_tree.configure(yscrollcommand=scrollbar2.set)
    scrollbar2.pack(side="right", fill="y")

    # --- 标签页3：收入统计 ---
    tab_stats = tk.Frame(notebook)
    notebook.add(tab_stats, text="收入统计")

    stats_tree = ttk.Treeview(tab_stats, columns=('Date', 'Count', 'Revenue', 'Current'), show='headings')
    for col, text, width in [('Date', '日期', 120), ('Count', '总车次', 80), ('Revenue', '收入(元)', 100), ('Current', '在库数', 80)]:
        stats_tree.heading(col, text=text)
        stats_tree.column(col, width=width, anchor='center')
    stats_tree.pack(side="left", fill="both", expand=True)
    scrollbar3 = ttk.Scrollbar(tab_stats, orient="vertical", command=stats_tree.yview)
    stats_tree.configure(yscrollcommand=scrollbar3.set)
    scrollbar3.pack(side="right", fill="y")

    # ========== 通用表格刷新函数 ==========
    def refresh_tree(tree, records):
        for item in tree.get_children():
            tree.delete(item)
        for record in records:
            tree.insert('', tk.END, values=record)

    def auto_refresh():
        # 刷新停车记录
        refresh_tree(records_tree, _db.get_all_records())
        # 刷新当前在库
        refresh_tree(current_tree, _db.get_current_parked())
        # 刷新统计
        refresh_tree(stats_tree, _db.get_revenue_stats(days=7))
        bottom_frame.after(REFRESH_INTERVAL, auto_refresh)

    auto_refresh()

    # ========== 主功能逻辑 ==========
    def toll():
        for widget in content_frame.winfo_children():
            widget.destroy()

        def detection(mode):
            if mode == "default":
                title = "车牌识别系统（入库）"
                file_title = "选择入库视频/摄像头"
            else:
                title = "车牌识别系统（出库）"
                file_title = "选择出库视频/摄像头"

            # 支持选择视频文件或直接输入摄像头索引
            dialog = tk.Toplevel(main_window)
            dialog.title(file_title)
            dialog.geometry("350x200")
            dialog.transient(main_window)
            dialog.grab_set()

            tk.Label(dialog, text="选择视频源:").pack(pady=5)
            source_var = tk.StringVar()
            source_entry = tk.Entry(dialog, textvariable=source_var, width=35)
            source_entry.pack(pady=5)

            def choose_file():
                path = filedialog.askopenfilename(
                    title=file_title,
                    filetypes=(("视频文件", "*.mp4 *.avi *.mkv"), ("所有文件", "*.*"))
                )
                if path:
                    source_var.set(path)

            def use_camera():
                source_var.set("0")

            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=5)
            tk.Button(btn_frame, text="选择文件", command=choose_file).pack(side="left", padx=5)
            tk.Button(btn_frame, text="使用摄像头", command=use_camera).pack(side="left", padx=5)

            def confirm():
                source = source_var.get().strip()
                if not source:
                    messagebox.showwarning("提示", "请选择视频源")
                    return
                dialog.destroy()
                start_detection(source, mode, title)

            tk.Button(dialog, text="开始识别", command=confirm, width=15).pack(pady=10)

        def start_detection(source, mode, title_text):
            video_container = tk.Frame(content_frame, bg="#ecf0f1")
            video_container.pack(side="left", padx=10, pady=5)

            tk.Label(video_container, text=title_text, font=("Microsoft YaHei", 14, "bold"), bg="#ecf0f1").pack(anchor="nw", pady=5)

            video_label = tk.Label(video_container, bg="black")
            video_label.pack(anchor="nw")

            # 控制按钮区
            ctrl_frame = tk.Frame(video_container, bg="#ecf0f1")
            ctrl_frame.pack(fill="x", pady=5)

            stop_event = threading.Event()
            pause_event = threading.Event()
            _video_controls[id(video_label)] = (stop_event, pause_event)

            def do_stop():
                stop_event.set()
                btn_stop.config(state="disabled")
                btn_pause.config(state="disabled")
                btn_resume.config(state="disabled")
                logger.info("用户停止视频识别")

            def do_pause():
                pause_event.set()
                btn_pause.config(state="disabled")
                btn_resume.config(state="normal")
                logger.info("用户暂停视频识别")

            def do_resume():
                pause_event.clear()
                btn_pause.config(state="normal")
                btn_resume.config(state="disabled")
                logger.info("用户恢复视频识别")

            btn_stop = tk.Button(ctrl_frame, text="停止", command=do_stop, width=8, bg="#e74c3c", fg="white")
            btn_stop.pack(side="left", padx=2)
            btn_pause = tk.Button(ctrl_frame, text="暂停", command=do_pause, width=8, bg="#f39c12")
            btn_pause.pack(side="left", padx=2)
            btn_resume = tk.Button(ctrl_frame, text="继续", command=do_resume, width=8, bg="#2ecc71", state="disabled")
            btn_resume.pack(side="left", padx=2)

            # 启动检测线程
            def run_detection():
                try:
                    from plate_detector import plate_detection
                    plate_detection(source, video_label, mode, stop_event=stop_event, pause_event=pause_event)
                except Exception as e:
                    logger.error("检测线程异常: %s", e)
                    messagebox.showerror("错误", f"检测异常: {e}")

            detection_thread = threading.Thread(target=run_detection, daemon=True)
            detection_thread.start()

        def parking_monitor():
            video_container = tk.Frame(content_frame, bg="#ecf0f1")
            video_container.pack(side="left", padx=10, pady=5)

            tk.Label(video_container, text="容量检测系统", font=("Microsoft YaHei", 14, "bold"), bg="#ecf0f1").pack(anchor="nw", pady=5)
            video_label = tk.Label(video_container, bg="black")
            video_label.pack(anchor="nw")

            ctrl_frame = tk.Frame(video_container, bg="#ecf0f1")
            ctrl_frame.pack(fill="x", pady=5)

            stop_event = threading.Event()
            pause_event = threading.Event()

            def do_stop():
                stop_event.set()
                btn_stop.config(state="disabled")
                logger.info("用户停止容量检测")

            def do_pause():
                pause_event.set()
                btn_pause.config(state="disabled")
                btn_resume.config(state="normal")

            def do_resume():
                pause_event.clear()
                btn_pause.config(state="normal")
                btn_resume.config(state="disabled")

            btn_stop = tk.Button(ctrl_frame, text="停止", command=do_stop, width=8, bg="#e74c3c", fg="white")
            btn_stop.pack(side="left", padx=2)
            btn_pause = tk.Button(ctrl_frame, text="暂停", command=do_pause, width=8, bg="#f39c12")
            btn_pause.pack(side="left", padx=2)
            btn_resume = tk.Button(ctrl_frame, text="继续", command=do_resume, width=8, bg="#2ecc71", state="disabled")
            btn_resume.pack(side="left", padx=2)

            import stream
            stream.parking_detection(video_label, stop_event=stop_event, pause_event=pause_event)

        # 左侧菜单按钮
        tk.Label(left_frame, text="车牌识别与智能计费系统", font=("Microsoft YaHei", 14, "bold"),
                 bg="#2c3e50", fg="white", wraplength=220).pack(pady=20)

        tk.Button(left_frame, text="汽车进入", command=lambda: detection(mode="default"),
                  width=20, bg="#3498db", fg="white", font=("Microsoft YaHei", 10)).pack(pady=10)
        tk.Button(left_frame, text="汽车出库", command=lambda: detection(mode="exit"),
                  width=20, bg="#3498db", fg="white", font=("Microsoft YaHei", 10)).pack(pady=10)
        tk.Button(left_frame, text="容量检测", command=parking_monitor,
                  width=20, bg="#9b59b6", fg="white", font=("Microsoft YaHei", 10)).pack(pady=10)
        tk.Button(left_frame, text="退出系统", command=main_window.destroy,
                  width=20, bg="#e74c3c", fg="white", font=("Microsoft YaHei", 10)).pack(pady=10)

    toll()
    main_window.mainloop()
