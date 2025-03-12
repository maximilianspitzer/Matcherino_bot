FROM python:3.10-slim

# Set up environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script and make it executable with explicit permissions
COPY docker-entrypoint.sh .
RUN chmod 755 /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Copy application code
COPY . .

# Create cache directory with proper permissions
RUN mkdir -p /app/cache && chmod 777 /app/cache

# Use the entrypoint script with shell form instead of exec form
ENTRYPOINT ["/bin/bash", "/app/docker-entrypoint.sh"] 