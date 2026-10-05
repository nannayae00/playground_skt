import json
from ktoa_mvno_period_aggregator import _get_db

db = _get_db()
doc = db.collection("ktoa_mvno_brand_insights").document("아이즈비전").get()

if doc.exists:
    data = doc.to_dict()
    def clean(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean(v) for v in obj]
        return obj
    cleaned = clean(data)
    with open("dump_아이즈비전.json", "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    print(json.dumps(cleaned, ensure_ascii=False, indent=2))
else:
    print("문서 없음")
