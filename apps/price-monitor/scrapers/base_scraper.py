"""
base_scraper.py  v1.4

변경 이력:
  v1.0  최초 작성
  v1.1  RS_DATA_SET에 '월 100GB + 3Mbps' 추가 (모요 실측 확인)
  v1.2  RS 판별 기준 강화: RS_CRITERIA (data+voice 튜플) 추가
        classify_rs(data, voice) → 통화 조건 포함 판별
        (월 6GB+1Mbps + 통화200분 → RM, 통화무제한 → RS)
  v1.3  소수점 Mbps 정규화 추가 (2025-04-23)
        classify_rs() 진입 전 _normalize_mbps() 적용
        예) 1.024Mbps → 1Mbps, 5.12Mbps → 5Mbps (범용 반올림)
        이지모바일 Mbps 소수점 표기 변경으로 인한 RS 오분류 수정
        aldot_scraper / mvnohub_scraper 등 make_plan() 경유 스크래퍼 전체 자동 적용
  v1.4  classify_rs() 반환값 변경: bool → (is_rs, segment) (2026-06-30)
        · 증상: 알닷/허브의 '매일 NGB + Mbps'(data_gb<6) RS 요금제가
                comparator.py의 data_gb 기반 segment fallback(6GB 이상부터
                정의)에 안 걸려 구간(segment) 공란으로 빠지는 문제
        · 원인: classify_rs()가 is_rs bool만 반환하고 segment를 만들지
                않아, make_plan()이 만든 plan dict에 rs_segment 필드 자체가
                없었음 (모요 RS_RULES는 (data,voice)→segment까지 처리하던 것과 비대칭)
        · 수정: _resolve_rs_segment() 추가, classify_rs()가 (is_rs, segment)
                튜플 반환하도록 변경, make_plan()에 rs_segment 필드 추가
        · 호출부 영향: classify_rs()를 직접 호출하는 곳은 make_plan() 뿐이라
                       (aldot_scraper.py / mvnohub_scraper.py 직접 호출 없음 확인) 안전
─────────────────────────────────────────────────────────────────────────────
모든 스크래퍼의 공통 인터페이스 및 유틸리티
─────────────────────────────────────────────────────────────────────────────

리턴 데이터 표준 스펙 (plan dict):
  plan_id            : str   - 사이트 내 고유 ID
  source             : str   - 'moyo' | 'ald' | 'mvnohub' | 'phoneb' | 'weayo' | 'yogeum' | 'smtong' | 'toss'
  provider           : str   - 알뜰폰 사업자명
  name               : str   - 요금제명
  data               : str   - 데이터 표기 (예: '월 15GB + 3Mbps')
  data_gb            : float - GB 숫자 (무제한=9999)
  voice              : str   - 통화 (예: '무제한', '300분')
  sms                : str   - 문자 (예: '무제한', '100건')
  network            : str   - 'SKT' | 'KT' | 'LGU+'
  network_generation : str   - 'LTE' | '5G'
  final_price        : int   - 할인 후 월 요금(원)
  base_price         : int   - 할인 전 월 요금(원, 없으면 final_price와 동일)
  discount_months    : int   - 할인 개월수 (0이면 미표기)
  is_rs              : bool  - RS 요금제 여부
  subscribers        : int   - 가입자수 (없으면 0)
  scraped_at         : str   - UTC ISO 수집 시각
"""

import re
from datetime import datetime

# ── RS 요금제 데이터 패턴 (모요와 동일) ─────────────────────────────────────

