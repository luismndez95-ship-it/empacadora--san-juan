# Desplegar Empacadora San Juan en Fly.io

Elegimos Fly.io (y no Render) porque su free tier permite dejar la app
**siempre despierta** (`min_machines_running = 1`) -- nada de esperar
a que "despierte" mientras alguien esta parado en planta marcando
tarjeta. Ademas soporta un volumen persistente real, asi que la base
de datos SQLite sobrevive redeploys y reinicios.

## 1. Instalar flyctl

Windows (PowerShell):
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

Si `winget`/`iwr` fallan por proxy corporativo, usa las variables de
`HTTP_PROXY`/`HTTPS_PROXY` de sysproxy.wal-mart.com (ver notas internas),
o instala flyctl desde tu red personal (este proyecto es 100% ajeno a
Walmart, no hace falta VPN para el hosting en si).

## 2. Login y crear la app

```bat
flyctl auth login
cd empacadora-san-juan
flyctl launch --no-deploy
```

Cuando pregunte, di que **no** a Postgres/Redis (no los usamos) y
confirma el nombre de la app (`empacadora-san-juan` o el que seleccione
como disponible).

## 3. Crear el volumen persistente

```bat
flyctl volumes create empacadora_data --region mia --size 1
```

(El nombre debe coincidir con `source = "empacadora_data"` en `fly.toml`.)

## 4. Configurar secretos (nunca en el codigo)

```bat
flyctl secrets set SESSION_SECRET=el-valor-que-genere-python
flyctl secrets set ADMIN_USERNAME=admin
flyctl secrets set ADMIN_PASSWORD=una-contrasena-real-y-fuerte
```

Genera `SESSION_SECRET` con:
```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

## 5. Deploy

```bat
flyctl deploy
```

## 6. Verificar

```bat
flyctl status
flyctl logs
```

Abre la URL que te da Fly (`https://empacadora-san-juan.fly.dev`) --
el kiosko debe cargar de inmediato, sin espera de "cold start".

## Actualizaciones futuras

Cualquier cambio de codigo: `flyctl deploy` de nuevo desde la carpeta
del proyecto. La base de datos en el volumen `/data` no se toca -- los
empleados, marcajes y configuracion se mantienen entre despliegues.

## Backups

La base de datos vive sola en el volumen de Fly. Recomendado bajar una
copia de vez en cuando (ej. cada mes) por si acaso:

```bat
flyctl ssh sftp get /data/empacadora.db ./backup_empacadora.db
```
