# Empacadora San Juan -- Checador y Nomina

App interna para **Empacadora San Juan** (San Juan de Chicua, Cartago,
Costa Rica -- empaque de coliflor y brocoli). Reemplaza el control de
entrada/salida manual con un kiosko de PIN y calcula automaticamente
cuanto pagar cada semana, sin redondeos a favor de nadie.

Construido por **Veltyk** como proyecto cliente.

## Que hace

- **Kiosko publico (`/`)**: cada trabajador teclea su PIN de 4 digitos
  en una tablet/pantalla en planta para marcar entrada o salida.
- **Panel admin (`/admin`)**: login compartido (usuario + contraseña,
  extensible a mas administradores desde Configuracion).
  - **Empleados**: crear, activar/desactivar, reasignar PIN.
  - **Marcajes**: corregir entradas/salidas mal marcadas, marcar horas
    como "hora extra" (tarifa distinta, configurable).
  - **Nomina**: resumen semanal por empleado (horas + pago exacto),
    navegable semana a semana, exportable a Excel y PDF.
  - **Configuracion**: tarifa regular y de hora extra (colones), nombre
    del negocio, gestion de administradores.

## Como se calcula el pago

Pago = horas reales trabajadas (al minuto exacto, sin redondear a favor
de nadie) x tarifa por hora. Si alguien entra tarde, se le paga desde
que realmente marco entrada -- no desde la hora programada. Ver
`payroll.py`.

## Correr en local

```bat
uv venv
uv pip install -r requirements.txt
copy .env.example .env
REM edita .env con una contraseña real de admin
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Abre `http://127.0.0.1:8000` para el kiosko, `http://127.0.0.1:8000/admin`
para el panel (usuario/contraseña de `.env`).

## Estructura

| Archivo | Que hace |
|---|---|
| `main.py` | App FastAPI, kiosko publico, login/logout de admin |
| `admin_routes.py` | Rutas del panel: empleados, marcajes, nomina, configuracion |
| `db.py` | SQLite, sin ORM (dicts planos) |
| `payroll.py` | Calculo de horas/pago, formato de colones, semanas |
| `export.py` | Generacion de Excel (openpyxl) y PDF (reportlab) |
| `auth.py` | Hash de contraseñas (PBKDF2, sin dependencias nativas) + sesion admin |
| `security.py` | Rate limiting simple en memoria |

## Despliegue

Ver `DEPLOY.md` -- usamos Fly.io (no Render) especificamente porque no
duerme la app: si alguien llega a marcar tarjeta y el servicio estuviera
dormido, tendria que esperar. Fly.io con `min_machines_running = 1` se
queda siempre despierto, gratis dentro de su free tier para una app
tan chica como esta.
