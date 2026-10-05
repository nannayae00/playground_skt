import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

DATE = '2026-10-01'

docs = list(db.collection('ktoa_hourly').where('date', '==', DATE).stream())
docs.sort(key=lambda d: d.id)
print(f"오늘({DATE}) 총 {len(docs)}개 hourly 문서")
print()

on_hour = []
for doc in docs:
    d = doc.to_dict()
    fm = d.get('forecast_minute')
    fh = d.get('forecast_hour')
    if fm == 0:
        on_hour.append((doc.id, d))

print(f"정시 문서: {len(on_hour)}개\n")
print(f"{'시각':>6} | {'현재S':>6} {'예측S(마감)':>10} | {'현재SM_in':>9} {'예측SM_in':>9} | {'현재SM_out':>10} {'예측SM_out':>9} | source")
fc_s_list = []
for doc_id, d in on_hour:
    fh = d.get('forecast_hour')
    cur_s = (d.get('mno_out', {}) or {}).get('S', 0)
    fc_s = (d.get('forecast_mno_out', {}) or {}).get('S', 0)
    cur_smi = (d.get('mvno_in', {}) or {}).get('SM', 0)
    fc_smi = (d.get('forecast_mvno_in', {}) or {}).get('SM', 0)
    cur_smo = (d.get('mvno_out', {}) or {}).get('SM', 0)
    fc_smo = (d.get('forecast_mvno_out', {}) or {}).get('SM', 0)
    src = d.get('forecast_source')
    fc_s_list.append((fh, fc_s))
    print(f"{fh:>6} | {cur_s:>6} {fc_s:>10} | {cur_smi:>9} {fc_smi:>9} | {cur_smo:>10} {fc_smo:>9} | {src}")

print()
if len(fc_s_list) >= 2:
    vals = [v for _, v in fc_s_list]
    import statistics
    print(f"T Out(SKT S) 마감예측값 시간별 변동: min={min(vals)} max={max(vals)} "
          f"범위={max(vals)-min(vals)} (평균 {statistics.mean(vals):.0f} 대비 {(max(vals)-min(vals))/statistics.mean(vals)*100:.1f}%)")
    print(f"표준편차: {statistics.pstdev(vals):.1f}")
    print(f"최근 3개 시간 예측값: {vals[-3:]}")
