# -*- coding: UTF-8 -*-
"""
登录窗口（重构版）
特性：密码加密存储、输入校验、界面美化
使用统一数据库 parking_system.db
"""
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

from main_window import open_main_window
from utils.logger import get_logger
from utils.database import Database

logger = get_logger(__name__)
_db = Database()


def _init_default_user():
    """初始化默认管理员账号（单库模式）"""
    try:
        _db.init_user_table()
    except Exception as e:
        logger.error("初始化用户表失败: %s", e)


def validate_login(username, password):
    """验证用户名和密码"""
    return _db.validate_login(username, password)


def login_window():
    _init_default_user()

    root = tk.Tk()
    root.title("智能停车场管理系统 - 登录")
    root.resizable(False, False)

    window_width = 420
    window_height = 440
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # 主容器
    container = tk.Frame(root, bg="#ffffff")
    container.pack(fill="both", expand=True)

    # 顶部标题区
    header = tk.Frame(container, bg="#2c3e50", height=100)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="智能停车场管理系统", font=("Microsoft YaHei", 18, "bold"),
             bg="#2c3e50", fg="white").pack(pady=15)
    tk.Label(header, text="Plate Recognition & Parking Management",
             font=("Microsoft YaHei", 10), bg="#2c3e50", fg="#bdc3c7").pack()

    # 图标
    try:
        image = Image.open("icon.png")
        resized_image = image.resize((48, 48))
        photo = ImageTk.PhotoImage(resized_image)
        icon_label = tk.Label(container, image=photo, bg="#ffffff")
        icon_label.image = photo
        icon_label.pack(pady=10)
    except Exception:
        pass

    # 表单区
    form_frame = tk.Frame(container, bg="#ffffff", padx=40)
    form_frame.pack(fill="both", expand=True)

    tk.Label(form_frame, text="用户名", font=("Microsoft YaHei", 11), bg="#ffffff", fg="#2c3e50").pack(anchor="w", pady=(10, 2))
    username_entry = tk.Entry(form_frame, font=("Microsoft YaHei", 11), relief="solid", bd=1)
    username_entry.pack(fill="x", ipady=4)
    username_entry.focus()

    tk.Label(form_frame, text="密码", font=("Microsoft YaHei", 11), bg="#ffffff", fg="#2c3e50").pack(anchor="w", pady=(12, 2))
    password_entry = tk.Entry(form_frame, show="*", font=("Microsoft YaHei", 11), relief="solid", bd=1)
    password_entry.pack(fill="x", ipady=4)

    # 记住密码（UI占位，功能可后续扩展）
    remember_var = tk.BooleanVar()
    tk.Checkbutton(form_frame, text="记住密码", variable=remember_var,
                   bg="#ffffff", font=("Microsoft YaHei", 9)).pack(anchor="w", pady=8)

    def login():
        username = username_entry.get().strip()
        password = password_entry.get().strip()

        if not username:
            messagebox.showwarning("输入错误", "请输入用户名")
            return
        if not password:
            messagebox.showwarning("输入错误", "请输入密码")
            return

        if validate_login(username, password):
            logger.info("用户 %s 登录成功", username)
            messagebox.showinfo("登录成功", f"欢迎回来，{username}！")
            root.destroy()
            open_main_window()
        else:
            logger.warning("用户 %s 登录失败", username)
            messagebox.showerror("登录失败", "用户名或密码错误")
            password_entry.delete(0, tk.END)

    # 绑定回车键登录
    root.bind('<Return>', lambda e: login())

    login_btn = tk.Button(form_frame, text="登 录", command=login,
                          bg="#3498db", fg="white", font=("Microsoft YaHei", 12, "bold"),
                          relief="flat", cursor="hand2")
    login_btn.pack(fill="x", pady=(5, 15), ipady=4)

    # 底部信息
    tk.Label(container, text="默认账号: admin / admin", font=("Microsoft YaHei", 9),
             bg="#ecf0f1", fg="#7f8c8d").pack(fill="x", ipady=6)

    tk.mainloop()