# RS 요금제 판별 기준: (데이터 표기, 통화) 튜플
# 통화: '무제한' | '100분' | '300분'
RS_CRITERIA = {
    # 7G+ 구간 (통화 무제한)
    ('월 6GB + 1Mbps',  '무제한'), ('월 7GB + 1Mbps',  '무제한'),
    ('월 8GB + 1Mbps',  '무제한'), ('월 9GB + 1Mbps',  '무제한'),
    # 10G+ 구간 (통화 무제한)
    ('월 10GB + 1Mbps', '무제한'),
    # 11G+ 구간 (통화 무제한)
    ('월 10GB + 3Mbps', '무제한'), ('월 10GB + 매일 2GB + 3Mbps', '무제한'),
    ('월 11GB + 1Mbps', '무제한'), ('월 11GB + 3Mbps', '무제한'),
    ('월 11GB + 매일 2GB + 3Mbps', '무제한'),
    ('월 12GB + 1Mbps', '무제한'), ('월 13GB + 1Mbps', '무제한'),
    # 15G+100 구간 (통화 100분)
    ('월 15GB + 3Mbps', '100분'),
    # 15G+300 구간 (통화 300분)
    ('월 15GB + 3Mbps', '300분'),
    # 15G+ 기타 (통화 무제한)
    ('월 15GB + 1Mbps', '무제한'), ('월 15GB + 3Mbps', '무제한'),
    ('월 17GB + 3Mbps', '무제한'),
    # 100G+ 구간 (통화 무제한)
    ('매일 5GB + 5Mbps', '무제한'),
    ('월 40GB + 3Mbps', '무제한'),
    ('월 50GB + 1Mbps', '무제한'), ('월 54GB + 1Mbps', '무제한'),
    ('월 70GB + 1Mbps', '무제한'), ('월 74GB + 1Mbps', '무제한'),
    ('월 80GB + 1Mbps', '무제한'), ('월 90GB + 1Mbps', '무제한'),
    ('월 95GB + 3Mbps', '무제한'), ('월 99GB + 1Mbps', '무제한'),
    ('월 100GB + 3Mbps', '무제한'), ('월 100GB + 5Mbps', '무제한'),
    ('월 100GB + 515024Mbps', '무제한'),
    ('월 110GB + 1Mbps', '무제한'), ('월 110GB + 5Mbps', '무제한'),
    ('월 125GB + 5Mbps', '무제한'), ('월 135GB + 3Mbps', '무제한'),
    ('월 150GB + 5Mbps', '무제한'), ('월 160GB + 5Mbps', '무제한'),
    ('월 180GB + 10Mbps', '무제한'), ('월 200GB + 5Mbps', '무제한'),
    ('월 200GB + 10Mbps', '무제한'), ('월 210GB + 5Mbps', '무제한'),
    ('월 250GB + 5Mbps', '무제한'), ('월 300GB + 5Mbps', '무제한'),
    ('월 30GB + 1Mbps', '무제한'), ('월 30GB + 매일 2GB + 5Mbps', '무제한'),
    ('월 31GB + 1Mbps', '무제한'), ('월 36GB + 1Mbps', '무제한'),
    ('월 41GB + 1Mbps', '무제한'),
    ('월 1GB + 1Mbps',   '무제한'), ('월 1.4GB + 1Mbps', '무제한'),
    ('월 2GB + 1Mbps',   '무제한'), ('월 2.2GB + 1Mbps', '무제한'),
    ('월 2.25GB + 1Mbps','무제한'), ('월 2.5GB + 1Mbps', '무제한'),
    ('월 250MB + 1Mbps', '무제한'), ('월 300MB + 1Mbps', '무제한'),
    ('월 750MB + 1Mbps', '무제한'),
    ('월 3GB + 1Mbps',   '무제한'), ('월 3GB +월 4GB + 1Mbps', '무제한'),
    ('월 3.5GB + 1Mbps', '무제한'),
    ('월 4GB + 1Mbps',   '무제한'), ('월 4.5GB + 1Mbps', '무제한'),
    ('월 5GB + 1Mbps',   '무제한'), ('월 5GB + 5Mbps',   '무제한'),
    ('월 24GB + 1Mbps',  '무제한'), ('월 15GB + 35024Mbps', '무제한'),
}

