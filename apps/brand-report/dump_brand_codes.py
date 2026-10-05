from ktoa_mvno_period_aggregator import _get_db
from datetime import date, timedelta

db = _get_db()

# 최근 7월 한 달치 brand_in 문서를 훑어서 network별 (brand_code, brand) 유니크 목록 추출
seen = {}  # network -> {(code, name)}
d = date(2026, 7, 1)
end = date(2026, 7, 31)
while d <= end:
    ds = d.isoformat()
    docs = db.collection("ktoa_mvno_brand_in").where("date", "==", ds).stream()
    for doc in docs:
        data = doc.to_dict()
        net = data.get("network")
        code = data.get("brand_code")
        name = data.get("brand")
        seen.setdefault(net, set()).add((code, name))
    d += timedelta(days=1)

for net in sorted(seen.keys()):
    print(f"\n=== {net} ({len(seen[net])}개) ===")
    for code, name in sorted(seen[net], key=lambda x: (x[0] or "")):
        print(f"{code}\t{name}")
