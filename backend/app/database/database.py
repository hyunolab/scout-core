import sqlite3

DATABASE = "nuclear_scout.db"


def get_connection():
    return sqlite3.connect(DATABASE)