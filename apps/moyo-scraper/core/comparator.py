import yaml
import os

class Comparator:
    def __init__(self):
        self.load_config()
        self.segments = {
            '7G+':     (7,    10),
            '10G+':    (10,   11),
            '11G+':    (11,   15),
            '15G+100': (15,   15.1),
            '15G+300': (15.1, 71),
            '100G+':   (100,  999),
        }

    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'sites.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.our_plans         = config.get('our_company', {}).get('plans', [])
                self.alert_thresholds  = config.get('alert_thresholds', {'price_difference': 1000})
        except:
            self.our_plans        = []
            self.alert_thresholds = {'price_difference': 1000}

    def _get_min_price(self, plans, network):
        # 3,000원 미만은 프로모션 특가(100원 등) 제외
        prices = [p['final_price'] for p in plans
                  if p.get('network') == network and p.get('final_price', 0) >= 3000]
        return min(prices) if prices else 0

    def get_segment_min_prices(self, plans, rs_only=None):
        """
        rs_only=None  → 전체
        rs_only=True  → RS 요금제만
        rs_only=False → RM 요금제만
        """
        if rs_only is True:
            plans = [p for p in plans if p.get('is_rs', False)]
        elif rs_only is False:
            plans = [p for p in plans if not p.get('is_rs', False)]

        summary = {}
        for seg, (lo, hi) in self.segments.items():
            seg_plans = [p for p in plans if lo <= p.get('data_gb', 0) < hi]
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
        plans = [copy.copy(p) for p in plans]

        # 1. segment 태깅
        for p in plans:
            gb  = p.get('data_gb', 0)
            seg = None
            for name, (lo, hi) in self.segments.items():
                if lo <= gb < hi:
                    seg = name
                    break
            p['segment'] = seg or ''

        # 2. 망+구간+타입별 최저가 계산
        from collections import defaultdict
        min_rs = defaultdict(lambda: float('inf'))  # key: (segment, network)
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
                    alerts.append({'message': f"⚠️ {our_plan['name']}: {cheapest['display_name']} 대비 {diff:,}원 비쌈"})
        return alerts