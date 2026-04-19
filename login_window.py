import tkinter as tk
from tkinter import messagebox
import sqlite3
from PIL import Image, ImageTk
from main_window import *
def login_window():
    root = tk.Tk()

    root.title("智能停车场")

    # 设置窗口大小
    window_width = 400
    window_height = 300

    # 获取屏幕的宽度和高度
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # 计算窗口的左上角位置，使其居中
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)

    # 设置窗口大小和位置
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # 数据库
    def validate_login(username, password):
        conn = sqlite3.connect('user_data.db')
        c = conn.cursor()

        # 查询数据库，验证用户名和密码
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        result = c.fetchone()

        conn.close()

        if result:
            return True
        else:
            return False

    # 登陆界面

    # 使用Pillow加载图片
    image = Image.open("icon.png")
    resized_image = image.resize((32, 32))
    photo = ImageTk.PhotoImage(resized_image)

    tk.Label(root, text="欢迎使用", image=photo, compound="top").place(x=170, y=10)

    tk.Label(root, text="用户名:").place(x=50, y=120)
    username_entry = tk.Entry(root)
    username_entry.place(x=150, y=120)

    tk.Label(root, text="密码:").place(x=50, y=150)
    password_entry = tk.Entry(root, show="*")  # 使用 show="*" 隐藏密码
    password_entry.place(x=150, y=150)

    # 登录按钮功能
    def login():
        username = username_entry.get()
        password = password_entry.get()

        if validate_login(username, password):
            # 在此可以加入进入主界面的逻辑
            messagebox.showinfo("登录成功", "欢迎进入系统！")
            root.destroy()  # 关闭登录窗口
            open_main_window()

        else:
            messagebox.showerror("登录失败", "用户名或密码错误")

    # 创建登录按钮
    login_button = tk.Button(root, text="登录", command=login)
    login_button.place(x=170, y=200)

    tk.mainloop()
