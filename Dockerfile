FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# La base de datos vive en el volumen persistente de Fly (ver fly.toml),
# no en el filesystem efimero del contenedor -- asi sobrevive redeploys.
ENV DB_PATH=/data/empacadora.db

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
