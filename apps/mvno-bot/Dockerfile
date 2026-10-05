FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 기존 파일
COPY main.py .
COPY config.py .
COPY date_parser.py .
COPY query_parser.py .
COPY data_aggregator.py .
COPY ktoa_scraper.py .
COPY ktoa_parser.py .
COPY ktoa_firestore.py .
COPY ktoa_telegram.py .
COPY bw_engine.py .
COPY forecast_excel.py .
COPY predict_gemini.py .
COPY prompt_builder.py .
COPY forecast_engine.py .
COPY backfill_hourly_pattern.py .
# [수정 20260924] target_goal_reader.py가 COPY 목록에서 누락돼 있었음 - config.py/
# ktoa_context_builder.py/main.py가 이 모듈로 월별 목표를 DB에서 동적 조회하려던
# 시도가 실제 운영 환경에선 매번 ImportError로 실패해 -5000/34000 하드코딩 폴백으로
# 떨어지고 있었음(이전 "버그 수정"이 배포는 됐지만 무효했던 원인).
COPY target_goal_reader.py .

# v3.0 신규 파일
COPY ai_intent_parser.py .
COPY context_bundler.py .
COPY utils.py .

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 main:app
COPY ktoa_context_builder.py .
COPY ktoa_context_period_builder.py .
COPY ktoa_morning_check.py .
COPY cafe_collector.py .
COPY cafe_collector_runner.py .
# 1778494812