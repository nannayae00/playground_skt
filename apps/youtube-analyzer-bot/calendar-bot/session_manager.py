"""
[수정 이력]
v1.0 | 2026-03-19 | 최초 작성 - 인메모리 세션 관리
v2.0 | 2026-03-20 | Firestore 기반 세션으로 교체 (Cloud Run 재시작 대응)
v2.1 | 2026-09-20 | consume() 추가 - 등록 버튼 더블클릭 시 두 요청이 모두
     | get()으로 같은 세션을 읽고 나중에 각자 clear()하는 사이에 둘 다
     | register_events()까지 진행해 일정이 중복 등록되던 race condition 수정.
     | Firestore 트랜잭션으로 "읽기+삭제"를 원자적으로 묶어서 동시 요청 중
     | 단 하나만 세션을 가져가도록 보장
"""

import os
import time
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_TTL = 600  # 10분


class SessionManager:
    def __init__(self):
        self._db = None
        self._collection = "calendar_bot_sessions"
        self._use_firestore = True

    def _get_db(self):
        if self._db is None:
            try:
                from google.cloud import firestore
                self._db = firestore.Client()
                logger.info("Firestore 세션 연결 성공")
            except Exception as e:
                logger.warning(f"Firestore 연결 실패, 인메모리로 fallback: {e}")
                self._use_firestore = False
                self._memory = {}
        return self._db

    def get(self, chat_id: int) -> Optional[dict]:
        if not self._use_firestore:
            return self._memory_get(chat_id)
        try:
            db = self._get_db()
            if not self._use_firestore:
                return self._memory_get(chat_id)
            doc = db.collection(self._collection).document(str(chat_id)).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            if time.time() - data.get("updated_at", 0) > SESSION_TTL:
                self.clear(chat_id)
                return None
            return data.get("session")
        except Exception as e:
            logger.error(f"Session get error: {e}")
            return None

    def set(self, chat_id: int, data: dict):
        if not self._use_firestore:
            return self._memory_set(chat_id, data)
        try:
            db = self._get_db()
            if not self._use_firestore:
                return self._memory_set(chat_id, data)
            db.collection(self._collection).document(str(chat_id)).set({
                "session": data,
                "updated_at": time.time(),
            })
            logger.info(f"Session saved to Firestore for {chat_id}: state={data.get('state')}")
        except Exception as e:
            logger.error(f"Session set error: {e}")

    def consume(self, chat_id: int) -> Optional[dict]:
        """세션을 원자적으로 읽고 즉시 삭제. 동시에 두 요청(더블클릭 등)이 들어와도
        Firestore 트랜잭션이 보장하는 낙관적 동시성 제어 덕분에 둘 중 하나만
        세션을 가져가고, 나머지는 None을 받는다 (호출 측에서 조용히 무시하면 됨)."""
        if not self._use_firestore:
            data = self._memory_get(chat_id)
            if data is not None:
                self._memory.pop(chat_id, None)
            return data
        try:
            from google.cloud import firestore
            db = self._get_db()
            if not self._use_firestore:
                data = self._memory_get(chat_id)
                if data is not None:
                    self._memory.pop(chat_id, None)
                return data
            doc_ref = db.collection(self._collection).document(str(chat_id))

            @firestore.transactional
            def _consume_txn(transaction, ref):
                snap = ref.get(transaction=transaction)
                if not snap.exists:
                    return None
                data = snap.to_dict()
                transaction.delete(ref)
                if time.time() - data.get("updated_at", 0) > SESSION_TTL:
                    return None
                return data.get("session")

            return _consume_txn(db.transaction(), doc_ref)
        except Exception as e:
            logger.error(f"Session consume error: {e}")
            return None

    def clear(self, chat_id: int):
        if not self._use_firestore:
            self._memory.pop(chat_id, None)
            return
        try:
            db = self._get_db()
            db.collection(self._collection).document(str(chat_id)).delete()
            logger.info(f"Session cleared from Firestore for {chat_id}")
        except Exception as e:
            logger.error(f"Session clear error: {e}")

    # 인메모리 fallback
    def _memory_get(self, chat_id):
        if not hasattr(self, '_memory'):
            self._memory = {}
        entry = self._memory.get(chat_id)
        if not entry:
            return None
        if time.time() - entry["updated_at"] > SESSION_TTL:
            del self._memory[chat_id]
            return None
        return entry["data"]

    def _memory_set(self, chat_id, data):
        if not hasattr(self, '_memory'):
            self._memory = {}
        self._memory[chat_id] = {"data": data, "updated_at": time.time()}