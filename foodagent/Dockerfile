# Dockerfile — Render-ready, GDAL fixed, requirements copied
FROM python:3.11-slim

# 1. Install system deps
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Set GDAL version
ENV GDAL_VERSION=3.6.2

# 3. Set workdir
WORKDIR /app

# 4. COPY requirements FIRST (better caching)
COPY requirements.txt .

# 5. Install GDAL + dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir "gdal==${GDAL_VERSION}"
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy app code
COPY . .

# 7. Django setup
RUN python manage.py collectstatic --noinput || true
RUN python manage.py migrate --noinput || true

# 8. Run
EXPOSE 8000
CMD ["gunicorn", "foodagent.wsgi:application", "--bind", "0.0.0.0:8000"]