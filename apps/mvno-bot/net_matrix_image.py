"""순증 매트릭스 이미지 (일마감 텔레그램 첨부용)

[추가 20261104] 실무 요청 - 텍스트 메시지에 對MNO/對MVNO 상세를 다 넣으면 너무 길어서,
상대사업자별 순증을 표 한 장(당일 + 월 누적)으로 만들어 사진으로 보냄.
표의 값 = 열(기준) 사업자가 행(상대)에게서 받은 건수 - 행 상대에게 준 건수.
ktoa_daily.matrix[도착지][출발지] 기준, 음수는 ▲.
"""
import html as _html
import os as _os

# [추가 20261104] Pretendard (SIL OFL) - 서버 기본 한글 글꼴이 투박하다는 피드백. 한자(對)는 Noto CJK로 대체 표시.
_FONT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'fonts', 'PretendardVariable.woff2')

NODES = [('SKT', 'S'), ('KT', 'K'), ('LGU', 'L'),
         ('MVNO_SKT', 'SM'), ('MVNO_KT', 'KM'), ('MVNO_LGU', 'LM')]
COL_LABEL = {'MVNO_SKT': 'S-MVNO', 'MVNO_KT': 'K-MVNO', 'MVNO_LGU': 'L-MVNO',
             'SKT': 'SKT', 'KT': 'KT', 'LGU': 'LGU+'}
ROW_LABEL = {'SKT': '對SKT', 'KT': '對KT', 'LGU': '對LGU+',
             'MVNO_SKT': '對S-MVNO', 'MVNO_KT': '對K-MVNO', 'MVNO_LGU': '對L-MVNO'}
MNO = ['SKT', 'KT', 'LGU']
MVNO = ['MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']
COLS = MVNO + MNO


def _pair(m: dict, base: str, other: str) -> int:
    return ((m.get(base) or {}).get(other, 0) or 0) - ((m.get(other) or {}).get(base, 0) or 0)


def _fmt(v, same=False):
    if same:
        return '<td class="na">-</td>'
    cls = 'pos' if v > 0 else ('neg' if v < 0 else 'zero')
    txt = f'+{v:,}' if v >= 0 else f'▲{abs(v):,}'
    return f'<td class="{cls}">{txt}</td>'


def _table(m: dict, title: str) -> str:
    head = ''.join(f'<th>{COL_LABEL[c]}</th>' for c in COLS)
    rows = []
    for grp, sub in ((MNO, 'MNO계'), (MVNO, 'MVNO계')):
        for r in grp:
            rows.append(f'<tr><th class="rl">{ROW_LABEL[r]}</th>'
                        + ''.join(_fmt(_pair(m, c, r), same=(c == r)) for c in COLS) + '</tr>')
        rows.append(f'<tr class="sub{" mno-end" if sub == "MNO계" else ""}"><th class="rl">' + sub + '</th>'
                    + ''.join(_fmt(sum(_pair(m, c, r) for r in grp if r != c)) for c in COLS) + '</tr>')
    rows.append('<tr class="tot"><th class="rl">합계</th>'
                + ''.join(_fmt(sum(_pair(m, c, r) for r in MNO + MVNO if r != c)) for c in COLS) + '</tr>')
    return (f'<div class="card"><div class="ttl">{_html.escape(title)}</div>'
            f'<table><thead><tr><th class="rl">구분</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


PAGE_WIDTH = 500  # CSS px - 폰 화면 폭에 맞춤 (기존 760은 폰에서 확대해야 읽혔음)


def build_html(day_matrix: dict, cum_matrix: dict, date_label: str, cum_label: str,
               width: int = PAGE_WIDTH) -> str:
    parts = [_table(day_matrix, f'순증 매트릭스 [당일] {date_label}')]
    if cum_matrix:
        parts.append(_table(cum_matrix, f'순증 매트릭스 [{cum_label}]'))
    font_face = (f'@font-face{{font-family:"Pretendard";src:url("file://{_FONT}") format("woff2");'
                 f'font-weight:100 900}}') if _os.path.exists(_FONT) else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{font_face}
body{{margin:0;padding:8px;background:#f4f6f5;font-family:"Pretendard","Noto Sans CJK KR","Noto Sans KR","WenQuanYi Zen Hei","NanumGothic",sans-serif;color:#1f2a24;width:{width}px;box-sizing:border-box}}
.card{{background:#fff;border-radius:10px;padding:10px 8px 6px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.ttl{{font-weight:700;font-size:16px;margin:0 0 4px 4px}}
table{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
th,td{{padding:5px 4px;text-align:right;white-space:nowrap}}
thead th{{font-size:13.5px;color:#3d4a43;font-weight:700;border-bottom:2px solid #d5ddd8}}
th.rl{{text-align:left;font-weight:500;color:#2c3a32}}
tbody tr{{border-bottom:1px solid #eef1ef}}
tr.sub{{background:#e9f2ec}} tr.sub th.rl{{font-weight:700}}
tr.tot{{background:#1f4d36;color:#fff}} tr.tot th.rl{{color:#fff;font-weight:700}}
td.pos{{color:#1e7a47}} td.neg{{color:#c0392b}} td.zero,td.na{{color:#9aa59f}}
tr.tot td.pos{{color:#a8f0c6}} tr.tot td.neg{{color:#ffb3a8}}
td:nth-child(5){{border-left:2px solid #d5ddd8}} th:nth-child(5){{border-left:2px solid #d5ddd8}}
td:nth-child(2),th:nth-child(2){{border-left:2px solid #d5ddd8}}
thead tr{{border-bottom:2px solid #d5ddd8}}
tr.mno-end{{border-bottom:2px solid #d5ddd8}}
</style></head><body>{"".join(parts)}</body></html>'''


def render_png(html_text: str, out_path: str, width: int = PAGE_WIDTH) -> str:
    """headless Chromium으로 HTML → PNG (운영 이미지의 chromium/chromedriver 사용).
    [수정 20261104] 창 크기로 맞추면 브라우저 테두리만큼 아래가 잘려 '계·합계' 줄이 빠졌음 →
    CDP로 뷰포트를 내용 크기에 정확히 맞춘 뒤 캡처(2배 해상도)."""
    import os, tempfile
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_text)
        src = f.name
    opts = Options()
    for a in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
              f'--window-size={width},2000', '--hide-scrollbars'):
        opts.add_argument(a)
    if os.environ.get('CHROME_BIN'):
        opts.binary_location = os.environ['CHROME_BIN']
    d = webdriver.Chrome(options=opts)
    try:
        d.get('file://' + src)
        import time as _t
        for _ in range(30):  # 글꼴 로딩 대기 (최대 3초)
            if d.execute_script('return document.fonts.status') == 'loaded':
                break
            _t.sleep(0.1)
        h = int(d.execute_script('return Math.ceil(document.body.getBoundingClientRect().height)'))
        d.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',
                          {'width': width, 'height': h, 'deviceScaleFactor': 2, 'mobile': False})
        import base64
        shot = d.execute_cdp_cmd('Page.captureScreenshot',
                                 {'format': 'png', 'captureBeyondViewport': True,
                                  'clip': {'x': 0, 'y': 0, 'width': width, 'height': h, 'scale': 1}})
        with open(out_path, 'wb') as f:
            f.write(base64.b64decode(shot['data']))
    finally:
        d.quit()
        os.unlink(src)
    return out_path
