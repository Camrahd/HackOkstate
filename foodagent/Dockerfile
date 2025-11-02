# Use official Python image
FROM python:3.11-slim

# Install system dependencies (GDAL and others)
RUN apt-get update && apt-get install -y gdal-bin libgdal-dev && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Collect static files (optional but good for production)
RUN python manage.py collectstatic --noinput || true

# Expose port
EXPOSE 8000

# Run Django using Gunicorn
CMD ["gunicorn", "foodagent.wsgi:application", "--bind", "0.0.0.0:8000"]
