"""Capa de datos SQLite para Empacadora San Juan.

Sigue el mismo patron dependency-free que usamos en barberia-demo: todo
en dicts planos, sin ORM. Para 4 empleados y un puñado de admins esto
sobra por años -- YAGNI antes que SQLAlchemy.

Persistencia en produccion: el archivo vive en un volumen de Fly.io
(ver fly.toml + DEPLOY.md) para que sobreviva reinicios/redeploys.
"""
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "empacadora.db"))

DEFAULT_HOURLY_RATE = 1500.0
DEFAULT_CURRENCY_SYMBOL = "₡"
DEFAULT_BUSINESS_NAME = "Empacadora San Juan"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _all(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            pin_code TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            clock_in TEXT NOT NULL,
            clock_out TEXT,
            is_overtime INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            business_name TEXT NOT NULL,
            hourly_rate REAL NOT NULL,
            overtime_hourly_rate REAL NOT NULL,
            currency_symbol TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    if not _one(conn, "SELECT id FROM settings WHERE id = 1"):
        conn.execute(
            """INSERT INTO settings (id, business_name, hourly_rate, overtime_hourly_rate, currency_symbol, updated_at)
               VALUES (1, ?, ?, ?, ?, ?)""",
            (DEFAULT_BUSINESS_NAME, DEFAULT_HOURLY_RATE, DEFAULT_HOURLY_RATE, DEFAULT_CURRENCY_SYMBOL, datetime.now().isoformat()),
        )
        conn.commit()

    conn.close()


def seed_default_admin(username: str, password_hash: str) -> None:
    """Crea el primer admin solo si la tabla esta vacia. Idempotente."""
    conn = get_conn()
    count = _one(conn, "SELECT COUNT(*) AS n FROM admin_users")["n"]
    if count == 0:
        conn.execute(
            "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.now().isoformat()),
        )
        conn.commit()
    conn.close()


# ── Employees ────────────────────────────────────────────────────────

def gen_unique_pin(conn) -> str:
    for _ in range(50):
        pin = f"{secrets.randbelow(10000):04d}"
        if not _one(conn, "SELECT id FROM employees WHERE pin_code = ?", (pin,)):
            return pin
    raise RuntimeError("No se pudo generar un PIN unico -- ¿demasiados empleados?")


def get_employees(include_inactive: bool = True):
    conn = get_conn()
    sql = "SELECT * FROM employees"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY full_name"
    rows = _all(conn, sql)
    conn.close()
    return rows


def get_employee(employee_id: int):
    conn = get_conn()
    row = _one(conn, "SELECT * FROM employees WHERE id = ?", (employee_id,))
    conn.close()
    return row


def get_employee_by_pin(pin_code: str):
    conn = get_conn()
    row = _one(conn, "SELECT * FROM employees WHERE pin_code = ? AND active = 1", (pin_code,))
    conn.close()
    return row


def create_employee(full_name: str, pin_code: str | None = None) -> dict:
    conn = get_conn()
    pin = pin_code or gen_unique_pin(conn)
    conn.execute(
        "INSERT INTO employees (full_name, pin_code, active, created_at) VALUES (?, ?, 1, ?)",
        (full_name, pin, datetime.now().isoformat()),
    )
    conn.commit()
    row = _one(conn, "SELECT * FROM employees WHERE pin_code = ?", (pin,))
    conn.close()
    return row


def update_employee(employee_id: int, full_name: str, active: bool) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE employees SET full_name = ?, active = ? WHERE id = ?",
        (full_name, 1 if active else 0, employee_id),
    )
    conn.commit()
    conn.close()


def reset_employee_pin(employee_id: int) -> str:
    conn = get_conn()
    pin = gen_unique_pin(conn)
    conn.execute("UPDATE employees SET pin_code = ? WHERE id = ?", (pin, employee_id))
    conn.commit()
    conn.close()
    return pin


