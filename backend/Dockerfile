# ============================================
# Enterprise RAG Platform — Backend Dockerfile
# ============================================
# Multi-stage build for smaller final image.
# Uses slim Python image to minimize attack surface.

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
# (so logs appear immediately in Docker)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (if needed for future packages like PyMuPDF)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (Docker layer caching)
# This layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the API port
EXPOSE 8000

# Run FastAPI with uvicorn
# --host 0.0.0.0 makes it accessible from outside the container
# --reload enables hot-reload for development (removed in production)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
