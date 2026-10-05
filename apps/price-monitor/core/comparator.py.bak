"""
comparator.py  v2.2
─────────────────────────────────────────────────────────────────────────────
v2.0 변경:
  - RS 요금제의 segment를 scraper에서 넘어온 rs_segment 필드 우선 사용
    · is_rs=True & rs_segment 있음 → rs_segment 사용 (룰 기반 확정 구간)
    · is_rs=True & rs_segment 없음 (badge만) → 기존 data_gb 기반 구간
    · is_rs=False (RM) → 기존 data_gb 기반 구간
  - segments 정의에 15G+100 / 15G+300 구간 분리 유지

v2.1 변경 / 2026-03-24:
  - _resolve_segment(): RS 요금제 구간 판별 시 통화 조건 반영
    · 15G+100: 월 15GB + 3Mbps + 통화 100분
    · 15G+300: 월 15GB + 3Mbps + 통화 300분
    · 그 외 RS: data_gb 기반 구간 (단, 15G+100/300 혼입 방지)
  - SEGMENT_RANGES 15G+100/300 범위 축소 → data_gb 15~15.1 only
    (31GB, 50GB 등이 15G+300으로 잘못 분류되는 문제 수정)
─────────────────────────────────────────────────────────────────────────────
"""

import yaml
import os


# ── 구간 정의 (data_gb 기반 fallback용) ──────────────────────────────────────
# RS 요금제는 _resolve_segment()에서 통화 조건 포함 판별
# RM 요금제는 data_gb 기반 구간 사용
SEGMENT_RANGES = {
    '7G+':     (6,    10),    # 6GB 이상 10GB 미만
    '10G+':    (10,   11),
    '11G+':    (11,   15),
    '15G+100': (15,   15.1),  # RS 통화100분 전용 (data_gb fallback용)
    '15G+300': (15.1, 16),    # RS 통화300분 전용 (15.1~16GB only, 31GB/50GB 혼입 방지)
    '100G+':   (16,   9999),  # 16GB 이상
}

# RS 15G+100/300 구간 판별용 (data+voice 조합)
RS_15G_SEGMENTS = {
    ('월 15GB + 3Mbps', '100분'):  '15G+100',
    ('월 15GB + 3Mbps', '통화 100분'): '15G+100',
    ('월 15GB + 3Mbps', '300분'):  '15G+300',
    ('월 15GB + 3Mbps', '통화 300분'): '15G+300',
    ('월 15GB + 3Mbps', '무제한'): '15G+300',   # 통화 무제한이면 15G+300
    ('월 15GB + 3Mbps', '통화 무제한'): '15G+300',
}


def _gb_to_segment(data_gb: float) -> str:
    """data_gb 값으로 구간 반환 (fallback)"""
    for seg, (lo, hi) in SEGMENT_RANGES.items():
        if lo <= data_gb < hi:
            return seg
    return ''


