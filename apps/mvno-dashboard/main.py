# main.py
# ============================================================
# [수정 이력]
# v1.0 | 2026-05-27 | 최초 작성
#   - FastAPI 기반 MVNO Intelligence 대시보드 서버
#   - Basic Auth 미들웨어 포함
#   - /api/realtime, /api/daily, /api/archive 엔드포인트
#   - Step 1: 실시간 탭 Firestore 연동
# ============================================================

import os
import base64
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import firestore_client as fc
import data_processor as dp

# ── 환경 변수 ─────────────────────────────────────────────
DASHBOARD_ID = os.environ.get("DASHBOARD_ID", "mvno")
DASHBOARD_PW = os.environ.get("DASHBOARD_PW", "skt2024!")

KST = timezone(timedelta(hours=9))

# ── FastAPI 앱 ────────────────────────────────────────────
app = FastAPI(title="MVNO Intelligence Hub")
templates = Jinja2Templates(directory="templates")


# ══════════════════════════════════════════════════════════
# Basic Auth 미들웨어
# ══════════════════════════════════════════════════════════

@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    # /health 는 인증 제외 (Cloud Run 헬스체크)
    if request.url.path in ("/health", "/favicon.ico"):
        return await call_next(request)

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            id_, pw = decoded.split(":", 1)
            if id_ == DASHBOARD_ID and pw == DASHBOARD_PW:
                return await call_next(request)
        except Exception:
            pass

    return Response(
        content="인증이 필요합니다.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="MVNO Dashboard"'},
    )


# ══════════════════════════════════════════════════════════
# 헬스체크
# ══════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(KST).isoformat()}


# ══════════════════════════════════════════════════════════
# API — 실시간 탭 데이터
# ══════════════════════════════════════════════════════════

@app.get("/api/realtime")
async def api_realtime():
    """
    실시간 탭 전체 데이터 반환
    - 장중: ktoa_hourly 최신
    - 마감: ktoa_daily 오늘
    """
    is_close = fc.is_close_time()

    try:
        if is_close:
            raw = fc.get_daily()
        else:
            raw = fc.get_latest_hourly()

        if raw is None:
            return JSONResponse({"error": "데이터 없음", "is_close": is_close}, status_code=404)

        snapshot_hour = raw.get("_snapshot_hour", datetime.now(KST).hour)
        comp = fc.get_hourly_comparison(snapshot_hour)

        metrics = dp.process_realtime(
            today     = raw,
            yesterday = comp.get("yesterday"),
            last_week = comp.get("last_week"),
            is_close  = is_close,
        )

        # 트렌드 테이블
        recent = fc.get_recent_daily(5)
        metrics["trend_rows"] = dp.process_trend_table(recent)

        # 군별 득실
        metrics["gain_loss"] = dp.process_gain_loss_table(raw)

        return JSONResponse(metrics)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ══════════════════════════════════════════════════════════
# API — 일별 리포트 데이터
# ══════════════════════════════════════════════════════════

@app.get("/api/daily")
async def api_daily(date: Optional[str] = None):
    """
    date: YYYY-MM-DD (없으면 오늘)
    """
    try:
        daily   = fc.get_daily(date)
        context = fc.get_context_daily(date)

        if daily is None:
            return JSONResponse({"error": f"{date or '오늘'} 데이터 없음"}, status_code=404)

        metrics = dp.process_realtime(
            today     = daily,
            yesterday = None,
            last_week = None,
            is_close  = True,
        )
        metrics["context"] = context or {}
        return JSONResponse(metrics)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ══════════════════════════════════════════════════════════
# API — 아카이브 목록
# ══════════════════════════════════════════════════════════

@app.get("/api/archive")
async def api_archive(limit: int = 30):
    try:
        items = fc.get_archive_list(limit)
        return JSONResponse({"items": items})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ══════════════════════════════════════════════════════════
# API — 주간/월간 컨텍스트
# ══════════════════════════════════════════════════════════

@app.get("/api/context/week")
async def api_context_week(yw: Optional[str] = None):
    data = fc.get_context_week(yw)
    return JSONResponse(data or {"error": "데이터 없음"})

@app.get("/api/context/month")
async def api_context_month(ym: Optional[str] = None):
    data = fc.get_context_month(ym)
    return JSONResponse(data or {"error": "데이터 없음"})


# ══════════════════════════════════════════════════════════
# 메인 페이지 (HTML)
# ══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # 아카이브 사이드바 목록은 서버사이드 렌더링
    archive_items = []
    try:
        archive_items = fc.get_archive_list(30)
    except Exception:
        pass

    return templates.TemplateResponse(
        "index.html",
        {
            "request":       request,
            "archive_items": archive_items,
            "now_kst":       datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "is_close":      fc.is_close_time(),
        }
    )


# ══════════════════════════════════════════════════════════
# 로컬 실행 (Cloud Run 에서는 gunicorn)
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True)
