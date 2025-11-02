# Dockerfile — FINAL WORKING VERSION
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc g++ libgdal-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_VERSION=3.6.2
WORKDIR /app

# Copy & install deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir "gdal==${GDAL_VERSION}"
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Only run collectstatic if STATIC_ROOT is defined
RUN python -c "import os; from pathlib import Path; print('STATIC_ROOT:', os.path.join(Path(__file__).parent, 'staticfiles'))" && \
    python manage.py collectstatic --noinput || echo "collectstatic skipped (STATIC_ROOT not set)"

RUN python manage.py migrate --noinput

EXPOSE 8000
CMD ["gunicorn", "foodagent.wsgi:application", "--bind", "0.0.0.0:8000"]