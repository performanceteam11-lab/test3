import sqlite3
import os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "monitoring.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            check_date    TEXT    NOT NULL,
            keyword       TEXT    NOT NULL,
            device        TEXT    NOT NULL,
            brand         TEXT    NOT NULL,
            campaign      TEXT    NOT NULL,
            group_name    TEXT    NOT NULL,
            exposed       INTEGER NOT NULL DEFAULT 0,
            creative_count INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id       INTEGER NOT NULL,
            screenshot_path TEXT    NOT NULL,
            creative_index  INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(result_id) REFERENCES results(id)
        )
    """)
    conn.commit()
    conn.close()


def save_result(check_date, keyword, device, brand, campaign, group_name,
                exposed, creative_count, screenshot_paths):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO results
            (check_date, keyword, device, brand, campaign, group_name, exposed, creative_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (check_date, keyword, device, brand, campaign, group_name,
          1 if exposed else 0, creative_count))
    result_id = c.lastrowid
    for i, path in enumerate(screenshot_paths):
        c.execute("""
            INSERT INTO screenshots (result_id, screenshot_path, creative_index)
            VALUES (?, ?, ?)
        """, (result_id, path, i))
    conn.commit()
    conn.close()
    return result_id


def get_results_by_date(check_date):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT
            r.*,
            GROUP_CONCAT(s.screenshot_path ORDER BY s.creative_index) AS screenshot_paths
        FROM results r
        LEFT JOIN screenshots s ON r.id = s.result_id
        WHERE r.check_date = ?
        GROUP BY r.id
        ORDER BY r.brand, r.device, r.keyword
    """, (check_date,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_available_dates():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT check_date FROM results ORDER BY check_date DESC")
    dates = [row[0] for row in c.fetchall()]
    conn.close()
    return dates


def get_summary_by_date(check_date):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT
            brand,
            device,
            COUNT(*) AS total,
            SUM(exposed) AS exposed_count
        FROM results
        WHERE check_date = ?
        GROUP BY brand, device
    """, (check_date,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows
