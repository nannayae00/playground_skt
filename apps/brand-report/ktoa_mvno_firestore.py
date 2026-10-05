"""
ktoa_mvno_firestore.py  v2.1
작성일: 2026-07-28

[수정 이력]
v2.1 | 2026-08-07 | 사업자 마스터 리스트 + 신규 사업자 2단계 알림 기능 추가.
  신규 컬렉션 ktoa_mvno_operator_registry/{code} 신설 - 등록일(first_seen_at,
  get_operator_list()에 처음 나타난 날)과 실적시작일(first_in_date, total_in>0이
  처음 나온 날)을 별도로 기록. 이 둘은 대개 다른 날짜임(등록만 되고 실제 서비스는
  나중에 시작하는 경우가 실제로 있음 - 사용자 지적).
  - register_new_operators(): get_operator_list() 결과와 registry를 비교해서
    새 코드를 registry에 등록하고 신규 목록 반환(1차 "등록 감지" 알림용)
  - check_in_start(): 이번 수집 결과(results)에서 total_in>0인 사업자 중
    registry의 first_in_date가 아직 비어있는 것을 찾아 채우고 반환(2차
    "실적 시작" 알림용) - 등록 시점과 별개 타이밍에 별도 알림 발송 목적
  - 기존 사업자(2024-12~ 이미 활동 중)는 backfill_operator_registry.py로
    별도 1회 시딩(알림 없이 조용히 채움) - 이 함수들은 그 이후 신규 건만 대응
v2.0 | 2026-07-28 | 컬렉션/필드명을 in/out 관점으로 직관화 + carrier_summary 추가
  - ktoa_mvno_flow        → ktoa_mvno_brand_in   (사업자별 유입 상세, to 기준)
  - ktoa_mvno_flow_pivot  → ktoa_mvno_brand_out  (사업자별 유출 상세, from 기준)
  - 신규: ktoa_carrier_summary
    SKT/KT/LGU+/S-MVNO/K-MVNO/L-MVNO 6개 carrier 간 in/out/net 요약 (1일 1문서)
    brand_in 데이터를 carrier 단위로 group-by 합산해서 생성 (별도 스크래핑 불필요)
v1.0 | 2026-07-27 | 최초 작성 (ktoa_mvno_flow / ktoa_mvno_flow_pivot)
"""

import logging

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

log = logging.getLogger(__name__)

# 6개 carrier 그룹 (원조 3사 + MVNO 3사 합산군)
CARRIERS = ["SKT", "KT", "LGU+", "S-MVNO", "K-MVNO", "L-MVNO"]


def _get_db():
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project="mvno-484509", database="mvno-data")


def save_brand_in_batch(results: dict) -> dict:
    """
    results: { code: {to, to_code, to_network, days: {date: {total_market, total_in, flows}}} }
    ktoa_mvno_brand_in/{date}_{brand} 문서로 저장 (batch write, 500개 단위 분할)

    반환값: {brand_name: {code, network}} 매핑 (build_carrier_summary에서 carrier 판별용으로 재사용)
    """
    db = _get_db()
    batch = db.batch()
    count = 0
    total_written = 0
    brand_registry: dict[str, dict] = {}

    for code, parsed in results.items():
        to_name = parsed["to"]
        to_code = parsed["to_code"]
        to_network = parsed["to_network"]
        brand_registry[to_name] = {"code": to_code, "network": to_network}

        for date_str, day_data in parsed["days"].items():
            doc_id = f"{date_str}_{to_name}"
            ref = db.collection("ktoa_mvno_brand_in").document(doc_id)
            payload = {
                "date": date_str,
                "brand": to_name,
                "brand_code": to_code,
                "network": to_network,
                "total_in": day_data["total_in"],
                "reference_total": day_data["total_market"],
                "inflows": day_data["flows"],  # {from_brand: count, ...}
                "collected_at": fs.SERVER_TIMESTAMP,
            }
            batch.set(ref, payload, merge=True)
            count += 1
            total_written += 1

            if count >= 400:  # Firestore batch 한도(500) 여유있게
                batch.commit()
                batch = db.batch()
                count = 0

    if count > 0:
        batch.commit()

    log.info(f"ktoa_mvno_brand_in 저장 완료: {total_written}건")
    return brand_registry


