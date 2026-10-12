"""Rutas de administracion: empleados, correcciones de marcaje, nomina
semanal y configuracion. Separado de main.py para no inflar un solo
archivo (login/logout de admin se quedan en main.py porque son
infraestructura de sesion, no gestion de negocio).
"""
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

import auth
import db
import export
import payroll
import production

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def _require_admin(request: Request):
    if not auth.is_admin(request):
        return RedirectResponse("/admin/login")
    return None


def _initials(full_name: str) -> str:
    """JQ para 'Juan Quiros', MS para 'Maria Solano'. Con un solo nombre
    usa las primeras dos letras -- nunca revienta con nombres raros."""
    parts = full_name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return full_name[:2].upper() if full_name else "??"


# ─────────────────────────── Dashboard ─────────────────────────────

@router.get("/dashboard")
def dashboard(request: Request):
    if (redirect := _require_admin(request)):
        return redirect

    settings = db.get_settings()
    today_monday, _ = payroll.week_bounds(date.today())
    start_iso, end_iso = payroll.week_range_iso(today_monday)
    entries = db.get_entries_between(start_iso, end_iso)
    summary = payroll.build_payroll_summary(entries, settings)

    open_entries = db.get_open_entries_with_names()
    for e in open_entries:
        hours = payroll.worked_hours(e["clock_in"], None)
        h, m = payroll.hours_and_minutes(hours)
        e["elapsed"] = f"{h}h {m}min"
        e["clock_in_time"] = datetime.fromisoformat(e["clock_in"]).strftime("%H:%M")

    today_str = date.today().isoformat()
    products = db.get_products(include_inactive=False)
    packing_entries = db.get_packing_entries_for_date(today_str)
    production_summary = production.build_daily_summary(packing_entries, products)

    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "business_name": settings["business_name"],
        "open_entries": open_entries,
        "week_label": f"{payroll.format_fecha_corta(today_monday)} - {payroll.format_fecha_corta(payroll.week_bounds(date.today())[1])}",
        "summary": summary,
        "production_summary": production_summary,
        "currency_symbol": settings["currency_symbol"],
        "format_crc": lambda amt: payroll.format_crc(amt, settings["currency_symbol"]),
        "employee_count": len(db.get_employees(include_inactive=False)),
    })


# ─────────────────────────── Empleados ─────────────────────────────

