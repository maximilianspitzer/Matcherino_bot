FROM python:3.10-slim

# Install system dependencies including bash (bash is required by your entrypoint script)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc postgresql-client bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy requirements file and install build-time dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the files
COPY . .

# Fix line endings and ensure the entrypoint script is executable
RUN sed -i 's/\r$//' docker-entrypoint.sh && \
    chmod +x docker-entrypoint.sh

# Create a persistent cache directory (this is mapped on Unraid)
RUN mkdir -p /app/cache && chmod 777 /app/cache

# Create a non-root user and adjust ownership
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Use an absolute path for the entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]
