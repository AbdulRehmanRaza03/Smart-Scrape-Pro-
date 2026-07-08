# ─────────────────────────────────────────────
# SmartScrape Pro — Dockerfile
# Multi-stage production build
# ─────────────────────────────────────────────

FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ curl wget \
    libpq-dev libffi-dev \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libgtk-3-0 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers
RUN playwright install chromium --with-deps

# App source
COPY . .

# Create required dirs
RUN mkdir -p database logs exports exports/uploads

# Non-root user for security
RUN useradd -m -u 1000 scraper && chown -R scraper:scraper /app
USER scraper

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
