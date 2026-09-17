"""Rutas de administracion: empleados, correcciones de marcaje, nomina
semanal y configuracion. Separado de main.py para no inflar un solo
archivo (login/logout de admin se quedan en main.py porque son
infraestructura de sesion, no gestion de negocio).
"""
from datetime import date, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

import auth
import db
import export
import payroll

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def _require_admin(request: Request):
    if not auth.is_admin(request):
        return RedirectResponse("/admin/login")
    return None


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

    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "business_name": settings["business_name"],
        "open_entries": open_entries,
        "week_label": f"{payroll.format_fecha_corta(today_monday)} - {payroll.format_fecha_corta(payroll.week_bounds(date.today())[1])}",
        "summary": summary,
        "currency_symbol": settings["currency_symbol"],
        "format_crc": lambda amt: payroll.format_crc(amt, settings["currency_symbol"]),
        "employee_count": len(db.get_employees(include_inactive=False)),
    })


# ─────────────────────────── Empleados ─────────────────────────────

@router.get("/employees")
def employees_page(request: Request, new_pin: str | None = None):
    if (redirect := _require_admin(request)):
        return redirect
    settings = db.get_settings()
    return templates.TemplateResponse(request, "admin_employees.html", {
        "business_name": settings["business_name"],
        "employees": db.get_employees(),
        "new_pin": new_pin,
    })


@router.post("/employees")
def create_employee(request: Request, full_name: str = Form(...)):
    if (redirect := _require_admin(request)):
        return redirect
    full_name = full_name.strip()
    if not full_name:
        return RedirectResponse("/admin/employees", status_code=303)
    employee = db.create_employee(full_name)
    return RedirectResponse(f"/admin/employees?new_pin={employee['pin_code']}", status_code=303)


@router.post("/employees/{employee_id}")
def edit_employee(request: Request, employee_id: int, full_name: str = Form(...), active: str = Form("")):
    if (redirect := _require_admin(request)):
        return redirect
    db.update_employee(employee_id, full_name.strip(), active == "on")
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
    summary = payroll.build_payroll_summary(entries, settings)
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
