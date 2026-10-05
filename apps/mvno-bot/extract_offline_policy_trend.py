import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

TARGET_LABELS = ['텔링크', 'KTM', '스카이', '유모비', '헬로']

SOURCES = {
    'busung': ['2026-09-23', '2026-09-24', '2026-09-28', '2026-09-29', '2026-10-01'],
    'vision': ['2026-09-23', '2026-09-24', '2026-09-29', '2026-09-30', '2026-10-01'],
}

for src, dates in SOURCES.items():
    col = f'offline_policy_{src}'
    print(f"===== {col} =====\n")
    for ds in dates:
        doc = db.collection(col).document(ds).get()
        d = doc.to_dict() if doc.exists else {}
        pbl = d.get('prices_by_label', {}) or {}
        print(f"--- {ds} (글: {d.get('subject')}) ---")
        for label in TARGET_LABELS:
            info = pbl.get(label)
            if not info:
                print(f"  {label}: (데이터없음)")
                continue
            plans = info.get('plans', info) if isinstance(info, dict) else info
            if isinstance(plans, dict) and 'plans' in plans:
                plans = plans['plans']
            if not isinstance(plans, list):
                print(f"  {label}: (plans 형식 아님) {str(info)[:200]}")
                continue
            # 7GB대, 11GB대 최고가(domestic_mnp) 추출
            def _num(v):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            def _gb(p):
                return _num(p.get('data_gb'))
            def _price(p):
                return _num(p.get('domestic_mnp')) or 0
            gb7  = [_price(p) for p in plans if (_gb(p) is not None) and 6 <= _gb(p) <= 8]
            gb11 = [_price(p) for p in plans if (_gb(p) is not None) and 10 <= _gb(p) <= 12]
            best_7 = max(gb7) if gb7 else None
            best_11 = max(gb11) if gb11 else None
            print(f"  {label}: 7G대 최고가={best_7} | 11G대 최고가={best_11}")
        print()
