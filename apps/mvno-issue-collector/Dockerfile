FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# [수정 20261005] 120→540: /daily-news 뉴스 스크랩이 동기 처리라 요청당 수 분 걸림.
# gunicorn 자체 --timeout(워커 워치독)이 Cloud Run --timeout(540, deploy.sh)보다 짧으면
# gunicorn이 먼저 워커를 SIGKILL해서 Service Unavailable이 발생함 (실측 확인).
CMD exec gunicorn --bind :$PORT --workers 1 --timeout 540 main:app