# ── Time entries ─────────────────────────────────────────────────────

def get_open_entry(employee_id: int):
    conn = get_conn()
    row = _one(
        conn,
        "SELECT * FROM time_entries WHERE employee_id = ? AND clock_out IS NULL ORDER BY clock_in DESC LIMIT 1",
        (employee_id,),
    )
    conn.close()
    return row


def clock_in(employee_id: int) -> dict:
    conn = get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO time_entries (employee_id, clock_in, created_at) VALUES (?, ?, ?)",
        (employee_id, now, now),
    )
    conn.commit()
    row = _one(conn, "SELECT * FROM time_entries WHERE employee_id = ? AND clock_in = ?", (employee_id, now))
    conn.close()
    return row


def clock_out(entry_id: int) -> dict:
    conn = get_conn()
    now = datetime.now().isoformat()
    conn.execute("UPDATE time_entries SET clock_out = ? WHERE id = ?", (now, entry_id))
    conn.commit()
    row = _one(conn, "SELECT * FROM time_entries WHERE id = ?", (entry_id,))
    conn.close()
    return row


def get_open_entries_with_names():
    conn = get_conn()
    rows = _all(
        conn,
        """SELECT time_entries.*, employees.full_name
           FROM time_entries JOIN employees ON employees.id = time_entries.employee_id
           WHERE time_entries.clock_out IS NULL
           ORDER BY time_entries.clock_in""",
    )
    conn.close()
    return rows


def get_entries_between(start_iso: str, end_iso: str):
    conn = get_conn()
    rows = _all(
        conn,
        """SELECT time_entries.*, employees.full_name
           FROM time_entries JOIN employees ON employees.id = time_entries.employee_id
           WHERE time_entries.clock_in >= ? AND time_entries.clock_in < ?
           ORDER BY employees.full_name, time_entries.clock_in""",
        (start_iso, end_iso),
    )
    conn.close()
    return rows


def get_entry(entry_id: int):
    conn = get_conn()
    row = _one(
        conn,
        """SELECT time_entries.*, employees.full_name
           FROM time_entries JOIN employees ON employees.id = time_entries.employee_id
           WHERE time_entries.id = ?""",
        (entry_id,),
    )
    conn.close()
    return row


def update_entry(entry_id: int, clock_in_iso: str, clock_out_iso: str | None, is_overtime: bool) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE time_entries SET clock_in = ?, clock_out = ?, is_overtime = ? WHERE id = ?",
        (clock_in_iso, clock_out_iso, 1 if is_overtime else 0, entry_id),
    )
    conn.commit()
    conn.close()


def delete_entry(entry_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


# ── Settings ─────────────────────────────────────────────────────────

def get_settings() -> dict:
    conn = get_conn()
    row = _one(conn, "SELECT * FROM settings WHERE id = 1")
    conn.close()
    return row


def update_settings(hourly_rate: float, overtime_hourly_rate: float, business_name: str) -> None:
    conn = get_conn()
    conn.execute(
        """UPDATE settings SET hourly_rate = ?, overtime_hourly_rate = ?, business_name = ?, updated_at = ?
           WHERE id = 1""",
        (hourly_rate, overtime_hourly_rate, business_name, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ── Admin users ──────────────────────────────────────────────────────

def get_admin_by_username(username: str):
    conn = get_conn()
    row = _one(conn, "SELECT * FROM admin_users WHERE username = ?", (username,))
    conn.close()
    return row


def get_admin_users():
    conn = get_conn()
    rows = _all(conn, "SELECT id, username, created_at FROM admin_users ORDER BY id")
    conn.close()
    return rows


def create_admin_user(username: str, password_hash: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_admin_user(admin_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
    conn.commit()
    conn.close()


def count_admin_users() -> int:
    conn = get_conn()
    n = _one(conn, "SELECT COUNT(*) AS n FROM admin_users")["n"]
    conn.close()
    return n
