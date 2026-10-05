FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 설치 (Playwright 의존성 포함)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 설치 (의존성 스킵)
RUN playwright install chromium
RUN playwright install-deps chromium || true

# 앱 코드 복사
COPY . .

# Cloud Run 실행 (timeout 900초 = 15분)
CMD exec gunicorn --bind :$PORT --workers 1 --timeout 900 main:app