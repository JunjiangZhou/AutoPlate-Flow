# -*- coding: UTF-8 -*-
"""
智能停车场管理系统主界面（多页面多路监控版）
特性：入库/出库/容量检测三页独立、每页支持多路视频、完善的数据库管理
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue

from utils.logger import get_logger
from utils.database import Database
from config import REFRESH_INTERVAL, VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT

logger = get_logger(__name__)
_db = Database()

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
        # 从数据库读取最新动态费率和占用率
        cur, pct = _db.get_latest_hourly_rate(base_rate)
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

    # ========== 全局布局 ==========
    left_frame = tk.Frame(main_window, width=260, bg="#e8e8e8")
    left_frame.pack(side="left", fill="y")
    left_frame.pack_propagate(False)

    right_frame = tk.Frame(main_window, bg="#ffffff")
    right_frame.pack(side="left", expand=True, fill="both")

    # 底部数据库面板
    bottom_frame = tk.Frame(right_frame, bg="#f0f0f0", height=220)
    bottom_frame.pack(side="bottom", fill="x")
    bottom_frame.pack_propagate(False)

    notebook_bottom = ttk.Notebook(bottom_frame)
    notebook_bottom.pack(fill="both", expand=True)

    tab_records = tk.Frame(notebook_bottom)
    notebook_bottom.add(tab_records, text="停车记录")
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

    tab_current = tk.Frame(notebook_bottom)
    notebook_bottom.add(tab_current, text="当前在库")
    current_tree = ttk.Treeview(tab_current, columns=('ID', 'Plate', 'Entry', 'Rate'), show='headings')
    for col, text, width in [('ID', 'ID', 50), ('Plate', '车牌号', 150), ('Entry', '入库时间', 200), ('Rate', '费率', 80)]:
        current_tree.heading(col, text=text)
        current_tree.column(col, width=width, anchor='center')
    current_tree.pack(side="left", fill="both", expand=True)
    scrollbar2 = ttk.Scrollbar(tab_current, orient="vertical", command=current_tree.yview)
    current_tree.configure(yscrollcommand=scrollbar2.set)
    scrollbar2.pack(side="right", fill="y")

    tab_stats = tk.Frame(notebook_bottom)
    notebook_bottom.add(tab_stats, text="收入统计")
    stats_tree = ttk.Treeview(tab_stats, columns=('Date', 'Count', 'Revenue', 'Current'), show='headings')
    for col, text, width in [('Date', '日期', 120), ('Count', '总车次', 80), ('Revenue', '收入(元)', 100), ('Current', '在库数', 80)]:
        stats_tree.heading(col, text=text)
        stats_tree.column(col, width=width, anchor='center')
    stats_tree.pack(side="left", fill="both", expand=True)
    scrollbar3 = ttk.Scrollbar(tab_stats, orient="vertical", command=stats_tree.yview)
    stats_tree.configure(yscrollcommand=scrollbar3.set)
    scrollbar3.pack(side="right", fill="y")

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

    # ========== 右侧内容区（Notebook 三页） ==========
    content_notebook = ttk.Notebook(right_frame)
    content_notebook.pack(side="top", expand=True, fill="both")

    page_entry = tk.Frame(content_notebook, bg="#ffffff")
    page_exit = tk.Frame(content_notebook, bg="#ffffff")
    page_parking = tk.Frame(content_notebook, bg="#ffffff")
    content_notebook.add(page_entry, text="入库管理")
    content_notebook.add(page_exit, text="出库管理")
    content_notebook.add(page_parking, text="容量检测")

    # ========== 页面构建辅助函数 ==========
    def build_page(parent_page, mode, title_prefix):
        """为某个页面创建顶部工具栏和可滚动的视频区域"""
        toolbar = tk.Frame(parent_page, bg="#f5f5f5", height=40)
        toolbar.pack(fill="x", padx=5, pady=5)
        toolbar.pack_propagate(False)

        def add_monitor():
            ask_and_start(parent_page, mode, title_prefix)

        tk.Button(toolbar, text="+ 添加监控", command=add_monitor,
                  fg="black", font=("Microsoft YaHei", 9, "bold"),
                  cursor="hand2").pack(side="left", padx=5, pady=5)

        tk.Label(toolbar, text=f"{title_prefix} — 可同时运行多路视频",
                 bg="#f5f5f5", font=("Microsoft YaHei", 9), fg="#555").pack(side="left", padx=10)

        # 视频容器区域（用 Canvas + Frame 实现滚动）
        canvas = tk.Canvas(parent_page, bg="#ffffff", highlightthickness=0)
        scrollbar_v = ttk.Scrollbar(parent_page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar_v.set)
        scrollbar_v.pack(side="right", fill="y")
        canvas.pack(side="left", expand=True, fill="both")

        video_grid = tk.Frame(canvas, bg="#ffffff")
        canvas_window = canvas.create_window((0, 0), window=video_grid, anchor="nw")

        def on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)

        video_grid.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

        return video_grid

    entry_grid = build_page(page_entry, "default", "入库识别")
    exit_grid = build_page(page_exit, "exit", "出库识别")
    parking_grid = build_page(page_parking, "parking", "容量检测")

    # ========== 核心功能：弹窗选源 + 启动监控 ==========
    def ask_and_start(parent_grid, mode, title_prefix):
        """弹窗让用户选择视频源，确认后在指定 grid 中添加监控面板"""
        try:
            if mode == "default":
                file_title = "选择入库视频/摄像头"
            elif mode == "exit":
                file_title = "选择出库视频/摄像头"
            else:
                file_title = "选择容量检测视频/摄像头"

            dialog = tk.Toplevel(main_window)
            dialog.title(file_title)
            dialog.geometry("380x220")
            dialog.transient(main_window)
            dialog.grab_set()
            dialog.lift()
            dialog.focus_force()

            tk.Label(dialog, text="选择视频源:", font=("Microsoft YaHei", 10)).pack(pady=8)
            source_var = tk.StringVar()
            source_entry = tk.Entry(dialog, textvariable=source_var, width=40)
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

            btn_row = tk.Frame(dialog)
            btn_row.pack(pady=5)
            tk.Button(btn_row, text="选择文件", command=choose_file, width=12,
                      fg="black", font=("Microsoft YaHei", 10)).pack(side="left", padx=5)
            tk.Button(btn_row, text="使用摄像头", command=use_camera, width=12,
                      fg="black", font=("Microsoft YaHei", 10)).pack(side="left", padx=5)

            def confirm():
                source = source_var.get().strip()
                if not source:
                    messagebox.showwarning("提示", "请选择视频源")
                    return
                dialog.destroy()
                start_monitor(parent_grid, source, mode, title_prefix)

            tk.Button(dialog, text="开始识别", command=confirm, width=15,
                      fg="black", font=("Microsoft YaHei", 10, "bold")).pack(pady=12)
        except Exception as e:
            logger.error("ask_and_start 异常: %s", e, exc_info=True)
            messagebox.showerror("错误", f"打开识别窗口失败: {e}")

    def start_monitor(parent_grid, source, mode, title_prefix):
        """在指定的 grid 中添加一个视频面板并启动检测线程"""
        try:
            # 每个监控面板是一个独立的 Frame
            panel = tk.Frame(parent_grid, bg="#ffffff", bd=1, relief="solid")
            panel.pack(side="top", fill="x", padx=5, pady=5)

            header = tk.Frame(panel, bg="#eeeeee")
            header.pack(fill="x")
            tk.Label(header, text=f"{title_prefix} — {source}",
                     bg="#eeeeee", font=("Microsoft YaHei", 9, "bold")).pack(side="left", padx=5)

            video_label = tk.Label(panel, bg="black", width=VIDEO_DISPLAY_WIDTH, height=VIDEO_DISPLAY_HEIGHT)
            video_label.pack(anchor="nw", padx=5, pady=5)

            ctrl_frame = tk.Frame(panel, bg="#ffffff")
            ctrl_frame.pack(fill="x", padx=5, pady=(0, 5))

            stop_event = threading.Event()
            pause_event = threading.Event()

            def do_stop():
                stop_event.set()
                btn_stop.config(state="disabled")
                btn_pause.config(state="disabled")
                btn_resume.config(state="disabled")
                logger.info("用户停止监控: %s", source)

            def do_pause():
                pause_event.set()
                btn_pause.config(state="disabled")
                btn_resume.config(state="normal")
                logger.info("用户暂停监控: %s", source)

            def do_resume():
                pause_event.clear()
                btn_pause.config(state="normal")
                btn_resume.config(state="disabled")
                logger.info("用户恢复监控: %s", source)

            def do_close_panel():
                stop_event.set()
                panel.destroy()
                logger.info("关闭监控面板: %s", source)

            btn_stop = tk.Button(ctrl_frame, text="停止", command=do_stop, width=8, bg="#e74c3c", fg="white")
            btn_stop.pack(side="left", padx=2)
            btn_pause = tk.Button(ctrl_frame, text="暂停", command=do_pause, width=8, bg="#f39c12")
            btn_pause.pack(side="left", padx=2)
            btn_resume = tk.Button(ctrl_frame, text="继续", command=do_resume, width=8, bg="#2ecc71", state="disabled")
            btn_resume.pack(side="left", padx=2)
            tk.Button(ctrl_frame, text="关闭面板", command=do_close_panel, width=10, bg="#95a5a6").pack(side="left", padx=10)

            def run_detection():
                try:
                    if mode in ("default", "exit"):
                        from plate_detector import plate_detection
                        logger.info("启动车牌识别: source=%s, mode=%s", source, mode)
                        plate_detection(source, video_label, mode, stop_event=stop_event, pause_event=pause_event)
                    else:
                        import stream
                        logger.info("启动容量检测: source=%s", source)
                        stream.parking_detection_with_source(source, video_label, stop_event=stop_event, pause_event=pause_event)
                except Exception as e:
                    logger.error("检测线程异常: %s", e, exc_info=True)
                    error_queue.put(f"检测异常: {e}")

            detection_thread = threading.Thread(target=run_detection, daemon=True)
            detection_thread.start()
        except Exception as e:
            logger.error("start_monitor 异常: %s", e, exc_info=True)
            messagebox.showerror("错误", f"启动监控失败: {e}")

    # ========== 左侧菜单内容 ==========
    tk.Label(left_frame, text="智能停车场管理系统", font=("Microsoft YaHei", 14, "bold"),
             bg="#e8e8e8", fg="#000000", justify="center").pack(pady=(15, 5))

    rate_status_label = tk.Label(left_frame, text="当前动态费率: --", font=("Microsoft YaHei", 9),
                                  bg="#d0d0d0", fg="#006400", justify="left", padx=8, pady=5)
    rate_status_label.pack(fill="x", padx=10, pady=5)

    base_rate_label = tk.Label(left_frame, text="基础费率: --", font=("Microsoft YaHei", 8),
                                bg="#e8e8e8", fg="#333333", justify="left", padx=10)
    base_rate_label.pack(fill="x", pady=(0, 5))

    tk.Frame(left_frame, height=2, bg="#bbbbbb").pack(fill="x", padx=10, pady=5)

    tk.Label(left_frame, text="费率设置", font=("Microsoft YaHei", 11, "bold"),
             bg="#e8e8e8", fg="#000000").pack(anchor="w", padx=15, pady=(5, 2))

    settings_frame = tk.Frame(left_frame, bg="#e8e8e8", padx=15)
    settings_frame.pack(fill="x")

    def make_setting_row(parent, label_text, default_val, row):
        tk.Label(parent, text=label_text, font=("Microsoft YaHei", 9),
                 bg="#e8e8e8", fg="#000000").grid(row=row, column=0, sticky="w", pady=2)
        entry = tk.Entry(parent, width=8, font=("Microsoft YaHei", 9), justify="center", relief="solid", bd=1)
        entry.grid(row=row, column=1, sticky="e", pady=2, padx=(5, 0))
        entry.insert(0, str(default_val))
        return entry

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
              fg="black", font=("Microsoft YaHei", 9),
              cursor="hand2").grid(row=5, column=0, columnspan=2, pady=8, sticky="ew")

    tk.Frame(left_frame, height=2, bg="#bbbbbb").pack(fill="x", padx=10, pady=5)

    tk.Label(left_frame, text="页面切换", font=("Microsoft YaHei", 11, "bold"),
             bg="#e8e8e8", fg="#000000").pack(anchor="w", padx=15, pady=(5, 2))

    nav_frame = tk.Frame(left_frame, bg="#e8e8e8", padx=15)
    nav_frame.pack(fill="x")

    def switch_page(index):
        content_notebook.select(index)

    def make_nav_btn(parent, text, idx):
        tk.Button(parent, text=text, command=lambda: switch_page(idx),
                  fg="black", font=("Microsoft YaHei", 10, "bold"),
                  relief="flat", cursor="hand2", width=20, pady=6).pack(pady=5, fill="x")

    make_nav_btn(nav_frame, "入库管理", page_entry)
    make_nav_btn(nav_frame, "出库管理", page_exit)
    make_nav_btn(nav_frame, "容量检测", page_parking)

    tk.Frame(left_frame, height=2, bg="#bbbbbb").pack(fill="x", padx=10, pady=5)
    tk.Button(left_frame, text="退出系统", command=main_window.destroy,
              fg="black", font=("Microsoft YaHei", 10, "bold"),
              relief="flat", cursor="hand2", width=20, pady=6).pack(pady=10)

    # ========== 线程安全错误队列 ==========
    error_queue = queue.Queue()

    def check_error_queue():
        try:
            while True:
                err_msg = error_queue.get_nowait()
                messagebox.showerror("错误", err_msg)
        except queue.Empty:
            pass
        main_window.after(200, check_error_queue)

    check_error_queue()

    # ========== 启动 ==========
    auto_refresh()
    main_window.mainloop()