RS_DATA_SET = {
    '월 7GB + 1Mbps', '월 10GB + 1Mbps', '월 11GB + 매일 2GB + 3Mbps',
    '월 15GB + 3Mbps', '매일 5GB + 5Mbps', '월 1.4GB + 1Mbps',
    '월 100GB + 3Mbps', '월 100GB + 515024Mbps', '월 100GB + 5Mbps', '월 10GB + 3Mbps',
    '월 10GB + 매일 2GB + 3Mbps', '월 110GB + 1Mbps', '월 110GB + 5Mbps',
    '월 11GB + 1Mbps', '월 11GB + 3Mbps', '월 125GB + 5Mbps',
    '월 12GB + 1Mbps', '월 135GB + 3Mbps', '월 13GB + 1Mbps',
    '월 150GB + 5Mbps', '월 15GB + 1Mbps', '월 15GB + 35024Mbps',
    '월 160GB + 5Mbps', '월 17GB + 3Mbps', '월 180GB + 10Mbps',
    '월 1GB + 1Mbps', '월 2.25GB + 1Mbps', '월 2.2GB + 1Mbps',
    '월 2.5GB + 1Mbps', '월 200GB + 10Mbps', '월 200GB + 5Mbps',
    '월 210GB + 5Mbps', '월 24GB + 1Mbps', '월 250GB + 5Mbps',
    '월 250MB + 1Mbps', '월 2GB + 1Mbps', '월 3.5GB + 1Mbps',
    '월 300GB + 5Mbps', '월 300MB + 1Mbps', '월 30GB + 1Mbps',
    '월 30GB + 매일 2GB + 5Mbps', '월 31GB + 1Mbps', '월 36GB + 1Mbps',
    '월 3GB + 1Mbps', '월 3GB +월 4GB + 1Mbps', '월 4.5GB + 1Mbps',
    '월 40GB + 3Mbps', '월 41GB + 1Mbps', '월 4GB + 1Mbps',
    '월 50GB + 1Mbps', '월 54GB + 1Mbps', '월 5GB + 1Mbps',
    '월 5GB + 5Mbps', '월 6GB + 1Mbps', '월 70GB + 1Mbps',
    '월 74GB + 1Mbps', '월 750MB + 1Mbps', '월 80GB + 1Mbps',
    '월 8GB + 1Mbps', '월 90GB + 1Mbps', '월 95GB + 3Mbps',
    '월 99GB + 1Mbps', '월 9GB + 1Mbps',
}

# ── 공통 파싱 유틸 ────────────────────────────────────────────────────────────

def parse_network(raw: str) -> str:
    r = raw.replace('망', '').replace(' ', '').upper()
    if 'SKT' in r:                    return 'SKT'
    if 'KT' in r and 'LGU' not in r: return 'KT'
    return 'LGU+'

def parse_data_gb(raw: str) -> float:
    if not raw: return 0
    if '무제한' in raw: return 9999
    m = re.search(r'([\d.]+)\s*GB', raw, re.IGNORECASE)
    if m: return float(m.group(1))
    m = re.search(r'([\d.]+)\s*MB', raw, re.IGNORECASE)
    if m: return round(float(m.group(1)) / 1024, 3)
    return 0

def parse_price(raw: str) -> int:
    if not raw: return 0
    m = re.search(r'([\d,]+)원', raw.replace(' ', ''))
    return int(m.group(1).replace(',', '')) if m else 0

def parse_price_int(v) -> int:
    """숫자/문자열 → int 원"""
    if isinstance(v, int):   return v
    if isinstance(v, float): return int(v)
    if isinstance(v, str):
        cleaned = re.sub(r'[^\d]', '', v)
        return int(cleaned) if cleaned else 0
    return 0

def parse_discount_months(raw: str):
    """'7개월 이후 47,300원' → (7, 47300)"""
    m_mon = re.search(r'(\d+)개월', raw)
    m_pri = re.search(r'([\d,]+)원', raw)
    months = int(m_mon.group(1)) if m_mon else 0
    price  = int(m_pri.group(1).replace(',', '')) if m_pri else 0
    return months, price

def parse_subscribers(raw: str) -> int:
    m = re.search(r'([\d,]+)', raw)
    return int(m.group(1).replace(',', '')) if m else 0

def _normalize_mbps(raw: str) -> str:
    """
    소수점 Mbps → 반올림 정수 Mbps 변환 (범용)
    예) 1.024Mbps → 1Mbps, 5.12Mbps → 5Mbps
    정수 표기(1Mbps, 3Mbps 등)는 그대로 통과
    """
    return re.sub(
        r'([\d.]+)\s*Mbps',
        lambda m: f"{round(float(m.group(1)))}Mbps",
        raw
    )

SEGMENT_RANGES = {
    '7G+':     (6,    10),
    '10G+':    (10,   11),
    '11G+':    (11,   15),
    '15G+100': (15,   15.1),
    '15G+300': (15.1, 16),
    '100G+':   (16,   9999),
}

