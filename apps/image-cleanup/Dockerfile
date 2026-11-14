FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
WORKDIR /app
COPY cleanup.py .
ENV PYTHONUNBUFFERED=1
# 이 이미지에는 시스템 python3가 없어 gcloud 내장 파이썬을 씀
ENTRYPOINT ["/bin/sh", "-c", "PY=$(command -v python3 || ls /usr/lib/google-cloud-sdk/platform/bundledpythonunix/bin/python3 2>/dev/null); exec $PY /app/cleanup.py \"$@\"", "--"]
