import sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

import forecast_engine
forecast_engine._get_db = lambda: db

date_str = '2026-09-30'
daily = db.collection('ktoa_daily').document(date_str).get().to_dict()
act_skt = daily.get('mno_out', {}).get('S')
print(f"실제마감 SKT OUT ({date_str}): {act_skt}")

fc_crude_list = []
fc_ratio_list = []

for hour in range(11, 20):
    found = None
    for minute in ['00', '01', '10', '50', '59']:
        doc_id = f"{date_str}_{hour:02d}{minute}"
        doc = db.collection('ktoa_hourly').document(doc_id).get()
        if doc.exists:
            found = doc.to_dict()
            if minute == '00':
                break
    if not found:
        continue
    cur_skt = found.get('mno_out', {}).get('S', 0) or 0
    if not cur_skt:
        continue
    elapsed = max(1, hour - 10)
    fc_crude = int(cur_skt * 10 / elapsed)
    ratio = forecast_engine._get_hour_completion_ratio(date_str, hour)
    fc_ratio = int(cur_skt / ratio) if ratio > 0 else fc_crude
    fc_crude_list.append(fc_crude)
    fc_ratio_list.append(fc_ratio)
    print(f"  {hour}시: 실적누적={cur_skt:>5}  균일페이스예측={fc_crude:>6,}  완료율곡선예측={fc_ratio:>6,}  (ratio={ratio*100:.1f}%)")

def acc(preds, actual):
    if not preds or not actual:
        return None
    avg = sum(preds) / len(preds)
    return round((1 - abs(avg - actual) / abs(actual)) * 100, 1)

print()
print(f"균일페이스(현재 엑셀캡션 방식) 정확도: {acc(fc_crude_list, act_skt)}%  (평균예측={sum(fc_crude_list)/len(fc_crude_list):.0f})")
print(f"완료율곡선(현재 실제 배포된 예측) 정확도: {acc(fc_ratio_list, act_skt)}%  (평균예측={sum(fc_ratio_list)/len(fc_ratio_list):.0f})")
