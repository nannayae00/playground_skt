import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

import forecast_engine
forecast_engine._get_db = lambda: db

DATE = '2026-10-01'
TEST_DOC_ID = '_TEST_DRYRUN_MIN0_DELETE_ME'

# 오늘 10시 10분 문서의 현재값을 그대로 가져와 "정시(minute=0)" 호출을 흉내냄
src_doc = db.collection('ktoa_hourly').document(f'{DATE}_1011').get().to_dict()
current_vals = {
    'mvno_in':  src_doc.get('mvno_in', {}),
    'mno_out':  src_doc.get('mno_out', {}),
    'mvno_out': src_doc.get('mvno_out', {}),
}
print("입력 현재값:", current_vals)
print()

result = forecast_engine.predict_hourly(DATE, 10, 0, current_vals, TEST_DOC_ID)
print("predict_hourly() 반환값:")
print(result)
print()

# 실제로 DB에 뭐가 저장됐는지 확인
saved = db.collection('ktoa_hourly').document(TEST_DOC_ID).get().to_dict()
print("DB에 저장된 내용:")
print(saved)

# 테스트 문서 정리
db.collection('ktoa_hourly').document(TEST_DOC_ID).delete()
print()
print("[테스트 문서 삭제 완료]")
