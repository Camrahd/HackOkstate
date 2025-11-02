# Dockerfile — Render-ready, no GDAL compile hell
FROM python:3.11-slim

# 1. Install system dependencies (GDAL + PostgreSQL client)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Set GDAL version to match system package
ENV GDAL_VERSION=3.6.2

# 3. Install Python deps — GDAL wheel will match system lib
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir \
    "gdal==${GDAL_VERSION}" \
    -r requirements.txt

# 4. Copy app
WORKDIR /app
COPY . .

# 5. Django setup
RUN python manage.py collectstatic --noinput || true
RUN python manage.py migrate --noinput || true

# 6. Run as non-root
EXPOSE 8000
CMD ["gunicorn", "foodagent.wsgi:application", "--bind", "0.0.0.0:8000"]