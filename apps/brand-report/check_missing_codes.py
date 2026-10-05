from ktoa_mvno_period_aggregator import _get_db
from datetime import date, timedelta

db = _get_db()

# 시트에 없던 코드들 + 반대로 확인 필요했던 코드(K49/K50)
target_codes = {
    "S06",
    "K05", "K16", "K19", "K25", "K28", "K31", "K37", "K42", "CJM", "ONS",
    "L03", "L08", "L09", "L23", "L29", "L32", "L35", "L37", "L38",
    "K49", "K50",
}

sum_in = {code: 0 for code in target_codes}
name = {}

d = date(2026, 7, 1)
end = date(2026, 7, 31)
while d <= end:
    ds = d.isoformat()
    docs = db.collection("ktoa_mvno_brand_in").where("date", "==", ds).stream()
    for doc in docs:
        data = doc.to_dict()
        code = data.get("brand_code")
        if code in target_codes:
            sum_in[code] += data.get("total_in") or 0
            name[code] = data.get("brand")
    d += timedelta(days=1)

for code in sorted(sum_in.keys(), key=lambda c: -sum_in[c]):
    print(f"{code}\t{name.get(code, '(7월 데이터 없음)')}\t{sum_in[code]:,}건")
