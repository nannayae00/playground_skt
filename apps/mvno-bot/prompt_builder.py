#!/usr/bin/env python3
"""
본 코드 미사용 변경 (260409)

프롬프트 생성기 (Prompt Builder)
집계 타입과 비교 타입에 따라 최적화된 프롬프트 생성

주요 기능:
1. 집계 타입별 설명 추가 (순기별/주차별/월별/연별)
2. 비교 타입별 분석 지시사항
3. 데이터 상세 정보 포맷팅
4. config.py 통합
"""

from typing import Dict, Any, List
from datetime import datetime
import json

from query_parser import QueryIntent
from data_aggregator import AggregatedData


class PromptBuilder:
    """프롬프트 생성기"""
    
    def __init__(self, config: Dict[str, str]):
        """
        Args:
            config: config.py에서 가져온 설정
                - DATA_STRUCTURE
                - MONTHLY_GOALS
                - KEY_FOCUS
                - GENERAL_RESPONSE_FORMAT
        """
        self.data_structure = config.get('DATA_STRUCTURE', '')
        self.monthly_goals = config.get('MONTHLY_GOALS', '')
        self.key_focus = config.get('KEY_FOCUS', '')
        self.response_format = config.get('GENERAL_RESPONSE_FORMAT', '')
    
    def build_prompt(
        self,
        aggregated: AggregatedData,
        intent: QueryIntent,
        feedbacks: str = ""
    ) -> str:
        """
        프롬프트 생성
        
        Args:
            aggregated: 집계된 데이터
            intent: 질문 의도
            feedbacks: 사용자 피드백 (선택)
        
        Returns:
            완성된 프롬프트
        """
        
        # 기본 구조
        prompt = f"""당신은 SK MVNO(SM) 실적 분석 전문가입니다.

{self.data_structure}

{self.monthly_goals}

{self.key_focus}

**사용자 질문:**
{intent.question}

"""
        
        # 데이터 없으면 안내
        if not aggregated.records:
            return self._build_no_data_prompt(intent)
        
        # 집계 타입별 설명 추가
        prompt += self._get_aggregation_explanation(aggregated.aggregation)
        
        # 비교 타입별 지시사항
        prompt += self._get_comparison_instruction(intent.comparison)
        
        # 데이터 상세
        prompt += self._format_data_details(aggregated, intent)
        
        # 통계 정보 (일별 데이터가 많을 때)
        if aggregated.aggregation == 'daily' and len(aggregated.records) > 10:
            prompt += self._get_statistics(aggregated.records)
        
        # 피드백 추가
        if feedbacks:
            prompt += f"""

**🔄 과거 사용자 피드백 (최근 10건):**
{feedbacks}

⚠️ 위 피드백을 적극 반영하세요:
- 긍정 피드백 → 계속 유지
- 부정 피드백 → 개선
- 제안사항 → 최대한 반영
"""
        
        # 답변 형식
        prompt += f"\n{self.response_format}"
        
        return prompt
    
    def _build_no_data_prompt(self, intent: QueryIntent) -> str:
        """데이터 없을 때 프롬프트"""
        
        prompt = f"""사용자가 다음 질문을 했습니다:
"{intent.question}"

하지만 해당 기간의 데이터가 없습니다.

**요청 기간:**
"""
        for period in intent.periods:
            prompt += f"- {period.description} ({period.start_date} ~ {period.end_date})\n"
        
        prompt += """

**답변 요청:**
데이터가 없다는 것을 친절하게 안내하고, 보유 데이터 범위를 알려주세요.
"""
        
        return prompt
    
    def _get_aggregation_explanation(self, aggregation: str) -> str:
        """집계 타입별 설명"""
        
        if aggregation == '10day':
            return """
**중요: 이것은 순기별 집계 데이터입니다.**
- 각 레코드 = 해당 순기의 실적 합계 (누적 차이값으로 계산)
- 1순기: 1~10일, 2순기: 11~20일, 3순기: 21~말일
- 예: 1순기 T Out 1,000건 = 1~10일 동안의 T Out 합계
- **반드시 "X순기" 형식으로 답변**
- 일별 데이터가 아니므로 "일별 실적" 언급 금지

"""
        
        elif aggregation == 'weekly':
            return """
**중요: 이것은 주차별 집계 데이터입니다.**
- 각 레코드 = 해당 주차의 실적 합계 (누적 차이값으로 계산)
- 1주차: 1~7일, 2주차: 8~14일, 3주차: 15~21일, 4주차: 22~말일
- 예: 1주차 T Out 1,000건 = 1~7일 동안의 T Out 합계
- **반드시 "X주차" 형식으로 답변**
- 일별 데이터가 아니므로 "일별 실적" 언급 금지

"""
        
        elif aggregation == 'monthly':
            return """
**중요: 이것은 각 월 마지막 영업일의 '누적' 데이터입니다.**
- 각 레코드 = 해당 월 전체 실적
- 예: 2025-01-31의 누적 T Out = 2025년 1월 전체 T Out
- 월별 비교 시 각 레코드를 독립된 월 실적으로 취급
- 일별 데이터가 아니므로 "일별 실적 비교" 금지
- 반드시 "X월(X/XX 기준)" 형식으로 답변

"""
        
        elif aggregation == 'yearly':
            return """
**중요: 이것은 각 연도 마지막 날의 '누적' 데이터입니다.**
- 각 레코드 = 해당 연도 전체 실적
- 예: 2025-12-31의 누적 순증 = 2025년 전체 순증
- 연도별 비교 시 각 레코드를 독립된 연도 실적으로 취급

"""
        
        else:  # daily
            return """
**이것은 일별 실적 데이터입니다.**
- 각 레코드 = 해당 날짜의 당일 실적
- 누적 데이터는 해당 월 1일부터의 누적

"""
    
    def _get_comparison_instruction(self, comparison: str) -> str:
        """비교 타입별 지시사항"""
        
        common_format = """
**답변 형식 (필수):**

1부. AI 분석 (■로 시작하는 bullet point)
- 핵심 인사이트 3~5개
- 구체적 숫자 포함
- 명사형 종결

2부. 세부 실적 표 (반드시 포함!)

[실적 상세]

■ 실적 (기간)

◎ 신규 누적
S X,XXX (XX.X%)
K X,XXX (XX.X%)
L X,XXX (XX.X%)
계 X,XXX

◎ MVNO_MNP_해지 누적
S XX.Xk (XX.X%)
K XX.Xk (XX.X%)
L XX.Xk (XX.X%)
계 XX.Xk

◎ 순증감 누적
S +X,XXX (XX.X%)
K +X,XXX (XX.X%)
L +X,XXX (XX.X%)
계 +X,XXX

◎ MNO Out 누적
S XX.Xk (XX.X%)
K XX.Xk (XX.X%)
L XX.Xk (XX.X%)
계 XX.Xk

**주의사항:**
- 1,000 이상은 천 단위로 표기 (예: 12.4k, 19.3천)
- 비율은 소수점 1자리까지
- 순증감은 +/- 부호 필수
- 각 섹션 사이 빈 줄 1개

"""
        
        if comparison == 'compare':
            return common_format + """
**분석 방식: 비교 분석**
- **답변 첫 문장에 반드시 분석 기간 명시**
- 각 기간의 실적을 명확히 구분하여 제시
- 차이점과 공통점 강조
- 구체적인 숫자로 비교
- 어느 기간이 더 좋았는지 명확히 결론
- **세부 실적은 각 기간별로 별도 표 작성**

"""
        
        elif comparison == 'trend':
            return common_format + """
**분석 방식: 트렌드 분석**
- **답변 첫 문장에 반드시 분석 기간 명시**
- 시간 흐름에 따른 변화 패턴 파악
- 증가/감소 추세 설명
- 특이 변곡점이 있다면 지적
- 향후 예상되는 방향 제시
- **세부 실적은 대표 기간만 선택하여 표 작성**

"""
        
        else:  # single
            return common_format + """
**분석 방식: 단일 기간 상세 분석**
- **답변 첫 문장에 반드시 분석 기간 명시**
- 해당 기간의 실적을 종합적으로 평가
- 목표 대비 달성도
- 경쟁사 대비 우위
- 개선이 필요한 부분 지적

"""
    
    def _format_data_details(self, aggregated: AggregatedData, intent: QueryIntent) -> str:
        """데이터 상세 정보 포맷팅"""
        
        records = aggregated.records
        
        # 데이터 범위 명시
        dates = [r.get('date') for r in records if r.get('date')]
        if dates:
            earliest = min(dates)
            latest = max(dates)
            data_range = f"\n**전체 데이터 범위: {earliest} ~ {latest} (총 {len(records)}건)**\n"
        else:
            data_range = f"\n**과거 데이터 (총 {len(records)}건):**\n"
        
        prompt = data_range
        
        # 집계 타입별 상세 출력
        if aggregated.aggregation == '10day':
            prompt += self._format_10day_details(records)
        
        elif aggregated.aggregation == 'weekly':
            prompt += self._format_weekly_details(records)
        
        elif aggregated.aggregation == 'monthly':
            prompt += self._format_monthly_details(records)
        
        elif aggregated.aggregation == 'yearly':
            prompt += self._format_yearly_details(records)
        
        else:  # daily
            prompt += self._format_daily_details(records)
        
        return prompt
    
    def _format_10day_details(self, records: List[Dict]) -> str:
        """순기별 상세"""
        
        prompt = "\n**각 순기 실적 상세 (해당 기간 합계):**\n"
        
        for i, record in enumerate(records[:10], 1):
            period_name = record.get('period_name', 'N/A')
            date = record.get('display_date', record.get('date', 'N/A'))
            data = record.get('data', {})
            
            prompt += f"{i}. {period_name} ({date} 기준)\n"
            
            def fmt_signed(v): return f"{v:+,}" if isinstance(v, (int, float)) else str(v)
            def fmt_unsigned(v): return f"{v:,}" if isinstance(v, (int, float)) else str(v)
            def total_str(d, key): 
                t = d.get('계', '')
                return f", 계: {fmt_unsigned(t)}" if isinstance(t, (int, float)) else ""
            
            if '누적_순증감' in data:
                growth = data['누적_순증감']
                s_val = growth.get('S', '데이터없음')
                k_val = growth.get('K', '데이터없음')
                l_val = growth.get('L', '데이터없음')
                prompt += f"   순증: S {fmt_signed(s_val)}, K {fmt_signed(k_val)}, L {fmt_signed(l_val)}{total_str(growth, '계')}\n"
            
            if '누적_신규' in data:
                new = data['누적_신규']
                s_val = new.get('S', '데이터없음')
                k_val = new.get('K', '데이터없음')
                l_val = new.get('L', '데이터없음')
                prompt += f"   신규: S {fmt_unsigned(s_val)}, K {fmt_unsigned(k_val)}, L {fmt_unsigned(l_val)}{total_str(new, '계')}\n"
            
            if '누적_MVNO_MNP_해지' in data:
                mnp = data['누적_MVNO_MNP_해지']
                s_val = mnp.get('S', '데이터없음')
                k_val = mnp.get('K', '데이터없음')
                l_val = mnp.get('L', '데이터없음')
                prompt += f"   MVNO MNP해지: S {fmt_unsigned(s_val)}, K {fmt_unsigned(k_val)}, L {fmt_unsigned(l_val)}{total_str(mnp, '계')}\n"
            
            if '누적_MNO_Out' in data:
                mno_out = data['누적_MNO_Out']
                s_val = mno_out.get('S', '데이터없음')
                k_val = mno_out.get('K', '데이터없음')
                l_val = mno_out.get('L', '데이터없음')
                prompt += f"   T Out: S {fmt_unsigned(s_val)}, K {fmt_unsigned(k_val)}, L {fmt_unsigned(l_val)}{total_str(mno_out, '계')}\n"
            
            prompt += "\n"
        
        return prompt
    
    def _format_weekly_details(self, records: List[Dict]) -> str:
        """주차별 상세"""
        
        prompt = "\n**각 주차 실적 상세 (해당 주 합계):**\n"
        
        for i, record in enumerate(records[:10], 1):
            period_name = record.get('period_name', 'N/A')
            date = record.get('display_date', record.get('date', 'N/A'))
            data = record.get('data', {})
            
            prompt += f"{i}. {period_name} ({date} 기준)\n"
            
            if '누적_순증감' in data:
                growth = data['누적_순증감']
                s_val = growth.get('S', '데이터없음')
                k_val = growth.get('K', '데이터없음')
                l_val = growth.get('L', '데이터없음')
                total_val = growth.get('계', '')
                s_fmt = f"{s_val:+,}" if isinstance(s_val, (int, float)) else s_val
                k_fmt = f"{k_val:+,}" if isinstance(k_val, (int, float)) else k_val
                l_fmt = f"{l_val:+,}" if isinstance(l_val, (int, float)) else l_val
                total_fmt = f", 계: {total_val:+,}" if isinstance(total_val, (int, float)) else ""
                prompt += f"   순증: S {s_fmt}, K {k_fmt}, L {l_fmt}{total_fmt}\n"
            
            if '누적_신규' in data:
                new = data['누적_신규']
                s_val = new.get('S', '데이터없음')
                k_val = new.get('K', '데이터없음')
                l_val = new.get('L', '데이터없음')
                total_val = new.get('계', '')
                s_fmt = f"{s_val:,}" if isinstance(s_val, (int, float)) else s_val
                k_fmt = f"{k_val:,}" if isinstance(k_val, (int, float)) else k_val
                l_fmt = f"{l_val:,}" if isinstance(l_val, (int, float)) else l_val
                total_fmt = f", 계: {total_val:,}" if isinstance(total_val, (int, float)) else ""
                prompt += f"   신규: S {s_fmt}, K {k_fmt}, L {l_fmt}{total_fmt}\n"
            
            if '누적_MVNO_MNP_해지' in data:
                mnp = data['누적_MVNO_MNP_해지']
                s_val = mnp.get('S', '데이터없음')
                k_val = mnp.get('K', '데이터없음')
                l_val = mnp.get('L', '데이터없음')
                total_val = mnp.get('계', '')
                s_fmt = f"{s_val:,}" if isinstance(s_val, (int, float)) else s_val
                k_fmt = f"{k_val:,}" if isinstance(k_val, (int, float)) else k_val
                l_fmt = f"{l_val:,}" if isinstance(l_val, (int, float)) else l_val
                total_fmt = f", 계: {total_val:,}" if isinstance(total_val, (int, float)) else ""
                prompt += f"   MVNO MNP해지: S {s_fmt}, K {k_fmt}, L {l_fmt}{total_fmt}\n"
            
            if '누적_MNO_Out' in data:
                mno_out = data['누적_MNO_Out']
                s_val = mno_out.get('S', '데이터없음')
                k_val = mno_out.get('K', '데이터없음')
                l_val = mno_out.get('L', '데이터없음')
                total_val = mno_out.get('계', '')
                s_fmt = f"{s_val:,}" if isinstance(s_val, (int, float)) else s_val
                k_fmt = f"{k_val:,}" if isinstance(k_val, (int, float)) else k_val
                l_fmt = f"{l_val:,}" if isinstance(l_val, (int, float)) else l_val
                total_fmt = f", 계: {total_val:,}" if isinstance(total_val, (int, float)) else ""
                prompt += f"   T Out: S {s_fmt}, K {k_fmt}, L {l_fmt}{total_fmt}\n"
            
            prompt += "\n"
        
        return prompt
    
    def _format_monthly_details(self, records: List[Dict]) -> str:
        """월별 상세"""
        
        prompt = "\n**각 월 실적 상세 (마지막 영업일 누적 기준):**\n"
        
        def fmt_signed(v): return f"{v:+,}" if isinstance(v, (int, float)) else str(v)
        def fmt_unsigned(v): return f"{v:,}" if isinstance(v, (int, float)) else str(v)
        def total_str(d):
            t = d.get('계', '')
            return f", 계: {fmt_unsigned(t)}" if isinstance(t, (int, float)) else ""
        
        for i, record in enumerate(records[:12], 1):
            date = record.get('date', 'N/A')
            data = record.get('data', {})
            year_month = date[:7]
            
            prompt += f"{i}. {year_month} ({date} 기준 누적)\n"
            
            if '누적_순증감' in data:
                growth = data['누적_순증감']
                prompt += f"   순증: S {fmt_signed(growth.get('S', '데이터없음'))}, K {fmt_signed(growth.get('K', '데이터없음'))}, L {fmt_signed(growth.get('L', '데이터없음'))}{total_str(growth)}\n"
            
            if '누적_신규' in data:
                new = data['누적_신규']
                prompt += f"   신규: S {fmt_unsigned(new.get('S', '데이터없음'))}, K {fmt_unsigned(new.get('K', '데이터없음'))}, L {fmt_unsigned(new.get('L', '데이터없음'))}{total_str(new)}\n"
            
            if '누적_MVNO_MNP_해지' in data:
                mnp = data['누적_MVNO_MNP_해지']
                prompt += f"   MVNO MNP해지: S {fmt_unsigned(mnp.get('S', '데이터없음'))}, K {fmt_unsigned(mnp.get('K', '데이터없음'))}, L {fmt_unsigned(mnp.get('L', '데이터없음'))}{total_str(mnp)}\n"
            
            if '누적_MNO_Out' in data:
                mno_out = data['누적_MNO_Out']
                prompt += f"   T Out: S {fmt_unsigned(mno_out.get('S', '데이터없음'))}, K {fmt_unsigned(mno_out.get('K', '데이터없음'))}, L {fmt_unsigned(mno_out.get('L', '데이터없음'))}{total_str(mno_out)}\n"
            
            prompt += "\n"
        
        return prompt
    
    def _format_yearly_details(self, records: List[Dict]) -> str:
        """연별 상세"""
        
        prompt = "\n**각 연도 실적 상세 (12/31 기준 누적):**\n"
        
        for i, record in enumerate(records, 1):
            year = record.get('year', 'N/A')
            date = record.get('date', 'N/A')
            data = record.get('data', {})
            
            prompt += f"{i}. {year}년 ({date} 기준 누적)\n"
            
            if '누적_순증감' in data:
                growth = data['누적_순증감']
                prompt += f"   순증: S {growth.get('S', 0):+,}, K {growth.get('K', 0):+,}, L {growth.get('L', 0):+,}"
            
            if '누적_MNO_Out' in data:
                mno_out = data['누적_MNO_Out']
                prompt += f" | T Out: S {mno_out.get('S', 0):,}, 계: {mno_out.get('계', 0):,}"
            
            if '누적_신규' in data:
                new = data['누적_신규']
                prompt += f" | 신규: S {new.get('S', 0):,}"
            
            prompt += "\n"
        
        return prompt
    
    def _format_daily_details(self, records: List[Dict]) -> str:
        """일별 상세 (최근 5일만)"""
        
        prompt = "\n**최근 5일 상세:**\n"
        
        for i, record in enumerate(records[:5], 1):
            date = record.get('date', 'N/A')
            data = record.get('data', {})
            weekday = record.get('weekday', '')
            day_type = record.get('day_type', '')
            
            prompt += f"{i}. {date} ({weekday}, {day_type})\n"
            
            if '당일_마감' in data:
                daily = data['당일_마감']
                total = daily.get('계', 1)
                s_share = (daily.get('S', 0) / total * 100) if total > 0 else 0
                prompt += f"   점유율: S {s_share:.1f}%"
            
            if '당일_순증감' in data:
                growth = data['당일_순증감']
                prompt += f" | 순증: S {growth.get('S', 0):+,}"
            
            if '당일_MVNO_MNP_해지' in data:
                mnp = data['당일_MVNO_MNP_해지']
                prompt += f" | MNP: S {mnp.get('S', 0):,}"
            
            if '당일_MNO_Out' in data:
                mno_out = data['당일_MNO_Out']
                prompt += f" | T Out: S {mno_out.get('S', 0):,}, 계: {mno_out.get('계', 0):,}"
            
            prompt += "\n"
        
        return prompt
    
    def _get_statistics(self, records: List[Dict]) -> str:
        """통계 정보 (일별 데이터용)"""
        
        try:
            s_shares = []
            s_growth = []
            
            for record in records:
                data = record.get('data', {})
                
                if '당일_마감' in data:
                    daily = data['당일_마감']
                    total = daily.get('계', 1)
                    if total > 0:
                        s_share = (daily.get('S', 0) / total * 100)
                        s_shares.append({'date': record.get('date'), 'share': s_share})
                
                if '당일_순증감' in data:
                    growth = data['당일_순증감']
                    s_growth.append({'date': record.get('date'), 'value': growth.get('S', 0)})
            
            prompt = ""
            
            if s_shares:
                avg_share = sum(x['share'] for x in s_shares) / len(s_shares)
                max_share = max(s_shares, key=lambda x: x['share'])
                min_share = min(s_shares, key=lambda x: x['share'])
                
                prompt += f"\n**SM 점유율 통계:**\n"
                prompt += f"- 평균: {avg_share:.1f}%\n"
                prompt += f"- 최고: {max_share['share']:.1f}% ({max_share['date']})\n"
                prompt += f"- 최저: {min_share['share']:.1f}% ({min_share['date']})\n"
            
            if s_growth:
                avg_growth = sum(x['value'] for x in s_growth) / len(s_growth)
                max_growth = max(s_growth, key=lambda x: x['value'])
                min_growth = min(s_growth, key=lambda x: x['value'])
                
                prompt += f"\n**SM 순증감 통계:**\n"
                prompt += f"- 평균: {avg_growth:+.0f}\n"
                prompt += f"- 최고: {max_growth['value']:+,} ({max_growth['date']})\n"
                prompt += f"- 최저: {min_growth['value']:+,} ({min_growth['date']})\n"
            
            return prompt
        
        except Exception as e:
            print(f"통계 계산 실패: {e}")
            return ""


# 테스트
if __name__ == "__main__":
    from query_parser import QueryParser
    from data_aggregator import DataAggregator
    from datetime import date
    
    # 샘플 config
    sample_config = {
        'DATA_STRUCTURE': '**데이터 구조:** ...',
        'MONTHLY_GOALS': '**2월 목표:** ...',
        'KEY_FOCUS': '**주안점:** ...',
        'GENERAL_RESPONSE_FORMAT': '**답변 형식:** ...'
    }
    
    # 샘플 데이터
    sample_data = []
    for day in range(1, 11):
        sample_data.append({
            'date': f'2026-01-{day:02d}',
            'year': 2026,
            'month': 1,
            'day': day,
            'data': {
                '누적_순증감': {'S': day * 100, 'K': day * 80, 'L': day * 60},
            }
        })
    
    # 질문 파싱 → 집계 → 프롬프트 생성
    parser = QueryParser(base_date=date(2026, 2, 9))
    intent = parser.parse("1월 순기별 실적은?")
    
    aggregator = DataAggregator(sample_data)
    aggregated = aggregator.aggregate(intent)
    
    builder = PromptBuilder(sample_config)
    prompt = builder.build_prompt(aggregated, intent)
    
    print("=" * 60)
    print(prompt)