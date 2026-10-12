"""Logica de negocio de nomina: horas exactas, pago sin redondeos a favor
del trabajador, formato de colones costarricenses, y limites de semana.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def worked_hours(clock_in_iso: str, clock_out_iso: str | None) -> float:
    """Horas trabajadas como decimal exacto. Si aun no ha marcado salida,
    calcula contra el momento actual (para mostrar 'llevas X horas' en
    vivo), pero eso NUNCA se usa para pagar -- solo para display."""
    start = parse_iso(clock_in_iso)
    end = parse_iso(clock_out_iso) if clock_out_iso else datetime.now()
    seconds = max((end - start).total_seconds(), 0)
    return seconds / 3600.0


def hours_and_minutes(hours: float) -> tuple[int, int]:
    total_minutes = round(hours * 60)
    return total_minutes // 60, total_minutes % 60


def compute_pay(hours: float, hourly_rate: float, overtime_rate: float, is_overtime: bool) -> float:
    """Pago exacto: horas reales (sin redondear a favor de nadie) por la
    tarifa que aplique. Si el admin marco la entrada como hora extra,
    usa la tarifa de hora extra configurada en Settings; si no, la
    tarifa regular (propia del empleado, o la global si no tiene una
    asignada). Sin umbral automatico -- el admin decide caso por caso."""
    rate = overtime_rate if is_overtime else hourly_rate
    return round(hours * rate, 2)


def format_crc(amount: float, symbol: str = "₡") -> str:
    """Formato costarricense: punto de millar, coma decimal.
    Ej. 12345.5 -> '₡12.345,50'"""
    amount = round(amount, 2)
    negative = amount < 0
    amount = abs(amount)
    integer_part = int(amount)
    cents = round((amount - integer_part) * 100)
    if cents == 100:
        integer_part += 1
        cents = 0
    int_str = f"{integer_part:,}".replace(",", ".")
    sign = "-" if negative else ""
    return f"{sign}{symbol}{int_str},{cents:02d}"


def week_bounds(anchor: date) -> tuple[date, date]:
    """Lunes a domingo de la semana que contiene `anchor`."""
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def week_range_iso(monday: date) -> tuple[str, str]:
    """Limites [inicio, fin) en ISO para filtrar clock_in con >= / <."""
    start = datetime.combine(monday, datetime.min.time())
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


DIAS_ES = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
DIA_CORTO_ES = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def format_fecha_corta(d: date) -> str:
    return f"{d.day} {MESES_ES[d.month - 1][:3]}"


def format_fecha_larga(d: date) -> str:
    return f"{DIAS_ES[d.weekday()]} {d.day} de {MESES_ES[d.month - 1]}"


def build_payroll_summary(entries: list[dict], settings: dict, monday: date | None = None) -> dict:
    """Agrupa entradas de la semana por empleado y calcula totales.

    `entries` viene de db.get_entries_between (incluye full_name y
    employee_hourly_rate). Si el empleado no tiene tarifa propia
    (employee_hourly_rate es None), se usa la tarifa global de Settings
    -- asi la app sigue funcionando igual para quien no la configure.

    Si se pasa `monday`, cada fila incluye ademas `days`: el desglose
    de horas/pago dia por dia (Lunes a Domingo) para la tarjeta de
    nomina estilo "historial semanal" en admin_payroll.html.
    """
    by_employee: dict[str, dict] = {}
    for e in entries:
        name = e["full_name"]
        employee_rate = e.get("employee_hourly_rate")
        effective_rate = employee_rate if employee_rate is not None else settings["hourly_rate"]
        row = by_employee.setdefault(name, {
            "full_name": name,
            "hourly_rate": effective_rate,
            "regular_hours": 0.0,
            "overtime_hours": 0.0,
            "regular_pay": 0.0,
            "overtime_pay": 0.0,
            "open_entry": False,
            "entry_count": 0,
            "_by_date": {},
        })
        hours = worked_hours(e["clock_in"], e["clock_out"])
        pay = compute_pay(hours, effective_rate, settings["overtime_hourly_rate"], bool(e["is_overtime"]))
        row["entry_count"] += 1
        if e["clock_out"] is None:
            row["open_entry"] = True
        if e["is_overtime"]:
            row["overtime_hours"] += hours
            row["overtime_pay"] += pay
        else:
            row["regular_hours"] += hours
            row["regular_pay"] += pay
        entry_date = parse_iso(e["clock_in"]).date()
        bucket = row["_by_date"].setdefault(entry_date, {"hours": 0.0, "pay": 0.0})
        bucket["hours"] += hours
        bucket["pay"] += pay

    rows = sorted(by_employee.values(), key=lambda r: r["full_name"])
    today = date.today()
    for row in rows:
        row["total_hours"] = row["regular_hours"] + row["overtime_hours"]
        row["total_pay"] = row["regular_pay"] + row["overtime_pay"]
        if monday is not None:
            days = []
            for i in range(7):
                d = monday + timedelta(days=i)
                bucket = row["_by_date"].get(d, {"hours": 0.0, "pay": 0.0})
                days.append({
                    "date": d,
                    "label": f"{DIA_CORTO_ES[i]} {d.day}",
                    "hours": bucket["hours"],
                    "pay": bucket["pay"],
                    "is_today": d == today,
                    "has_hours": bucket["hours"] > 0,
                })
            row["days"] = days
        del row["_by_date"]

    grand_total_hours = sum(r["total_hours"] for r in rows)
    grand_total_pay = sum(r["total_pay"] for r in rows)
    return {"rows": rows, "grand_total_hours": grand_total_hours, "grand_total_pay": grand_total_pay}
