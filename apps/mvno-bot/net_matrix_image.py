"""순증 매트릭스 이미지 (일마감 텔레그램 첨부용)

[추가 20261104] 실무 요청 - 텍스트 메시지에 對MNO/對MVNO 상세를 다 넣으면 너무 길어서,
상대사업자별 순증을 표 한 장(당일 + 월 누적)으로 만들어 사진으로 보냄.
표의 값 = 열(기준) 사업자가 행(상대)에게서 받은 건수 - 행 상대에게 준 건수.
ktoa_daily.matrix[도착지][출발지] 기준, 음수는 ▲.
"""
import html as _html

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
        rows.append('<tr class="sub"><th class="rl">' + sub + '</th>'
                    + ''.join(_fmt(sum(_pair(m, c, r) for r in grp if r != c)) for c in COLS) + '</tr>')
    rows.append('<tr class="tot"><th class="rl">합계</th>'
                + ''.join(_fmt(sum(_pair(m, c, r) for r in MNO + MVNO if r != c)) for c in COLS) + '</tr>')
    return (f'<div class="card"><div class="ttl">{_html.escape(title)}</div>'
            f'<table><thead><tr><th class="rl">상대 \\ 기준</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def build_html(day_matrix: dict, cum_matrix: dict, date_label: str, cum_label: str) -> str:
    parts = [_table(day_matrix, f'순증 매트릭스 [당일] {date_label}')]
    if cum_matrix:
        parts.append(_table(cum_matrix, f'순증 매트릭스 [{cum_label}]'))
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:16px;background:#f4f6f5;font-family:"NanumGothic","Noto Sans CJK KR","WenQuanYi Zen Hei",sans-serif;color:#1f2a24}}
.card{{background:#fff;border-radius:14px;padding:14px 16px 10px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.ttl{{font-weight:700;font-size:17px;margin:0 0 4px}}
.note{{font-size:11px;color:#7a857f;margin:0 0 8px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{padding:6px 10px;text-align:right;white-space:nowrap}}
thead th{{font-size:12px;color:#5d6b63;font-weight:600;border-bottom:1px solid #e3e8e5}}
th.rl{{text-align:left;font-weight:500;color:#2c3a32}}
tbody tr{{border-bottom:1px solid #eef1ef}}
tr.sub{{background:#e9f2ec}} tr.sub th.rl{{font-weight:700}}
tr.tot{{background:#1f4d36;color:#fff}} tr.tot th.rl{{color:#fff;font-weight:700}}
td.pos{{color:#1e7a47}} td.neg{{color:#c0392b}} td.zero,td.na{{color:#9aa59f}}
tr.tot td.pos{{color:#a8f0c6}} tr.tot td.neg{{color:#ffb3a8}}
td:nth-child(5){{border-left:2px solid #d5ddd8}} th:nth-child(5){{border-left:2px solid #d5ddd8}}
</style></head><body>{"".join(parts)}
<div class="note">값 = 열(기준) 사업자가 행(상대)에게서 받은 건수 − 준 건수. 음수는 ▲. 출처: KTOA 번호이동 경로표</div>
</body></html>'''


def render_png(html_text: str, out_path: str, width: int = 760) -> str:
    """headless Chromium으로 HTML → PNG (운영 이미지의 chromium/chromedriver 사용)."""
    import os, tempfile
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_text)
        src = f.name
    opts = Options()
    for a in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
              f'--window-size={width},1600', '--force-device-scale-factor=2', '--hide-scrollbars'):
        opts.add_argument(a)
    if os.environ.get('CHROME_BIN'):
        opts.binary_location = os.environ['CHROME_BIN']
    d = webdriver.Chrome(options=opts)
    try:
        d.get('file://' + src)
        h = d.execute_script('return document.body.scrollHeight')
        d.set_window_size(width, h + 20)
        d.save_screenshot(out_path)
    finally:
        d.quit()
        os.unlink(src)
    return out_path
