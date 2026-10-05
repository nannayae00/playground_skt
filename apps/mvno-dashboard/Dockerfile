# Dockerfile
# ============================================================
# [수정 이력]
# v1.0 | 2026-05-27 | 최초 작성
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐싱)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 포트
EXPOSE 8080

# Cloud Run: gunicorn으로 실행
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "30", \
     "--access-logfile", "-"]
