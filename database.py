import sqlite3
import os

DB_PATH = 'logs.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS log_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            error_count INTEGER,
            warning_count INTEGER,
            failed_count INTEGER,
            timeout_count INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def save_log_metadata(filename, counts):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO log_history (filename, error_count, warning_count, failed_count, timeout_count)
        VALUES (?, ?, ?, ?, ?)
    ''', (filename, counts['ERROR'], counts['WARNING'], counts['FAILED'], counts['TIMEOUT']))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_log_metadata(log_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM log_history WHERE id = ?', (log_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
