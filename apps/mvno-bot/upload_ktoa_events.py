"""
upload_ktoa_events.py
KOTA.xlsx 이벤트 시트 → Firestore ktoa_events 컬렉션 업로드

[수정 이력]
v1.0 | 2026-03-24 | 최초 작성

Firestore 구조:
ktoa_events/{event_id}
├── name: 이벤트명
├── start_date: 시작일 (YYYY-MM-DD)
├── end_date: 종료일 (YYYY-MM-DD)
├── category: 단말출시 / 사고 / 정책 / 기타
├── carrier: SKT / KT / LGU+ / 삼성 / Apple / 전체
├── impact: positive / negative / neutral
└── memo: 비고
"""

import sys
sys.path.insert(0, '/home/mclee_cecilia/.local/lib/python3.12/site-packages')

from google.cloud import firestore

db = firestore.Client(project='mvno-484509', database='mvno-data')

# ── 이벤트 데이터 (엑셀에서 추출 + 메타정보 추가) ────────────────────────────
EVENTS = [
    {
        'name':       'Galaxy S24 출시',
        'start_date': '2024-01-26',
        'end_date':   '2024-01-26',
        'category':   '단말출시',
        'carrier':    '삼성',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'Galaxy Z플립/폴드6 출시',
        'start_date': '2024-07-19',
        'end_date':   '2024-07-19',
        'category':   '단말출시',
        'carrier':    '삼성',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'iPhone 16 출시',
        'start_date': '2024-09-20',
        'end_date':   '2024-09-20',
        'category':   '단말출시',
        'carrier':    'Apple',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'Galaxy S25 출시',
        'start_date': '2025-02-04',
        'end_date':   '2025-02-04',
        'category':   '단말출시',
        'carrier':    '삼성',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'SKT 유심(USIM) 정보 유출 사고',
        'start_date': '2025-04-22',
        'end_date':   '2025-04-22',
        'category':   '사고',
        'carrier':    'SKT',
        'impact':     'negative',
        'memo':       'SKT 가입자 유심 정보 해킹 사고',
    },
    {
        'name':       'SKT 전 고객 유심 무상 교체 선언',
        'start_date': '2025-04-25',
        'end_date':   '2025-04-25',
        'category':   '정책',
        'carrier':    'SKT',
        'impact':     'negative',
        'memo':       'SKT Out 급증 원인',
    },
    {
        'name':       'SKT 해지 위약금 면제 시행',
        'start_date': '2025-07-04',
        'end_date':   '2025-07-14',
        'category':   '정책',
        'carrier':    'SKT',
        'impact':     'negative',
        'memo':       'SKT Out 급증 원인',
    },
    {
        'name':       'Galaxy Z플립/폴드7 출시',
        'start_date': '2025-07-22',
        'end_date':   '2025-07-22',
        'category':   '단말출시',
        'carrier':    '삼성',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'KT 소액결제 침해 사고 발생',
        'start_date': '2025-08-05',
        'end_date':   '2025-08-05',
        'category':   '사고',
        'carrier':    'KT',
        'impact':     'negative',
        'memo':       '',
    },
    {
        'name':       'iPhone 17 출시',
        'start_date': '2025-09-19',
        'end_date':   '2025-09-19',
        'category':   '단말출시',
        'carrier':    'Apple',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'KT 해지 위약금 면제 시행',
        'start_date': '2025-12-31',
        'end_date':   '2026-01-13',
        'category':   '정책',
        'carrier':    'KT',
        'impact':     'negative',
        'memo':       'KT Out 급증 원인',
    },
    {
        'name':       'Galaxy S26 출시',
        'start_date': '2026-03-06',
        'end_date':   '2026-03-06',
        'category':   '단말출시',
        'carrier':    '삼성',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'iPhone 17e 출시',
        'start_date': '2026-03-11',
        'end_date':   '2026-03-11',
        'category':   '단말출시',
        'carrier':    'Apple',
        'impact':     'positive',
        'memo':       '',
    },
    {
        'name':       'LGU+ 전 고객 유심 무상 교체 선언',
        'start_date': '2026-03-18',
        'end_date':   '2026-03-18',
        'category':   '정책',
        'carrier':    'LGU+',
        'impact':     'negative',
        'memo':       'LGU+ Out 영향 예상',
    },
]

# ── 업로드 ────────────────────────────────────────────────────────────────────
for event in EVENTS:
    # doc_id: 날짜_이벤트명 (간단하게)
    doc_id = f"{event['start_date']}_{event['name'][:10].replace(' ', '_')}"

    payload = {**event, 'updated_at': firestore.SERVER_TIMESTAMP}
    db.collection('ktoa_events').document(doc_id).set(payload)
    print(f"✅ {doc_id}")

print(f"\n완료! {len(EVENTS)}건 업로드")