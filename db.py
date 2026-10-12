
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
            hourly_rate REAL,
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
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            daily_target_boxes REAL,
            unit_price REAL,
            description TEXT,
            unit_label TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS packing_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            entry_date TEXT NOT NULL,
            boxes REAL NOT NULL,
            kg REAL NOT NULL,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    # Migracion ligera: bases creadas antes de la tarifa por empleado
    # no tienen esta columna. SQLite no soporta "ADD COLUMN IF NOT EXISTS",
    # por eso revisamos PRAGMA table_info primero.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(employees)").fetchall()}
    if "hourly_rate" not in existing_cols:
        conn.execute("ALTER TABLE employees ADD COLUMN hourly_rate REAL")
        conn.commit()

    product_cols = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "description" not in product_cols:
        conn.execute("ALTER TABLE products ADD COLUMN description TEXT")
        conn.commit()
    if "unit_label" not in product_cols:
        conn.execute("ALTER TABLE products ADD COLUMN unit_label TEXT")
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


def create_employee(full_name: str, pin_code: str | None = None, hourly_rate: float | None = None) -> dict:
    """Crea un empleado. Si `pin_code` viene vacio, se genera uno unico al
    azar (comportamiento original). Si el admin da un PIN manual y ya esta
    en uso por otro empleado, se levanta ValueError con mensaje claro en
    vez de dejar reventar el IntegrityError crudo de SQLite."""
    conn = get_conn()
    pin = pin_code or gen_unique_pin(conn)
    if pin_code and _one(conn, "SELECT id FROM employees WHERE pin_code = ?", (pin,)):
        conn.close()
        raise ValueError(f"El PIN {pin} ya esta asignado a otro empleado. Elige uno diferente.")
    conn.execute(
        "INSERT INTO employees (full_name, pin_code, active, hourly_rate, created_at) VALUES (?, ?, 1, ?, ?)",
        (full_name, pin, hourly_rate, datetime.now().isoformat()),
    )
    conn.commit()
    row = _one(conn, "SELECT * FROM employees WHERE pin_code = ?", (pin,))
    conn.close()
    return row


def update_employee(employee_id: int, full_name: str, active: bool, hourly_rate: float | None = None) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE employees SET full_name = ?, active = ?, hourly_rate = ? WHERE id = ?",
        (full_name, 1 if active else 0, hourly_rate, employee_id),
    )
    conn.commit()
    conn.close()


def delete_employee(employee_id: int) -> None:
    """Borra un empleado por completo -- SOLO si nunca ha marcado entrada.
    Si ya tiene time_entries reales (historial de nomina), se rechaza con
    ValueError: perder esos registros seria un problema legal/contable,
    no un simple detalle de UI. Para ese caso el admin debe desactivarlo
    (checkbox Activo) en vez de borrarlo -- conserva el historial pero
    lo saca de la lista de gente que puede marcar."""
    conn = get_conn()
    count = _one(conn, "SELECT COUNT(*) as n FROM time_entries WHERE employee_id = ?", (employee_id,))["n"]
    if count > 0:
        conn.close()
        raise ValueError(
            f"No se puede eliminar: tiene {count} marcaje(s) registrado(s) (historial de nomina). "
            "Desactivalo con el checkbox 'Activo' en su lugar."
        )
    conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
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
        """SELECT time_entries.*, employees.full_name, employees.hourly_rate AS employee_hourly_rate
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


# ── Products (catalogo de lo que se empaca) ───────────────────────────

def get_products(include_inactive: bool = True):
    conn = get_conn()
    sql = "SELECT * FROM products"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY name"
    rows = _all(conn, sql)
    conn.close()
    return rows


def get_product(product_id: int):
    conn = get_conn()
    row = _one(conn, "SELECT * FROM products WHERE id = ?", (product_id,))
    conn.close()
    return row


def create_product(name: str, daily_target_boxes: float | None, description: str | None = None, unit_label: str | None = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO products (name, daily_target_boxes, description, unit_label, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (name, daily_target_boxes, description, unit_label, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def update_product(product_id: int, name: str, daily_target_boxes: float | None, active: bool, description: str | None = None, unit_label: str | None = None) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE products SET name = ?, daily_target_boxes = ?, description = ?, unit_label = ?, active = ? WHERE id = ?",
        (name, daily_target_boxes, description, unit_label, 1 if active else 0, product_id),
    )
    conn.commit()
    conn.close()


# ── Packing entries (lo que realmente se empaco cada dia) ─────────────

def create_packing_entry(product_id: int, entry_date: str, boxes: float, kg: float, notes: str, created_by: str) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO packing_entries (product_id, entry_date, boxes, kg, notes, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (product_id, entry_date, boxes, kg, notes or None, created_by, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_packing_entries_for_date(entry_date: str):
    conn = get_conn()
    rows = _all(
        conn,
        """SELECT packing_entries.*, products.name AS product_name, products.daily_target_boxes, products.description, products.unit_label
           FROM packing_entries JOIN products ON products.id = packing_entries.product_id
           WHERE packing_entries.entry_date = ?
           ORDER BY products.name, packing_entries.created_at""",
        (entry_date,),
    )
    conn.close()
    return rows


def delete_packing_entry(entry_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM packing_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