def _resolve_rs_segment(data: str, voice: str, data_gb: float) -> str:
    """
    RS 요금제의 segment 결정 (comparator.py의 SEGMENT_RANGES와 동일 기준)
    v1.3에서 누락됐던 부분: classify_rs()가 bool만 반환하고 segment를
    안 만들어줘서, '매일 NGB + Mbps'(data_gb<6) 같은 RS 요금제가
    구간표(6GB 이상부터 정의됨)에 안 걸려 segment 공란이 되는 문제 수정.
    """
    v = voice.strip().replace('통화 ', '')
    # 15GB 구간은 통화 조건으로 100/300 분리
    if data == '월 15GB + 3Mbps':
        if v == '100분': return '15G+100'
        if v == '300분': return '15G+300'
        if v == '무제한': return '15G+300'
    # '매일 NGB + Mbps' 형태(일일 데이터)는 RS_CRITERIA상 전부 100G+ 구간
    if data.strip().startswith('매일'):
        return '100G+'
    for seg, (lo, hi) in SEGMENT_RANGES.items():
        if lo <= data_gb < hi:
            return seg
    return ''

def classify_rs(data_label: str, voice: str = '무제한'):
    """
    RS 요금제 판별: 데이터 표기 + 통화 조건 조합으로 판별
    voice: '무제한' | '100분' | '300분' 등
    하위 호환: voice 미입력 시 데이터만으로 판별 (기존 동작 유지)
    v1.3: Mbps 소수점 정규화 적용 (1.024Mbps→1Mbps, 5.12Mbps→5Mbps)
    v1.4: segment도 함께 반환 (is_rs, segment) — 기존 bool만 받던 호출부는
          호환을 위해 is_rs만 써도 되도록 named tuple 대신 일반 tuple 유지,
          make_plan()에서 segment까지 사용
    """
    data = _normalize_mbps(data_label.strip())  # v1.3: 소수점 Mbps 정규화
    # 통화 값 정규화 (접두어 제거: '통화 무제한' → '무제한')
    v = voice.strip().replace('통화 ', '')
    is_rs = False
    # (data, voice) 조합으로 정확한 판별
    if (data, v) in RS_CRITERIA:
        is_rs = True
    # 하위 호환: voice 기본값('무제한')으로 체크
    elif v == '무제한' and data in RS_DATA_SET:
        is_rs = True

    if not is_rs:
        return False, None

    data_gb = parse_data_gb(data)
    segment = _resolve_rs_segment(data, v, data_gb)
    return True, segment

def normalize_data_label(raw: str) -> str:
    """사이트별 데이터 표기를 RS_DATA_SET 형식으로 최대한 정규화"""
    raw = raw.strip()
    # 이미 '월 XGB + YMbps' 형식이면 그대로
    if re.match(r'^월\s+[\d.]+GB', raw): return raw
    # 'XGB+YMbps' → '월 XGB + YMbps'
    m = re.match(r'^([\d.]+)\s*GB\s*\+\s*([\d.]+)\s*Mbps$', raw, re.IGNORECASE)
    if m: return f'월 {m.group(1)}GB + {m.group(2)}Mbps'
    return raw

def make_plan(
    source: str, plan_id: str, provider: str, name: str,
    data: str, voice: str, sms: str,
    network: str, network_generation: str,
    final_price: int, base_price: int = 0, discount_months: int = 0,
    subscribers: int = 0,
) -> dict:
    """표준 plan dict 생성"""
    data_gb = parse_data_gb(data)
    is_rs, rs_segment = classify_rs(data, voice)
    return {
        'plan_id':            plan_id,
        'source':             source,
        'provider':           provider,
        'name':               name,
        'data':               data,
        'data_gb':            data_gb,
        'voice':              voice,
        'sms':                sms,
        'network':            network,
        'network_generation': network_generation,
        'final_price':        final_price,
        'base_price':         base_price if base_price else final_price,
        'discount_months':    discount_months,
        'is_rs':              is_rs,
        'rs_segment':         rs_segment,   # RS인 경우 확정 구간, 아니면 None
        'is_rs2':             False,
        'subscribers':        subscribers,
        'scraped_at':         datetime.utcnow().isoformat(),
    }

# ── 공통 브라우저 설정 ────────────────────────────────────────────────────────

COMMON_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

BROWSER_ARGS = [
    '--no-sandbox', '--disable-setuid-sandbox',
    '--disable-dev-shm-usage', '--disable-gpu',
]

# ── 추상 기반 클래스 ──────────────────────────────────────────────────────────

class BaseScraper:
    SOURCE = 'unknown'

    def __init__(self, progress_callback=None):
        self.progress = progress_callback or print

    def scrape(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._scrape_async())
        finally:
            loop.close()

    async def _scrape_async(self):
        raise NotImplementedError