FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# La base de datos vive en el volumen persistente de Fly (ver fly.toml),
# no en el filesystem efimero del contenedor -- asi sobrevive redeploys.
ENV DB_PATH=/data/empacadora.db

EXPOSE 8080
# --no-proxy-headers: que uvicorn no reescriba la IP del cliente con
# X-Forwarded-For (lo controla quien hace la peticion). La IP real para el
# rate limit sale de Fly-Client-IP, ver security.client_ip().
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers"]
