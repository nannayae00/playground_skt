"""
daily_memo.py - 하루 단위 계산 결과 저장소 (Firestore 읽기 절감)

[추가 20261009]
ktoa-collector는 10분마다 새 프로세스로 뜨는 Cloud Run Job이라, forecast_engine의
프로세스 내 캐시(_hourly_docs_cache, _month_series_cache 등)가 매 실행마다 비어 있음.
그래서 메시지 1회 생성에 과거 데이터를 약 3,300건씩 다시 읽고 있었음
(하루 18~20만 건, 전체 Firestore 읽기의 55%).

과거 데이터만으로 계산되는 함수는 같은 날 안에서는 결과가 바뀌지 않으므로,
그날 처음 계산한 결과를 ktoa_memo/{KST 오늘} 문서 1개에 저장하고 이후 실행은
그 문서 1건만 읽어 재사용함. 날짜가 바뀌면 새 문서에서 다시 계산하므로
과거 데이터 보정(백필 등)은 다음 날부터 반영됨.

- 값은 JSON 문자열로 저장 (tuple은 list로 복원됨 - 호출측은 언패킹/인덱싱만 사용)
- 저장소 오류 시 항상 원래 함수를 그대로 실행 (기능 영향 없음)
- MEMO_DISABLE=1 환경변수로 끌 수 있음
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

log = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))
_COLLECTION = 'ktoa_memo'

_loaded_day = None
_store: dict = {}


def _db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault())
    return fs.Client(project='mvno-484509', database='mvno-data')


def _today() -> str:
    return datetime.now(_KST).strftime('%Y-%m-%d')


def _ensure_loaded(day: str) -> None:
    global _loaded_day, _store
    if _loaded_day == day:
        return
    _store = {}
    _loaded_day = day
    try:
        doc = _db().collection(_COLLECTION).document(day).get()
        if doc.exists:
            _store = dict((doc.to_dict() or {}).get('v') or {})
    except Exception as e:
        log.warning(f"[daily_memo] 로드 실패 (계산으로 진행): {e}")


def _save(day: str, key: str, value_json: str) -> None:
    try:
        _db().collection(_COLLECTION).document(day).set(
            {'v': {key: value_json}, 'updated_at': datetime.now(_KST)}, merge=True)
    except Exception as e:
        log.warning(f"[daily_memo] 저장 실패: {e}")


def memo_daily(fn):
    """같은 날(KST) 같은 인자면 저장된 결과를 재사용. 과거 데이터만 쓰는 함수에만 적용할 것."""
    name = fn.__name__

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if os.environ.get('MEMO_DISABLE') == '1':
            return fn(*args, **kwargs)
        day = _today()
        raw = f"{name}|{json.dumps([args, kwargs], sort_keys=True, default=str)}"
        key = hashlib.sha1(raw.encode()).hexdigest()
        _ensure_loaded(day)
        if key in _store:
            try:
                return json.loads(_store[key])
            except Exception:
                pass
        result = fn(*args, **kwargs)
        try:
            value_json = json.dumps(result)
        except (TypeError, ValueError):
            return result
        _store[key] = value_json
        _save(day, key, value_json)
        return result

    return wrapper


def is_past_month(year: int, month: int) -> bool:
    now = datetime.now(_KST)
    return (year, month) < (now.year, now.month)
