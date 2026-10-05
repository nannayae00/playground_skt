from ktoa_mvno_period_aggregator import _get_db

db = _get_db()
docs = db.collection("ktoa_mvno_operator_registry").stream()

rows = []
for doc in docs:
    d = doc.to_dict()
    rows.append((
        d.get("first_seen_at") or "?",
        d.get("first_in_date") or "(실적없음)",
        d.get("code"),
        d.get("name"),
        d.get("network"),
    ))

rows.sort(key=lambda r: r[0])

for seen, in_date, code, name, net in rows:
    print(f"{seen}\t{in_date}\t{code}\t{name}\t{net}")
