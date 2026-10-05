"""
backfill_fc.py
5월 엑셀 리포트(S4 시트)에서 fc_ 예측값을 읽어 Firestore에 일괄 저장
- MVNO IN(SM/KM/LM/계), MNO Out(S/K/L/계), MVNO Out(SM/KM/LM/계)
- 순증감 = MVNO IN - MVNO OUT 자동 계산

사용법:
  python3 backfill_fc.py MVNO_리포트_2026-05-09.xlsx
"""
import sys
import json
from openpyxl import load_workbook
from google.cloud import firestore

def get_trio(ws, row, col):
    """Low/Mid/High 3개 값 읽기"""
    return {
        'low':  ws.cell(row,     col).value,
        'mid':  ws.cell(row + 1, col).value,
        'high': ws.cell(row + 2, col).value,
    }

def net_trio(fc_in, fc_out):
    """순증감 = MVNO IN - MVNO OUT"""
    result = {}
    for k in ['low', 'mid', 'high']:
        vi = fc_in.get(k)
        vo = fc_out.get(k)
        result[k] = (vi - vo) if (vi is not None and vo is not None) else None
    return result

def main(xlsx_path):
    wb = load_workbook(xlsx_path, data_only=True)
    ws4 = wb['월마감 예측 추이']

    # 열 → 날짜 매핑 (행3=일자, 행2=월)
    month = None
    col_date = {}
    for c in range(4, ws4.max_column + 1):
        mon = ws4.cell(2, c).value
        day = ws4.cell(3, c).value
        if mon and day and isinstance(day, int):
            month = int(mon) if isinstance(mon, int) else int(str(mon).replace('월','').strip())
            col_date[c] = f"2026-{month:02d}-{day:02d}"

    print(f"날짜 컬럼 매핑: {col_date}")

    # S4 시트에서 fc_ 값 읽기
    # 행번호는 위 분석 결과 기반
    # T-Out (MNO Out S): 행12~14
    # MVNO IN: SM=18~20, KM=23~25, LM=28~30, 계=33~35
    # MNO Out: S=39~41, K=44~46, L=49~51, 계=54~56
    # MVNO Out: SM=81~83, KM=86~88, LM=91~93, 계=96~98

    # 행번호 매핑 찾기 (동적)
    row_map = {}
    cur_sec = ''
    cur_grp = ''
    for r in range(1, ws4.max_row + 1):
        v1 = ws4.cell(r, 1).value
        v2 = ws4.cell(r, 2).value
        v3 = ws4.cell(r, 3).value
        if v1 and str(v1).startswith('■'):
            cur_sec = str(v1)
        if v2:
            cur_grp = str(v2)
        if v3 == '예측Low':
            key = f"{cur_sec}|{cur_grp}"
            row_map[key] = r

    print("\n행 매핑:")
    for k, v in row_map.items():
        print(f"  {k}: 행{v}")

    # Firestore 연결
    db = firestore.Client(project='mvno-484509', database='mvno-data')

    # 날짜별 fc_ 저장
    for col, date_str in col_date.items():
        fc_data = {}

        def trio(row):
            return {
                'low':  ws4.cell(row,     col).value,
                'mid':  ws4.cell(row + 1, col).value,
                'high': ws4.cell(row + 2, col).value,
            }

        # MVNO IN
        fc_mvno_in = {}
        for grp, key in [('SM','SM'), ('KM','KM'), ('LM','LM'), ('계','계')]:
            k = f"■ MVNO IN|{grp}"
            if k in row_map:
                fc_mvno_in[key] = trio(row_map[k])
        if fc_mvno_in:
            fc_data['fc_mvno_in'] = fc_mvno_in

        # MNO Out
        fc_mno_out = {}
        for grp, key in [('S','S'), ('K','K'), ('L','L'), ('계','계')]:
            k = f"■ MNO Out|{grp}"
            if k in row_map:
                fc_mno_out[key] = trio(row_map[k])
        if fc_mno_out:
            fc_data['fc_mno_out'] = fc_mno_out

        # MVNO Out
        fc_mvno_out = {}
        for grp, key in [('SM','SM'), ('KM','KM'), ('LM','LM'), ('계','계')]:
            k = f"■ MVNO Out|{grp}"
            if k in row_map:
                fc_mvno_out[key] = trio(row_map[k])
        if fc_mvno_out:
            fc_data['fc_mvno_out'] = fc_mvno_out

        # 순증감 = MVNO IN - MVNO OUT
        fc_net = {}
        for grp in ['SM', 'KM', 'LM', '계']:
            fi = fc_mvno_in.get(grp, {})
            fo = fc_mvno_out.get(grp, {})
            fc_net[grp] = net_trio(fi, fo)
        fc_data['fc_net'] = fc_net

        # T-Out 저장 (기존 fc_low/mid/high와 동일)
        skt_key = "■ SKT T-Out (MNO Out S)|계"
        if skt_key in row_map:
            t = trio(row_map[skt_key])
            fc_data['fc_mno_out']['S'] = t  # 이미 fc_mno_out에 있으면 덮어쓰기 불필요

        fc_data['fc_all_saved_at'] = date_str

        # 저장
        doc_ref = db.collection('ktoa_daily').document(date_str)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update(fc_data)
            mvno_in_mid = fc_mvno_in.get('계', {}).get('mid')
            mno_out_s_mid = fc_mno_out.get('S', {}).get('mid')
            print(f"✅ {date_str}: 저장 완료 (MVNO IN 계 mid={mvno_in_mid}, T-Out mid={mno_out_s_mid})")
        else:
            print(f"⚠️  {date_str}: ktoa_daily 문서 없음 → 스킵")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python3 backfill_fc.py MVNO_리포트_2026-05-09.xlsx")
        sys.exit(1)
    main(sys.argv[1])