@router.get("/employees")
def employees_page(request: Request, new_pin: str | None = None, error: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings = db.get_settings()
    return templates.TemplateResponse(request, "admin_employees.html", {
        "business_name": settings["business_name"],
        "employees": db.get_employees(),
        "new_pin": new_pin,
        "error": error,
        "default_hourly_rate": settings["hourly_rate"],
        "format_crc": lambda amt: payroll.format_crc(amt, settings["currency_symbol"]),
    })


@router.post("/employees")
def create_employee(request: Request, full_name: str = Form(...), hourly_rate: str = Form(""), pin_code: str = Form("")):
    if (redirect := _require_admin(request)):
        return redirect
    full_name = full_name.strip()
    if not full_name:
        return RedirectResponse("/admin/employees", status_code=303)
    rate = float(hourly_rate) if hourly_rate.strip() else None
    pin_code = pin_code.strip()
    if pin_code and not (pin_code.isdigit() and len(pin_code) == 4):
        return RedirectResponse(f"/admin/employees?error={quote('El PIN debe ser de exactamente 4 digitos numericos.')}", status_code=303)
    try:
        employee = db.create_employee(full_name, pin_code=pin_code or None, hourly_rate=rate)
    except ValueError as e:
        return RedirectResponse(f"/admin/employees?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/admin/employees?new_pin={employee['pin_code']}", status_code=303)


@router.post("/employees/{employee_id}")
def edit_employee(request: Request, employee_id: int, full_name: str = Form(...), active: str = Form(""), hourly_rate: str = Form("")):
    if (redirect := _require_admin(request)):
        return redirect
    rate = float(hourly_rate) if hourly_rate.strip() else None
    db.update_employee(employee_id, full_name.strip(), active == "on", hourly_rate=rate)
    return RedirectResponse("/admin/employees", status_code=303)


@router.post("/employees/{employee_id}/delete")
def delete_employee(request: Request, employee_id: int):
    if (redirect := _require_admin(request)):
        return redirect
    try:
        db.delete_employee(employee_id)
    except ValueError as e:
        return RedirectResponse(f"/admin/employees?error={quote(str(e))}", status_code=303)
    return RedirectResponse("/admin/employees", status_code=303)


@router.post("/employees/{employee_id}/reset-pin")
def reset_pin(request: Request, employee_id: int):
    if (redirect := _require_admin(request)):
        return redirect
    new_pin = db.reset_employee_pin(employee_id)
    return RedirectResponse(f"/admin/employees?new_pin={new_pin}", status_code=303)


# ─────────────────────────── Correcciones de marcaje ────────────────

@router.get("/entries")
def entries_page(request: Request, week: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings = db.get_settings()
    anchor = datetime.strptime(week, "%Y-%m-%d").date() if week else date.today()
    monday, sunday = payroll.week_bounds(anchor)
    start_iso, end_iso = payroll.week_range_iso(monday)
    entries = db.get_entries_between(start_iso, end_iso)

    for e in entries:
        hours = payroll.worked_hours(e["clock_in"], e["clock_out"])
        h, m = payroll.hours_and_minutes(hours)
        e["duration"] = f"{h}h {m}min" if e["clock_out"] else "En curso"
        e["clock_in_local"] = datetime.fromisoformat(e["clock_in"]).strftime("%Y-%m-%dT%H:%M")
        e["clock_out_local"] = datetime.fromisoformat(e["clock_out"]).strftime("%Y-%m-%dT%H:%M") if e["clock_out"] else ""

    return templates.TemplateResponse(request, "admin_entries.html", {
        "business_name": settings["business_name"],
        "entries": entries,
        "monday": monday,
        "prev_week_str": _shift_week(monday, -7),
        "next_week_str": _shift_week(monday, 7),
        "week_label": f"{payroll.format_fecha_corta(monday)} - {payroll.format_fecha_corta(sunday)}",
        "is_current_week": monday == payroll.week_bounds(date.today())[0],
    })


@router.post("/entries/{entry_id}")
def edit_entry(
    request: Request,
    entry_id: int,
    clock_in: str = Form(...),
    clock_out: str = Form(""),
    is_overtime: str = Form(""),
    week: str = Form(""),
):
    if (redirect := _require_admin(request)):
        return redirect
    clock_in_iso = datetime.strptime(clock_in, "%Y-%m-%dT%H:%M").isoformat()
    clock_out_iso = datetime.strptime(clock_out, "%Y-%m-%dT%H:%M").isoformat() if clock_out else None
    db.update_entry(entry_id, clock_in_iso, clock_out_iso, is_overtime == "on")
    suffix = f"?week={week}" if week else ""
    return RedirectResponse(f"/admin/entries{suffix}", status_code=303)


@router.post("/entries/{entry_id}/delete")
def delete_entry(request: Request, entry_id: int, week: str = Form("")):
    if (redirect := _require_admin(request)):
        return redirect
    db.delete_entry(entry_id)
    suffix = f"?week={week}" if week else ""
    return RedirectResponse(f"/admin/entries{suffix}", status_code=303)


# ─────────────────────────── Nomina semanal ─────────────────────────

def _week_summary(week: str | None):
    settings = db.get_settings()
    anchor = datetime.strptime(week, "%Y-%m-%d").date() if week else date.today()
    monday, sunday = payroll.week_bounds(anchor)
    start_iso, end_iso = payroll.week_range_iso(monday)
    entries = db.get_entries_between(start_iso, end_iso)
    summary = payroll.build_payroll_summary(entries, settings, monday)
    return settings, monday, sunday, summary


@router.get("/payroll")
def payroll_page(request: Request, week: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings, monday, sunday, summary = _week_summary(week)
    return templates.TemplateResponse(request, "admin_payroll.html", {
        "business_name": settings["business_name"],
        "summary": summary,
        "currency_symbol": settings["currency_symbol"],
        "format_crc": lambda amt: payroll.format_crc(amt, settings["currency_symbol"]),
        "monday": monday,
        "prev_week_str": _shift_week(monday, -7),
        "next_week_str": _shift_week(monday, 7),
        "week_label": f"{payroll.format_fecha_corta(monday)} - {payroll.format_fecha_corta(sunday)}",
        "initials": _initials,
    })


def _shift_week(monday: date, days: int) -> str:
    from datetime import timedelta
    return (monday + timedelta(days=days)).isoformat()


@router.get("/payroll/export.xlsx")
def export_xlsx(request: Request, week: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings, monday, sunday, summary = _week_summary(week)
    week_label = f"{payroll.format_fecha_corta(monday)} al {payroll.format_fecha_corta(sunday)}"
    content = export.build_excel(summary, settings["business_name"], week_label, settings["currency_symbol"])
    filename = f"nomina_{monday.isoformat()}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/payroll/export.pdf")
def export_pdf(request: Request, week: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings, monday, sunday, summary = _week_summary(week)
    week_label = f"{payroll.format_fecha_corta(monday)} al {payroll.format_fecha_corta(sunday)}"
    content = export.build_pdf(summary, settings["business_name"], week_label, settings["currency_symbol"])
    filename = f"nomina_{monday.isoformat()}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────── Configuracion ──────────────────────────

@router.get("/settings")
def settings_page(request: Request, saved: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings = db.get_settings()
    return templates.TemplateResponse(request, "admin_settings.html", {
        "business_name": settings["business_name"],
        "settings": settings,
        "admins": db.get_admin_users(),
        "saved": saved,
        "current_username": request.session.get("admin_username"),
    })


@router.post("/settings")
def update_settings(
    request: Request,
    business_name: str = Form(...),
    hourly_rate: float = Form(...),
    overtime_hourly_rate: float = Form(...),
):
    if (redirect := _require_admin(request)):
        return redirect
    db.update_settings(hourly_rate, overtime_hourly_rate, business_name.strip())
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@router.post("/settings/admins")
def add_admin(request: Request, username: str = Form(...), password: str = Form(...)):
    if (redirect := _require_admin(request)):
        return redirect
    username = username.strip()
    if username and len(password) >= 6 and not db.get_admin_by_username(username):
        db.create_admin_user(username, auth.hash_password(password))
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/admins/{admin_id}/delete")
def remove_admin(request: Request, admin_id: int):
    if (redirect := _require_admin(request)):
        return redirect
    if db.count_admin_users() > 1:
        db.delete_admin_user(admin_id)
    return RedirectResponse("/admin/settings", status_code=303)


# ───────────────── Catalogo de productos ───────────────────

@router.get("/products")
def products_page(request: Request):
    if (redirect := _require_admin(request)):
        return redirect
    settings = db.get_settings()
    return templates.TemplateResponse(request, "admin_products.html", {
        "business_name": settings["business_name"],
        "products": db.get_products(),
    })


@router.post("/products")
def create_product(request: Request, name: str = Form(...), daily_target_boxes: str = Form(""), description: str = Form(""), unit_label: str = Form("")):
    if (redirect := _require_admin(request)):
        return redirect
    name = name.strip()
    target = float(daily_target_boxes) if daily_target_boxes.strip() else None
    if name:
        db.create_product(name, target, description.strip() or None, unit_label.strip() or None)
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}")
def edit_product(
    request: Request,
    product_id: int,
    name: str = Form(...),
    daily_target_boxes: str = Form(""),
    active: str = Form(""),
    description: str = Form(""),
    unit_label: str = Form(""),
):
    if (redirect := _require_admin(request)):
        return redirect
    target = float(daily_target_boxes) if daily_target_boxes.strip() else None
    db.update_product(product_id, name.strip(), target, active == "on", description.strip() or None, unit_label.strip() or None)
    return RedirectResponse("/admin/products", status_code=303)


# ─────────────── Produccion empacada por dia ─────────────────

@router.get("/production")
def production_page(request: Request, day: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings = db.get_settings()
    selected_day = datetime.strptime(day, "%Y-%m-%d").date() if day else date.today()
    products = db.get_products(include_inactive=False)
    entries = db.get_packing_entries_for_date(selected_day.isoformat())
    summary = production.build_daily_summary(entries, products)

    return templates.TemplateResponse(request, "admin_production.html", {
        "business_name": settings["business_name"],
        "products": products,
        "entries": entries,
        "summary": summary,
        "selected_day": selected_day,
        "day_label": payroll.format_fecha_larga(selected_day),
        "prev_day_str": production.shift_date(selected_day, -1),
        "next_day_str": production.shift_date(selected_day, 1),
        "is_today": selected_day == date.today(),
    })


@router.post("/production")
def log_production(
    request: Request,
    product_id: int = Form(...),
    entry_date: str = Form(...),
    boxes: float = Form(...),
    kg: float = Form(...),
    notes: str = Form(""),
):
    if (redirect := _require_admin(request)):
        return redirect
    created_by = request.session.get("admin_username", "admin")
    db.create_packing_entry(product_id, entry_date, boxes, kg, notes.strip(), created_by)
    return RedirectResponse(f"/admin/production?day={entry_date}", status_code=303)


@router.post("/production/{entry_id}/delete")
def delete_production_entry(request: Request, entry_id: int, day: str = Form("")):
    if (redirect := _require_admin(request)):
        return redirect
    db.delete_packing_entry(entry_id)
    suffix = f"?day={day}" if day else ""
    return RedirectResponse(f"/admin/production{suffix}", status_code=303)
