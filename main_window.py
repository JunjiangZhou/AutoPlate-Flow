# -*- coding: UTF-8 -*-
"""
智能停车场管理系统主界面（重构版）
特性：完善的数据库管理、视频暂停/停止控制、摄像头支持、动态费率设置
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading

from utils.logger import get_logger
from utils.database import Database
from config import REFRESH_INTERVAL, VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT

logger = get_logger(__name__)
_db = Database()

# 控制信号存储（按视频标签管理）
_video_controls = {}

# 当前费率状态（供界面显示）
_current_rate_info = {"occupied_pct": 0.0, "current_rate": 10.0, "base_rate": 10.0}


def _refresh_rate_display(rate_label, base_label):
    """刷新费率显示标签"""
    try:
        base_rate = _db.get_setting('base_hourly_rate', 10.0)
        high_mul = _db.get_setting('rate_high_multiplier', 1.5)
        low_mul = _db.get_setting('rate_low_multiplier', 0.8)
        high_thr = _db.get_setting('occupancy_high_threshold', 80.0)
        low_thr = _db.get_setting('occupancy_low_threshold', 50.0)

        _current_rate_info['base_rate'] = base_rate

        rate_text = (
            f"基础费率: {base_rate:.1f}元/小时\n"
            f"占用>{high_thr:.0f}%: x{high_mul:.1f}\n"
            f"占用<{low_thr:.0f}%: x{low_mul:.1f}"
        )
        base_label.config(text=rate_text)

        # 显示当前动态费率（如果容量检测正在运行）
        pct = _current_rate_info.get('occupied_pct', 0)
        cur = _current_rate_info.get('current_rate', base_rate)
        rate_label.config(text=f"当前动态费率: {cur:.2f}元/小时\n车位占用率: {pct:.1f}%")
    except Exception as e:
        logger.error("刷新费率显示失败: %s", e)


def _save_settings(entries, rate_label, base_label):
    """保存费率设置到数据库"""
    try:
        base_rate = float(entries['base'].get().strip())
        high_mul = float(entries['high_mul'].get().strip())
        low_mul = float(entries['low_mul'].get().strip())
        high_thr = float(entries['high_thr'].get().strip())
        low_thr = float(entries['low_thr'].get().strip())

        if base_rate <= 0 or high_mul <= 0 or low_mul <= 0:
            messagebox.showwarning("输入错误", "费率和倍率必须大于0")
            return
        if not (0 < low_thr < high_thr < 100):
            messagebox.showwarning("输入错误", "阈值需在 0~100 之间，且 低阈值 < 高阈值")
            return

        _db.set_setting('base_hourly_rate', base_rate)
        _db.set_setting('rate_high_multiplier', high_mul)
        _db.set_setting('rate_low_multiplier', low_mul)
        _db.set_setting('occupancy_high_threshold', high_thr)
        _db.set_setting('occupancy_low_threshold', low_thr)

        messagebox.showinfo("保存成功", "费率设置已更新")
        _refresh_rate_display(rate_label, base_label)
        logger.info("费率设置已更新: 基础=%.2f, 高倍=%.2f, 低倍=%.2f", base_rate, high_mul, low_mul)
    except ValueError:
        messagebox.showwarning("输入错误", "请输入有效的数字")
    except Exception as e:
        logger.error("保存设置失败: %s", e)
        messagebox.showerror("错误", f"保存失败: {e}")


def open_main_window():
    main_window = tk.Tk()
    main_window.title("智能停车场管理系统")
    main_window.geometry("1280x720")

    # ========== 全局布局：左侧菜单 + 右侧区域 ==========
    # 左侧菜单栏
    left_frame = tk.Frame(main_window, width=260, bg="#2c3e50")
    left_frame.pack(side="left", fill="y")
    left_frame.pack_propagate(False)

    # 右侧主区域
    right_frame = tk.Frame(main_window, bg="#ecf0f1")
    right_frame.pack(side="left", expand=True, fill="both")

    # 内容区
    content_frame = tk.Frame(right_frame, bg="#ecf0f1")
    content_frame.pack(side="top", expand=True, fill="both")

    # 底部数据库面板
    bottom_frame = tk.Frame(right_frame, bg="#bdc3c7", height=220)
    bottom_frame.pack(side="bottom", fill="x")
    bottom_frame.pack_propagate(False)

    # ========== 底部数据库面板（Notebook 多标签页） ==========
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
        refresh_tree(records_tree, _db.get_all_records())
        refresh_tree(current_tree, _db.get_current_parked())
        refresh_tree(stats_tree, _db.get_revenue_stats(days=7))
        _refresh_rate_display(rate_status_label, base_rate_label)
        bottom_frame.after(REFRESH_INTERVAL, auto_refresh)

    # ========== 左侧菜单内容 ==========
    # 标题
    tk.Label(left_frame, text="智能停车场\n管理系统", font=("Microsoft YaHei", 14, "bold"),
             bg="#f8f9fa", fg="#212529", justify="center").pack(pady=(15, 5))

    # 动态费率显示区
    rate_status_label = tk.Label(left_frame, text="当前动态费率: --", font=("Microsoft YaHei", 9),
                                  bg="#e9ecef", fg="#198754", justify="left", padx=8, pady=5)
    rate_status_label.pack(fill="x", padx=10, pady=5)

    base_rate_label = tk.Label(left_frame, text="基础费率: --", font=("Microsoft YaHei", 8),
                                bg="#f8f9fa", fg="#6c757d", justify="left", padx=10)
    base_rate_label.pack(fill="x", pady=(0, 5))

    # 分隔线
    tk.Frame(left_frame, height=2, bg="#dee2e6").pack(fill="x", padx=10, pady=5)

    # 费率设置区
    tk.Label(left_frame, text="费率设置", font=("Microsoft YaHei", 11, "bold"),
             bg="#f8f9fa", fg="#212529").pack(anchor="w", padx=15, pady=(5, 2))

    settings_frame = tk.Frame(left_frame, bg="#f8f9fa", padx=15)
    settings_frame.pack(fill="x")

    def make_setting_row(parent, label_text, default_val, row):
        tk.Label(parent, text=label_text, font=("Microsoft YaHei", 9),
                 bg="#f8f9fa", fg="#495057").grid(row=row, column=0, sticky="w", pady=2)
        entry = tk.Entry(parent, width=8, font=("Microsoft YaHei", 9), justify="center",
                         relief="solid", bd=1)
        entry.grid(row=row, column=1, sticky="e", pady=2, padx=(5, 0))
        entry.insert(0, str(default_val))
        return entry

    # 读取当前设置
    base_rate_val = _db.get_setting('base_hourly_rate', 10.0)
    high_mul_val = _db.get_setting('rate_high_multiplier', 1.5)
    low_mul_val = _db.get_setting('rate_low_multiplier', 0.8)
    high_thr_val = _db.get_setting('occupancy_high_threshold', 80.0)
    low_thr_val = _db.get_setting('occupancy_low_threshold', 50.0)

    entries = {
        'base': make_setting_row(settings_frame, "基础费率(元)", base_rate_val, 0),
        'high_mul': make_setting_row(settings_frame, "高占用倍率", high_mul_val, 1),
        'low_mul': make_setting_row(settings_frame, "低占用倍率", low_mul_val, 2),
        'high_thr': make_setting_row(settings_frame, "高占用阈值(%)", high_thr_val, 3),
        'low_thr': make_setting_row(settings_frame, "低占用阈值(%)", low_thr_val, 4),
    }

    tk.Button(settings_frame, text="保存设置",
              command=lambda: _save_settings(entries, rate_status_label, base_rate_label),
              bg="#3498db", fg="white", font=("Microsoft YaHei", 9),
              cursor="hand2").grid(row=5, column=0, columnspan=2, pady=8, sticky="ew")

    # 分隔线
    tk.Frame(left_frame, height=2, bg="#dee2e6").pack(fill="x", padx=10, pady=5)

    # 功能按钮区
    tk.Label(left_frame, text="功能操作", font=("Microsoft YaHei", 11, "bold"),
             bg="#f8f9fa", fg="#212529").pack(anchor="w", padx=15, pady=(5, 2))

    btn_frame = tk.Frame(left_frame, bg="#f8f9fa", padx=15)
    btn_frame.pack(fill="x")

    def make_btn(parent, text, cmd, color):
        tk.Button(parent, text=text, command=cmd,
                  bg=color, fg="white", font=("Microsoft YaHei", 10),
                  relief="flat", cursor="hand2",
                  width=20, pady=4).pack(pady=6, fill="x")

    make_btn(btn_frame, "汽车进入", lambda: detection(mode="default"), "#3498db")
    make_btn(btn_frame, "汽车出库", lambda: detection(mode="exit"), "#3498db")
    make_btn(btn_frame, "容量检测", parking_monitor, "#9b59b6")
    make_btn(btn_frame, "退出系统", main_window.destroy, "#e74c3c")

    # ========== 主功能逻辑 ==========
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

        btn_frame_d = tk.Frame(dialog)
        btn_frame_d.pack(pady=5)
        tk.Button(btn_frame_d, text="选择文件", command=choose_file).pack(side="left", padx=5)
        tk.Button(btn_frame_d, text="使用摄像头", command=use_camera).pack(side="left", padx=5)

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

    # 启动自动刷新
    auto_refresh()
    main_window.mainloop()