def build_brand_out(ym: str) -> None:
    """
    당월(ym) 전체 ktoa_mvno_brand_in 문서를 읽어 from 기준으로 transpose,
    ktoa_mvno_brand_out/{date}_{brand} 문서로 저장.
    """
    db = _get_db()

    docs = list(
        db.collection("ktoa_mvno_brand_in")
        .where("date", ">=", f"{ym}-01")
        .where("date", "<=", f"{ym}-31")
        .stream()
    )
    log.info(f"brand_out 대상 문서: {len(docs)}건 ({ym})")

    # date -> from_brand -> {to_brand: count}
    pivot_data: dict[str, dict[str, dict[str, int]]] = {}

    for doc in docs:
        d = doc.to_dict()
        date_str = d["date"]
        to_name = d["brand"]
        inflows = d.get("inflows", {})

        pivot_data.setdefault(date_str, {})

        for from_name, cnt in inflows.items():
            pivot_data[date_str].setdefault(from_name, {})
            pivot_data[date_str][from_name][to_name] = cnt

    batch = db.batch()
    count = 0
    total_written = 0

    for date_str, from_map in pivot_data.items():
        for from_name, outflows in from_map.items():
            total_out = sum(outflows.values())
            doc_id = f"{date_str}_{from_name}"
            ref = db.collection("ktoa_mvno_brand_out").document(doc_id)
            payload = {
                "date": date_str,
                "brand": from_name,
                "total_out": total_out,
                "outflows": outflows,  # {to_brand: count, ...}
                "collected_at": fs.SERVER_TIMESTAMP,
            }
            batch.set(ref, payload, merge=True)
            count += 1
            total_written += 1

            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0

    if count > 0:
        batch.commit()

    log.info(f"ktoa_mvno_brand_out 저장 완료: {total_written}건")


def build_carrier_summary(ym: str, brand_registry: dict = None) -> None:
    """
    당월(ym) 전체 ktoa_mvno_brand_in 문서를 6개 carrier(SKT/KT/LGU+/S-MVNO/K-MVNO/L-MVNO)
    단위로 group-by 합산하여 ktoa_carrier_summary/{date} 문서로 저장.

    brand_registry 인자는 더 이상 사용하지 않음(하위호환용으로만 남김) — 부분 실행
    (TEST_ONLY_* 등) 시 이번 실행분 사업자만으로 판별하면 과거에 쌓인 다른 사업자들이
    resolve_carrier에서 전부 None 처리되는 버그가 있었음. 이제 매번 브랜드->network
    매핑을 이번에 읽은 전체 브랜드 문서에서 직접 재구성해서 사용.
    """
    db = _get_db()

    docs = list(
        db.collection("ktoa_mvno_brand_in")
        .where("date", ">=", f"{ym}-01")
        .where("date", "<=", f"{ym}-31")
        .stream()
    )
    log.info(f"carrier_summary 대상 문서: {len(docs)}건 ({ym})")

    docs_data = [doc.to_dict() for doc in docs]

    # 브랜드명 -> network 매핑을 이번에 읽은 문서들 자체에서 재구성 (부분 실행에도 안전)
    name_to_network: dict[str, str] = {}
    for d in docs_data:
        name_to_network[d["brand"]] = d.get("network")

    # 엑셀 컬럼 헤더(inflows의 from 키)와 팝업 사업자명(brand, to로 스크래핑한 이름)이
    # 다르게 표기되는 사업자들 — 발견되는 대로 여기 추가.
    # 예: 팝업/brand_in에는 "세종텔레콤(KT)"로 저장되지만, 엑셀 컬럼 헤더(inflows 키)는 "세종텔레콤"만 사용.
    NAME_ALIASES = {
        "세종텔레콤": "세종텔레콤(KT)",
        "SK텔링크": "SK텔링크(재판매)",
        "KCT": "KCT(미사용)",
    }

    def resolve_carrier(name: str):
        # 원조 3사는 이름 자체로 판별
        if name == "SKT":
            return "SKT"
        if name == "KT":
            return "KT"
        if name in ("LGU+", "LGT"):
            return "LGU+"
        # MVNO는 문서에서 재구성한 network로 판별 (별칭 매핑도 시도)
        lookup_name = NAME_ALIASES.get(name, name)
        net = name_to_network.get(lookup_name)  # "SKT" / "KT" / "LGU"
        return {"SKT": "S-MVNO", "KT": "K-MVNO", "LGU": "L-MVNO"}.get(net)

    # date -> {to_carrier: {from_carrier: count}}
    summary: dict[str, dict[str, dict[str, int]]] = {}
    unresolved = set()

    for d in docs_data:
        date_str = d["date"]
        to_carrier = resolve_carrier(d["brand"])
        if not to_carrier:
            unresolved.add(d["brand"])
            continue

        summary.setdefault(date_str, {c: {c2: 0 for c2 in CARRIERS} for c in CARRIERS})

        for from_name, cnt in d.get("inflows", {}).items():
            from_carrier = resolve_carrier(from_name)
            if not from_carrier:
                unresolved.add(from_name)
                continue
            summary[date_str][to_carrier][from_carrier] += cnt

    if unresolved:
        log.warning(f"carrier 판별 실패(무시됨) {len(unresolved)}개: {sorted(unresolved)[:15]}")

    MVNO_GROUPS = ["S-MVNO", "K-MVNO", "L-MVNO"]
    MNO_CARRIERS = ["SKT", "KT", "LGU+"]

    batch = db.batch()
    count = 0
    total_written = 0

    for date_str, matrix in summary.items():
        totals_in = {c: sum(matrix[c].values()) for c in CARRIERS}
        totals_out = {c: sum(matrix[c2].get(c, 0) for c2 in CARRIERS) for c in CARRIERS}
        net_change = {c: totals_in[c] - totals_out[c] for c in CARRIERS}

        # MNO 3사 기준 "MVNO로만"의 out (공식 리포트 'MNO Out'과 동일 정의, 골드 대조로 검증 완료).
        # 주의: 'MNO 순증감'은 이 mvno_out 기준이 아니라 net_change(전체 기준, MNO간 이동 포함)를
        # 써야 공식 리포트와 일치함 — 실제 검증 결과 net_change가 공식 순증감과 정확히 일치했음.
        mvno_out = {m: sum(matrix[g].get(m, 0) for g in MVNO_GROUPS) for m in MNO_CARRIERS}

        ref = db.collection("ktoa_carrier_summary").document(date_str)
        payload = {
            "date": date_str,
            "matrix": matrix,        # matrix[to_carrier][from_carrier] = count (원본, MNO간 포함 전체)
            "total_in": totals_in,   # 전체 유입 (MNO간+MVNO간 다 포함) = 리포트 'MVNO IN'
            "total_out": totals_out,  # 전체 유출 (MNO간+MVNO간 다 포함) = 리포트 'MVNO Out'
            "net_change": net_change,  # 전체 순증감 = 리포트 'MNO 순증감' & 'MVNO 순증감' 둘 다 이 필드 사용
            "mvno_out": mvno_out,      # MNO 3사만: MVNO로의 유출만 (= 공식 'MNO Out'과 동일 정의, 검증완료)
            "collected_at": fs.SERVER_TIMESTAMP,
        }
        batch.set(ref, payload, merge=True)
        count += 1
        total_written += 1

        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()

    log.info(f"ktoa_carrier_summary 저장 완료: {total_written}건")


