import sys
sys.path.insert(0, '.')
import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta
from calendar import monthrange

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

# 데이터 존재하는 전체 기간 파악 (ktoa_daily 중 bw_performance 있는 문서들)
docs = list(db.collection('ktoa_daily').stream())
by_date = {}
for d in docs:
    dd = d.to_dict()
    if dd and dd.get('bw_performance'):
        by_date[d.id] = float(dd['bw_performance'])

dates_sorted = sorted(by_date.keys())
print(f"bw_performance 존재 일자 수: {len(dates_sorted)}  (최초 {dates_sorted[0] if dates_sorted else '-'} ~ 최근 {dates_sorted[-1] if dates_sorted else '-'})")
print()

# 월별로 그룹화
months = {}
for ds in dates_sorted:
    ym = ds[:7]
    months.setdefault(ym, {})[ds] = by_date[ds]

print(f"{'월':>8} | {'1일':>7} {'2일':>7} {'3일':>7} | {'1~3일평균':>9} | {'그달전체평균':>10} | {'1~3일/전체비율':>12}")
ratios = []
day1_values = []
weekday_day1 = {}
for ym, dvals in sorted(months.items()):
    y, m = int(ym[:4]), int(ym[5:7])
    last_day = monthrange(y, m)[1]
    d1 = dvals.get(f"{ym}-01")
    d2 = dvals.get(f"{ym}-02")
    d3 = dvals.get(f"{ym}-03")
    first3 = [v for v in [d1, d2, d3] if v is not None]
    all_vals = list(dvals.values())
    month_avg = sum(all_vals) / len(all_vals) if all_vals else None
    first3_avg = sum(first3) / len(first3) if first3 else None
    ratio = (first3_avg / month_avg) if (first3_avg and month_avg) else None
    if ratio:
        ratios.append(ratio)
    if d1:
        day1_values.append(d1)
        wd = datetime.strptime(f"{ym}-01", '%Y-%m-%d').weekday()
        weekday_day1.setdefault(wd, []).append((ym, d1))
    print(f"{ym:>8} | {d1 if d1 else '-':>7} {d2 if d2 else '-':>7} {d3 if d3 else '-':>7} | "
          f"{(f'{first3_avg:.3f}' if first3_avg else '-'):>9} | {(f'{month_avg:.3f}' if month_avg else '-'):>10} | "
          f"{(f'{ratio:.3f}' if ratio else '-'):>12}")

print()
if ratios:
    print(f"월별 (1~3일평균/그달전체평균) 비율의 평균: {sum(ratios)/len(ratios):.3f}  (표본 {len(ratios)}개월)")
print()
print("=== 1일이 목요일이었던 달 (10/1=목요일과 동일 요일 비교) ===")
for wd, lst in sorted(weekday_day1.items()):
    wd_name = ['월','화','수','목','금','토','일'][wd]
    if wd == 3:
        print(f"목요일인 1일들: {lst}")
