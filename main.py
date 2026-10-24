



"""Empacadora San Juan -- checador de entrada/salida + nomina semanal.

Kiosko publico: cualquiera con un PIN valido marca su entrada/salida
desde una tablet en planta. Panel de admin (login compartido, extensible
a mas usuarios): empleados, correcciones, nomina y configuracion.
"""
import logging
import os
import secrets as pysecrets

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import admin_routes
import auth
import db
import payroll
import security

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("empacadora")

app = FastAPI(title="Empacadora San Juan")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="assets/photos"), name="assets")

SESSION_SECRET = os.environ.get("SESSION_SECRET")
if not SESSION_SECRET:
    SESSION_SECRET = pysecrets.token_hex(32)
    log.warning(
        "SESSION_SECRET no configurado -- usando uno temporal. Configuralo "
        "en el hosting real (ver DEPLOY.md) o las sesiones de admin se "
        "invalidan cada vez que el servicio reinicia."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.environ.get("FLY_APP_NAME", "") != "" and os.environ.get("LOCAL_DEV", "") == "",
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    default_user = os.environ.get("ADMIN_USERNAME", "admin")
    default_pass = os.environ.get("ADMIN_PASSWORD")
    if not default_pass:
        default_pass = "cambiame123"
        log.warning(
            "ADMIN_PASSWORD no configurado -- el admin inicial quedo con la "
            "contraseña temporal 'cambiame123'. CAMBIALA desde /admin en "
            "cuanto entres, o define ADMIN_PASSWORD en el hosting real."
        )
    db.seed_default_admin(default_user, auth.hash_password(default_pass))


app.include_router(admin_routes.router)


# ─────────────────────────── Landing publica ───────────────────────────

def _landing_whatsapp() -> str:
    """Numero de WhatsApp de la landing, o "" si falta o esta incompleto.

    Formato internacional sin "+": codigo de pais + numero (10 a 15 digitos).
    Asi un valor de ejemplo como 506XXXXXXXX no termina en un boton roto.
    """
    digits = "".join(ch for ch in os.environ.get("LANDING_WHATSAPP", "") if ch.isdigit())
    return digits if 10 <= len(digits) <= 15 else ""


def _site_url(request: Request) -> str:
    """URL base absoluta (para og:image). Detras de Fly el trafico llega por
    HTTP interno, pero hacia afuera siempre se sirve por HTTPS."""
    scheme = "https" if os.environ.get("FLY_APP_NAME") else request.url.scheme
    return f"{scheme}://{request.url.netloc}"


@app.get("/")
def landing(request: Request):
    settings = db.get_settings()
    # Contacto opcional (variables de entorno): sin ellas, el boton no se muestra.
    return templates.TemplateResponse(request, "landing.html", {
        "business_name": settings["business_name"],
        "whatsapp": _landing_whatsapp(),
        "email": os.environ.get("LANDING_EMAIL", "").strip(),
        "site_url": _site_url(request),
    })


@app.get("/landing")
def landing_old_url():
    # La landing vivia aqui antes de pasar a la raiz; no romper enlaces viejos.
    return RedirectResponse("/", status_code=301)


# ─────────────────────────── Kiosko publico ───────────────────────────

@app.get("/kiosko")
def kiosk(request: Request):
    settings = db.get_settings()
    return templates.TemplateResponse(request, "kiosk.html", {
        "business_name": settings["business_name"],
    })


@app.post("/clock")
def clock(request: Request, pin: str = Form(...)):
    ip = security.client_ip(request)
    if security.is_rate_limited(f"clock:{ip}", max_hits=15, window_seconds=60):
        return templates.TemplateResponse(request, "_clock_result.html", {
            "ok": False,
            "message": "Demasiados intentos seguidos. Espera un momento e intenta de nuevo.",
        })

    pin = pin.strip()
    if not (pin.isdigit() and len(pin) == 4):
        return templates.TemplateResponse(request, "_clock_result.html", {
            "ok": False,
            "message": "El PIN debe tener 4 digitos.",
        })

    employee = db.get_employee_by_pin(pin)
    if not employee:
        return templates.TemplateResponse(request, "_clock_result.html", {
            "ok": False,
            "message": "PIN incorrecto. Intenta de nuevo o pide ayuda al encargado.",
        })

    open_entry = db.get_open_entry(employee["id"])
    if open_entry:
        entry = db.clock_out(open_entry["id"])
        hours = payroll.worked_hours(entry["clock_in"], entry["clock_out"])
        h, m = payroll.hours_and_minutes(hours)
        return templates.TemplateResponse(request, "_clock_result.html", {
            "ok": True,
            "action": "salida",
            "employee_name": employee["full_name"],
            "message": f"Hasta luego, {employee['full_name']}! Salida registrada. Trabajaste {h}h {m}min hoy en este turno.",
        })

    db.clock_in(employee["id"])
    return templates.TemplateResponse(request, "_clock_result.html", {
        "ok": True,
        "action": "entrada",
        "employee_name": employee["full_name"],
        "message": f"Bienvenido/a, {employee['full_name']}! Entrada registrada.",
    })


# ─────────────────────── Login / logout de admin ───────────────────────

@app.get("/admin")
def admin_root(request: Request):
    if auth.is_admin(request):
        return RedirectResponse("/admin/dashboard")
    return RedirectResponse("/admin/login")


@app.get("/admin/login")
def admin_login_page(request: Request):
    if auth.is_admin(request):
        return RedirectResponse("/admin/dashboard")
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@app.post("/admin/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    ip = security.client_ip(request)
    if security.is_locked_out(ip):
        return templates.TemplateResponse(request, "admin_login.html", {
            "error": "Demasiados intentos fallidos. Espera 15 minutos e intenta de nuevo.",
        })

    admin_user = db.get_admin_by_username(username.strip())
    if admin_user and auth.verify_password(password, admin_user["password_hash"]):
        security.clear_failed_logins(ip)
        request.session["admin_ok"] = True
        request.session["admin_username"] = admin_user["username"]
        return RedirectResponse("/admin/dashboard", status_code=303)

    security.register_failed_login(ip)
    return templates.TemplateResponse(request, "admin_login.html", {"error": "Usuario o contraseña incorrectos."})


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login")