# ─────────────────────────────────────────────────────────────
# 사업자 마스터 리스트 (신규 사업자 2단계 감지)
# ─────────────────────────────────────────────────────────────

def get_known_operator_codes(db=None) -> set:
    """registry에 이미 등록된 코드 전체(집합)."""
    db = db or _get_db()
    docs = db.collection("ktoa_mvno_operator_registry").stream()
    return {d.id for d in docs}


def register_new_operators(operators: list, today_str: str) -> list:
    """
    get_operator_list()가 반환한 "현재 KTOA 사이트의 전체 사업자 목록"과
    registry를 비교해서 처음 보는 코드를 registry에 등록.
    반환값: 신규로 등록된 사업자 목록(1차 "등록 감지" 알림에 사용).
    등록 시점엔 first_in_date를 아직 모르므로 None으로 둠 - 실적이 실제로
    잡히기 시작하면 check_in_start()가 채움.
    """
    db = _get_db()
    known = get_known_operator_codes(db)
    new_ops = [op for op in operators if op["code"] not in known]

    if not new_ops:
        return []

    batch = db.batch()
    for op in new_ops:
        ref = db.collection("ktoa_mvno_operator_registry").document(op["code"])
        batch.set(ref, {
            "code": op["code"],
            "name": op["name"],
            "network": op["network"],
            "first_seen_at": today_str,
            "is_estimated_first_seen": False,  # 실시간으로 직접 감지한 것 - 추정치 아님
            "first_in_date": None,
            "in_start_notified": False,
            "updated_at": fs.SERVER_TIMESTAMP,
        })
    batch.commit()
    log.info(f"신규 사업자 registry 등록: {len(new_ops)}개")
    return new_ops


def check_in_start(results: dict) -> list:
    """
    이번 수집 결과(results: {code: parsed}) 중 total_in>0인 날짜가 있는
    사업자에 대해, registry의 first_in_date가 아직 비어있으면(=등록은 됐지만
    실적이 한 번도 없었던 상태) 그 최초 날짜로 채우고 알림 대상으로 반환.
    (2차 "실적 시작" 알림용 - register_new_operators()의 등록 감지와는
    별개 시점에 별도로 발송됨)
    """
    db = _get_db()
    started = []

    for code, parsed in results.items():
        in_dates = [
            ds for ds, day in parsed.get("days", {}).items()
            if (day.get("total_in") or 0) > 0
        ]
        if not in_dates:
            continue
        earliest = min(in_dates)

        ref = db.collection("ktoa_mvno_operator_registry").document(code)
        doc = ref.get()
        if not doc.exists:
            continue  # registry에 없는 코드(백필/등록감지 이전 상태) - 건드리지 않음

        data = doc.to_dict()
        if data.get("first_in_date") is None and not data.get("in_start_notified"):
            ref.update({
                "first_in_date": earliest,
                "in_start_notified": True,
                "updated_at": fs.SERVER_TIMESTAMP,
            })
            started.append({
                "code": code,
                "name": data.get("name"),
                "network": data.get("network"),
                "date": earliest,
            })

    if started:
        log.info(f"실적 시작 감지: {len(started)}개")
    return started
