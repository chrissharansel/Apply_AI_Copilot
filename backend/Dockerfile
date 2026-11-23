FROM node:22-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:/usr/local/bin:${PATH}"

WORKDIR /app

# Python runtime and certificates. Playwright's --with-deps installs Chromium's
# required Linux libraries in this image (the build runs as root).
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# GitHub Copilot CLI requires Node.js 22+ (provided by the base image).
RUN npm install --global @github/copilot

# Install Chromium and its OS-level dependencies at image-build time.
RUN python -m playwright install --with-deps chromium

COPY backend/ ./

RUN mkdir -p /app/storage && chmod 755 /app/storage

EXPOSE 10000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
