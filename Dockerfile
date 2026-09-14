# Aeltra Outbound — imagen para EasyPanel (o cualquier host con Docker)
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# deps primero (mejor cache)
COPY requirements.txt .
RUN pip install -r requirements.txt

# código
COPY . .

# la base SQLite vive en un volumen montado (ver EasyPanel abajo)
ENV DB_PATH=/data/aeltra.db
EXPOSE 8000

# EasyPanel puede inyectar $PORT; si no, usa 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
