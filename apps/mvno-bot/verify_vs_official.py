"""
KTOA 공식 파일(MNP_번호이동_현황_202607.xls, '총계' 기준)과
우리 carrier_summary를 날짜별로 대조 검증.

공식 파일 구조: row0=코드헤더, row1=사업자명, row2~=일자별 데이터
  - 컬럼 1: 합계(그날 전체 총량)
  - 컬럼 2~133: 각 사업자 코드별 값 = "총계(전체 시장)"를 to로 봤을 때 그 사업자로부터의 유입
    (즉 이 값 자체가 "그 사업자가 다른 곳으로 내보낸 총량" = 우리의 total_out과 대응)
"""
import sys
import pandas as pd
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

import os
import glob

# 커맨드라인 인자 대신, 현재 폴더에서 "번호이동" 포함 xls 파일을 자동으로 찾음
# (파일명에 숨은 특수 공백 문자가 있어 셸에서 직접 경로 지정이 어려운 환경 대응)
candidates = glob.glob("*번호이동*.xls") + glob.glob("*MNP*.xls")
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    OFFICIAL_XLS = sys.argv[1]
elif candidates:
    OFFICIAL_XLS = candidates[0]
    print(f"[자동 탐색] 파일 발견: {OFFICIAL_XLS!r}")
else:
    print("공식 xls 파일을 찾을 수 없습니다. 현재 폴더의 파일 목록:")
    for f in os.listdir("."):
        if f.lower().endswith(".xls") or f.lower().endswith(".xlsx"):
            print(f"  {f!r}")
    sys.exit(1)

DATE = sys.argv[2] if len(sys.argv) > 2 else "2026-07-27"

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

df = pd.read_excel(OFFICIAL_XLS, header=None)
row0 = df.iloc[0].tolist()
row1 = df.iloc[1].tolist()

target_row = None
for i in range(2, len(df)):
    if str(df.iloc[i, 0]).strip() == DATE:
        target_row = df.iloc[i].tolist()
        break

if target_row is None:
    print(f"{DATE} 행을 찾을 수 없음")
    sys.exit(1)

official = {}  # code -> value
for i in range(2, len(row0)):
    code = row0[i]
    val = target_row[i]
    if pd.notna(code):
        official[str(code)] = int(val) if pd.notna(val) else 0

print(f"=== 공식 파일 {DATE} 데이터 (컬럼별 = 그 사업자에서 나간 총 유출량) ===")
print(f"SKT(원조): {official.get('SKT')}")
print(f"KTF(=KT): {official.get('KTF')}")
print(f"LGT(=LGU+): {official.get('LGT')}")
print(f"KCT: {official.get('KCT')}")
print(f"SKL: {official.get('SKL')}")
print(f"CJM: {official.get('CJM')}")
print(f"ONS: {official.get('ONS')}")

s_mvno_official = sum(v for k, v in official.items() if k.startswith("S") and len(k) == 3 and k[1:].isdigit())
k_mvno_official = sum(v for k, v in official.items() if k.startswith("K") and len(k) == 3 and k[1:].isdigit())
l_mvno_official = sum(v for k, v in official.items() if k.startswith("L") and len(k) == 3 and k[1:].isdigit())
print(f"\nS-MVNO 합계(공식): {s_mvno_official}")
print(f"K-MVNO 합계(공식): {k_mvno_official}")
print(f"L-MVNO 합계(공식): {l_mvno_official}")

print(f"\n=== 우리 carrier_summary {DATE} (total_out) ===")
cs = db.collection("ktoa_carrier_summary").document(DATE).get()
if cs.exists:
    d = cs.to_dict()
    print("total_out:", d.get("total_out"))
    print("total_in:", d.get("total_in"))
else:
    print("문서 없음")