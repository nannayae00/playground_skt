import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

import forecast_engine
forecast_engine._get_db = lambda: db
import forecast_excel
forecast_excel._get_db = lambda: db

DATE = '2026-09-30'

print(f"===== 1) {DATE} 정시(on-the-hour) ktoa_hourly 문서 - DB 저장 예측값 점검 =====\n")
for hour in [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]:
    doc_id = f"{DATE}_{hour:02d}00"
    doc = db.collection('ktoa_hourly').document(doc_id).get()
    if not doc.exists:
        print(f"  {hour:02d}시 : 문서 없음 ({doc_id})")
        continue
    d = doc.to_dict()
    mno = d.get('mno_out', {}) or {}
    fmno = d.get('forecast_mno_out', {}) or {}
    mi = d.get('mvno_in', {}) or {}
    fmi = d.get('forecast_mvno_in', {}) or {}
    mo = d.get('mvno_out', {}) or {}
    fmo = d.get('forecast_mvno_out', {}) or {}
    src = d.get('source', '?')
    print(f"  {hour:02d}시 | source={src}")
    print(f"       현재 S={mno.get('S')} → 예측 S={fmno.get('S')} | 현재 SM_in={mi.get('SM')} → 예측 SM_in={fmi.get('SM')} | 현재 SM_out={mo.get('SM')} → 예측 SM_out={fmo.get('SM')}")

print()
print(f"===== 2) {DATE} 실제 마감(최종) 값 =====\n")
daily_doc = db.collection('ktoa_daily').document(DATE).get()
daily_data = daily_doc.to_dict() if daily_doc.exists else {}
act_s = (daily_data.get('mno_out', {}) or {}).get('S')
act_sm_in = (daily_data.get('mvno_in', {}) or {}).get('SM')
act_sm_out = (daily_data.get('mvno_out', {}) or {}).get('SM')
print(f"  실제 마감 S(SKT Out)={act_s} | SM IN={act_sm_in} | SM OUT={act_sm_out}")

print()
print(f"===== 3) get_daily_forecast_accuracy({DATE}) 직접 호출 결과 =====\n")
acc = forecast_excel.get_daily_forecast_accuracy(DATE, daily_data)
print(f"  {acc}")

print()
print(f"===== 4) 20시(마감) 시점 forecast_engine.get_field_daily_forecast() 직접 재계산 =====\n")
doc20 = db.collection('ktoa_hourly').document(f"{DATE}_2000").get()
if doc20.exists:
    d20 = doc20.to_dict()
    cur_s = (d20.get('mno_out', {}) or {}).get('S', 0) or 0
    cur_sm_in = (d20.get('mvno_in', {}) or {}).get('SM', 0) or 0
    cur_sm_out = (d20.get('mvno_out', {}) or {}).get('SM', 0) or 0
    fc_s = forecast_engine.get_field_daily_forecast(DATE, 20, 'mno_out', 'S', cur_s)
    fc_sm_in = forecast_engine.get_field_daily_forecast(DATE, 20, 'mvno_in', 'SM', cur_sm_in)
    fc_sm_out = forecast_engine.get_field_daily_forecast(DATE, 20, 'mvno_out', 'SM', cur_sm_out)
    def err(p, a):
        return None if not a else round(abs(p - a) / abs(a) * 100, 1)
    print(f"  20시 현재 S={cur_s} → 예측 마감 S={fc_s} (실제 {act_s}, 오차 {err(fc_s, act_s)}%)")
    print(f"  20시 현재 SM_in={cur_sm_in} → 예측 마감 SM_in={fc_sm_in} (실제 {act_sm_in}, 오차 {err(fc_sm_in, act_sm_in)}%)")
    print(f"  20시 현재 SM_out={cur_sm_out} → 예측 마감 SM_out={fc_sm_out} (실제 {act_sm_out}, 오차 {err(fc_sm_out, act_sm_out)}%)")
else:
    print("  20시 문서 없음")
