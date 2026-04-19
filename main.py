from login_window import *
from db import initialize_db as init_parking_db
from sql import initialize_db as init_user_db

if __name__ == "__main__":
    init_parking_db()
    init_user_db()
    login_window()