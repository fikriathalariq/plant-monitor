FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies needed for psycopg2 and compilation
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install python dependencies including gunicorn and redis
RUN pip install --no-cache-dir -r requirements.txt gunicorn redis django-redis

# Copy project files
COPY . .

# Expose port
EXPOSE 8080

# Command to run application
CMD ["gunicorn", "plant_monitor.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "60"]
