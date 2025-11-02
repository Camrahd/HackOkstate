# Dockerfile — FINAL VERSION (Render-ready)
FROM python:3.11-slim

# 1. System deps
RUN apt-get update && apt-get install -y \
    gcc g++ libgdal-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. GDAL version
ENV GDAL_VERSION=3.6.2

# 3. App dir
WORKDIR /app

# 4. Copy & install deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir "gdal==${GDAL_VERSION}"
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy app
COPY . .

# 6. Django: collectstatic + migrate (now works!)
RUN python manage.py collectstatic --noinput
RUN python manage.py migrate --noinput

# 7. Run
EXPOSE 8000
CMD ["gunicorn", "foodagent.wsgi:application", "--bind", "0.0.0.0:8000"]