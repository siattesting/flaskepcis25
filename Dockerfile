# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables to prevent Python from buffering stdout/stderr
# (Ensures logs show up immediately in Docker)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies (needed for some Postgres adapters)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Create a non-root user for security (Standard for production)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose port 8000
EXPOSE 8000

# The command to run the application using Gunicorn (Production Server)
# -w 4: Use 4 workers (Handle multiple requests concurrently)
# -b 0.0.0.0:5000: Bind to all interfaces
# run:app : "run.py" file, "app" object
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "src:create_app()"]