class Comparator:
    def __init__(self):
        self.load_config()

    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'sites.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.our_plans        = config.get('our_company', {}).get('plans', [])
                self.alert_thresholds = config.get('alert_thresholds', {'price_difference': 1000})
        except Exception:
            self.our_plans        = []
            self.alert_thresholds = {'price_difference': 1000}

    # ── segment 결정 ────────────────────────────────────────────────────────
    def _resolve_segment(self, plan: dict) -> str:
        """
        RS 요금제: 통화 조건 포함 정확한 구간 판별
          1) rs_segment 필드 있으면 우선 사용
          2) 15GB 구간은 data+voice 조합으로 15G+100/300 분리
          3) 그 외 data_gb 기반 fallback
        RM 요금제: data_gb 기반 fallback
        """
        if plan.get('is_rs'):
            # rs_segment 필드 우선
            if plan.get('rs_segment'):
                return plan['rs_segment']
            # 15GB 구간 통화 조건으로 정확히 분리
            data  = plan.get('data', '').strip()
            voice = plan.get('voice', '').strip()
            seg_key = (data, voice)
            if seg_key in RS_15G_SEGMENTS:
                return RS_15G_SEGMENTS[seg_key]
        return _gb_to_segment(plan.get('data_gb', 0))

    # ── 최저가 계산 ──────────────────────────────────────────────────────────
    def _get_min_price(self, plans, network):
        prices = [p['final_price'] for p in plans
                  if p.get('network') == network and p.get('final_price', 0) > 0]
        return min(prices) if prices else 0

    def get_segment_min_prices(self, plans, rs_only=None):
        """
        rs_only=None  → 전체
        rs_only=True  → RS 요금제만
        rs_only=False → RM 요금제만
        """
        if rs_only is True:
            filtered = [p for p in plans if p.get('is_rs', False)]
        elif rs_only is False:
            filtered = [p for p in plans if not p.get('is_rs', False)]
        else:
            filtered = plans

        # segment 임시 계산 (태깅 전 호출 시 대비)
        summary = {}
        all_segs = list(SEGMENT_RANGES.keys())
        for seg in all_segs:
            seg_plans = [p for p in filtered if self._resolve_segment(p) == seg]
            summary[seg] = {
                'SKT':  self._get_min_price(seg_plans, 'SKT'),
                'KT':   self._get_min_price(seg_plans, 'KT'),
                'LGU+': self._get_min_price(seg_plans, 'LGU+'),
            }
        return summary

    def analyze_changes(self, current_summary, prev_summary):
        changes = {}
        if not prev_summary:
            return changes
        for seg, networks in current_summary.items():
            changes[seg] = {}
            for net, price in networks.items():
                prev_price = prev_summary.get(seg, {}).get(net, 0)
                changes[seg][net] = (price - prev_price) if prev_price > 0 and price > 0 else 0
        return changes

    def tag_plans_with_lowest(self, plans):
        """
        각 요금제에 segment / is_lowest_rs / is_lowest_rm 필드 추가.
        원본 리스트를 수정하지 않고 새 리스트 반환.
        """
        import copy
        from collections import defaultdict

        plans = [copy.copy(p) for p in plans]

        # 1. segment 태깅
        for p in plans:
            p['segment'] = self._resolve_segment(p)

        # 2. 망+구간+타입별 최저가 계산
        min_rs = defaultdict(lambda: float('inf'))
        min_rm = defaultdict(lambda: float('inf'))

        for p in plans:
            seg = p.get('segment', '')
            net = p.get('network', '')
            prc = p.get('final_price', 0)
            if not seg or prc <= 0:
                continue
            key = (seg, net)
            if p.get('is_rs'):
                if prc < min_rs[key]: min_rs[key] = prc
            else:
                if prc < min_rm[key]: min_rm[key] = prc

        # 3. 최저가 여부 태깅
        for p in plans:
            seg = p.get('segment', '')
            net = p.get('network', '')
            prc = p.get('final_price', 0)
            key = (seg, net)
            if p.get('is_rs'):
                p['is_lowest_rs'] = (prc == min_rs[key]) if min_rs[key] != float('inf') else False
                p['is_lowest_rm'] = False
            else:
                p['is_lowest_rm'] = (prc == min_rm[key]) if min_rm[key] != float('inf') else False
                p['is_lowest_rs'] = False

        return plans

    def analyze_competitiveness(self, competitor_plans):
        alerts = []
        for our_plan in self.our_plans:
            our_data  = our_plan['data_gb']
            our_price = our_plan['final_price']
            comps = [p for p in competitor_plans
                     if p.get('data_gb') == our_data and p.get('is_competitor')]
            if comps:
                cheapest = min(comps, key=lambda x: x['final_price'])
                diff = our_price - cheapest['final_price']
                if diff > self.alert_thresholds['price_difference']:
                    alerts.append({
                        'message': f"⚠️ {our_plan['name']}: {cheapest['display_name']} 대비 {diff:,}원 비쌈"
                    })
        return alerts