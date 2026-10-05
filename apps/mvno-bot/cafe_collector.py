"""
후불유심정책 계열 네이버카페 게시글 수집기 - 멀티소스

지원 소스 (SOURCES 딕셔너리):
  busung : [부성] 후불유심정책 카페(30984571) - 통신사별 정책표 "이미지"를 Gemini Vision으로
           읽어서 7GB/11GB 내국인 MNP 최고가를 직접 추출하는 방식 (mode='image')
  vision : [비전] 청춘모바일 카페(31131498) - 게시글 "본문 텍스트"에 이미 통신사별
           "MNP 최대 N만원!" 대표가격이 적혀있어서 그걸 그대로 파싱하는 방식
           (mode='body_price', 이미지 재추출 안 함 - 더 단순하고 오류 가능성 낮음)

흐름 (소스 공통):
  1) 목록 API(cafe-boardlist-api, 로그인 불필요)로 최신 글 감지 -> 새 글이면 처리
  2) 게시글 상세는 로그인이 필요해서 Selenium(+네이버 세션 쿠키)으로 ca-fe 경로를 직접 로드
     - 주의: /f-e/... 경로로 접속하면 React 쉘이 뜨고 실제 콘텐츠는 렌더링되지 않는다(원인 불명).
       반드시 /ca-fe/... 경로(구버전 iframe 렌더러)로 접속해야 본문/첨부파일이 나온다.
  3) mode='image': 첨부이미지를 Gemini Vision으로 파싱해 7G/11G 최고가 추출
     mode='body_price': 본문의 "《주력 단가》" 섹션을 정규식으로 파싱
  4) 메시지 포맷팅 후 Firestore에 저장 + 텔레그램(메시지+첨부이미지) 전송

네이버 세션 쿠키(NID_AUT, NID_SES)는 로그인 자격증명이라 Firestore가 아니라
Secret Manager(시크릿명: naver-cafe-cookies, JSON 문자열 {"NID_AUT":...,"NID_SES":...})에
저장한다. 이 프로젝트의 다른 비밀값(telegram-token, gmail-app-password 등)과 동일한 패턴.
(두 소스 모두 같은 네이버 계정 세션을 공유해서 쓴다 - 카페만 다를 뿐 로그인은 하나)

Firestore 레이아웃 (database=mvno-data), 소스별로 컬렉션 분리(article_id가 카페마다 별개라서 충돌 방지):
  cafe_collector_config/{state_doc}              { last_article_id }
  offline_policy_busung/{YYYY-MM-DD}             { article_id, subject, writer, write_date,
  offline_policy_vision/{YYYY-MM-DD}               body_text, images, prices_by_label,
                                                    formatted_message, telegram_sent, created_at }
  (문서ID는 게시일 날짜 - article_id는 필드로만 남기고 조회는 날짜 기준이 더 알아보기 쉽다는
   지적으로 20260923 변경. 같은 날 수정글이 다시 오면 그 날짜 문서를 덮어씀)
"""
import os
import re
import json
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

SOURCES = {
    'busung': {
        'cafe_id': '30984571',
        'menu_id': '10',
        'msg_prefix': '[부성]',
        'mode': 'image',
        'row_order': ['텔링크', 'KTM', '스카이', '유모비', '헬로'],
        # 첨부파일명(확장자 제외) -> 메시지 양식 라벨
        # [검증 20260922] 실무자 예시 메시지와 실제 첨부이미지를 대조해 확인한 매핑
        'filename_to_label': {
            'KTM': 'KTM', '세븐': '텔링크', '스카이': '스카이',
            '유모비': '유모비', '헬로': '헬로', '이야기후불': '이야기후불',
        },
        # 본문 "N. 통신사명 (...)" 섹션 헤더 -> 메시지 양식 라벨
        'body_label_to_msg_label': {
            'KTM': 'KTM', 'LG유모비': '유모비', '헬로': '헬로',
            'KT스카이': '스카이', 'SK세븐': '텔링크', '이야기후불': '이야기후불',
        },
        'firestore_collection': 'offline_policy_busung',
        'state_doc': 'state',
    },
    'vision': {
        'cafe_id': '31131498',
        'menu_id': '11',
        'msg_prefix': '[비전]',
        'mode': 'image_summary',  # 여러 통신사가 한 장에 합쳐진 "요약본" 이미지 1장에서 전부 추출
        # [수정 20260924] '세븐' -> '텔링크'로 통일 + 부성과 순서 동일하게 맞춤
        # (부성/비전 두 소스가 같은 사업자를 다른 라벨/순서로 표시하던 것을 통일하라는 지시)
        'row_order': ['텔링크', 'KTM', '스카이', '유모비', '헬로'],  # 조이텔은 표엔 안 냄 (사장님 지시)
        # 첨부 이미지 중 파일명에 이 문자열이 들어간 것만 사용 (요약본 1장만, 나머지 통신사별
        # 개별표/QR코드 등은 텔레그램 전송도 안 하고 추출도 안 함 - 20260923 사장님 지시)
        'image_filename_filter': '요약',
        # "요약본" 표 안 통신사 섹션 헤더 -> 메시지 양식 라벨
        # [검증 20260923] 실제 요약본 이미지 실측: "SK JOYTEL", "SK 7mobile", "KT M mobile",
        # "kt skylife", "LG U+ Hello mobile", "U+ U MOBILE"
        'carrier_header_to_label': {
            'SK JOYTEL': '조이텔', 'SK7mobile': '텔링크', 'SK 7mobile': '텔링크',
            'KT M mobile': 'KTM', 'KTM mobile': 'KTM',
            'kt skylife': '스카이', 'KT skylife': '스카이',
            'LG U+ Hello mobile': '헬로', 'LG U+ Hello Mobile': '헬로', 'Hello mobile': '헬로',
            'U+ U MOBILE': '유모비', 'U MOBILE': '유모비',
        },
        # 본문 "◆ 통신사명" 표기 -> 메시지 양식 라벨 (하이라이트 추출용, 가격추출과는 별개)
        # [검증 20260923] 987/983번 글 실측: "KT M", "LG 헬로", "LG 유모비", "SK세븐"
        # [수정 20260924] '세븐' -> '텔링크' 통일
        'body_label_to_msg_label': {
            'KT M': 'KTM', 'KTM': 'KTM',
            'KT스카이': '스카이', 'KT 스카이': '스카이',
            'SK세븐': '텔링크', 'SK 세븐': '텔링크',
            'LG유모비': '유모비', 'LG 유모비': '유모비',
            'LG헬로': '헬로', 'LG 헬로': '헬로',
            '조이텔': '조이텔',
        },
        'firestore_collection': 'offline_policy_vision',
        'state_doc': 'state_vision',
    },
}


# [추가 20260924] 부성/비전 두 카페가 같은 사업자를 서로 다른 약칭으로 부르는
# 문제(예: 부성="텔링크" vs 비전="세븐" - 둘 다 SK텔링크 세븐모바일) 때문에, 화면
# 표시용 짧은 라벨(row_order 등 기존 로직 전부 유지)과 별개로 DB엔 정식 사업자명을
# 남기기 위한 매핑. ktoa_mvno_operator_registry 실측 대조(S05="SK텔링크(재판매)",
# K20="KT엠모바일", K32="KT스카이라이프", L31="LG헬로비전") + 사장님 확인
# ("세븐모바일이 텔링크임 - 풀네임은 SK텔링크 세븐모바일")으로 확정.
# '유모비'(U+ U MOBILE)와 '이야기후불'은 레지스트리에 개별 코드가 없어(LGU+/통신사
# 자체 직영 서브브랜드로 추정) 확실치 않은 채로 표기 - 필요시 정정.
PROVIDER_CANONICAL_NAME = {
    '텔링크':    'SK텔링크(세븐모바일)',
    '세븐':      'SK텔링크(세븐모바일)',
    'KTM':       'KT엠모바일',
    '스카이':    'KT스카이라이프',
    '헬로':      'LG헬로비전(헬로모바일)',
    '유모비':    'LG유플러스 U모바일',   # [불확실] 레지스트리에 개별 코드 없음
    '조이텔':    'SK조이텔',            # vision 요약본 헤더 "SK JOYTEL" 근거
    '이야기후불': '이야기모바일',        # [불확실] 레지스트리에 개별 코드 없음
}


def _get_db():
    from google.cloud import firestore
    return firestore.Client(project='mvno-484509', database='mvno-data')


def _get_cookies():
    """Secret Manager의 naver-cafe-cookies 시크릿에서 세션 쿠키를 읽는다.
    (Firestore가 아님 - 로그인 자격증명은 이 프로젝트의 다른 비밀값들과 같은 방식으로 관리)"""
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    name = 'projects/mvno-484509/secrets/naver-cafe-cookies/versions/latest'
    resp = client.access_secret_version(request={'name': name})
    payload = json.loads(resp.payload.data.decode('utf-8'))
    nid_aut, nid_ses = payload.get('NID_AUT'), payload.get('NID_SES')
    if not nid_aut or not nid_ses:
        raise RuntimeError('naver-cafe-cookies 시크릿에 NID_AUT/NID_SES가 없습니다')
    return nid_aut, nid_ses


def fetch_latest_articles(source: dict, page_size: int = 15) -> list:
    """목록 API로 최신 글 목록 조회 (로그인 불필요, 공개 API)"""
    cafe_id, menu_id = source['cafe_id'], source['menu_id']
    list_api = f'https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{cafe_id}/menus/{menu_id}/articles'
    r = requests.get(
        list_api,
        params={'page': 1, 'pageSize': page_size, 'sortBy': 'TIME', 'viewType': 'L'},
        headers={'User-Agent': UA, 'Referer': f'https://cafe.naver.com/f-e/cafes/{cafe_id}/menus/{menu_id}'},
        timeout=15,
    )
    r.raise_for_status()
    items = r.json()['result']['articleList']
    out = []
    for it in items:
        a = it['item']
        out.append({
            'article_id': a['articleId'],
            'subject': a['subject'],
            'writer': a['writerInfo']['nickName'],
            'write_ts_ms': a['writeDateTimestamp'],
            'has_file': a.get('hasFile', False),
            'summary': a.get('summary', ''),
        })
    return out


def get_last_seen_article_id(source: dict) -> int:
    db = _get_db()
    doc = db.collection('cafe_collector_config').document(source['state_doc']).get()
    return (doc.to_dict() or {}).get('last_article_id', 0)


def set_last_seen_article_id(source: dict, article_id: int):
    db = _get_db()
    db.collection('cafe_collector_config').document(source['state_doc']).set(
        {'last_article_id': article_id, 'updated_at': datetime.now(KST)}, merge=True
    )


def _get_chrome_driver():
    """ktoa_scraper.py의 get_driver()와 동일한 옵션 (이 이미지엔 selenium+chromium만 있음,
    playwright는 안 씀). Cloud Run 이미지에 이미 apt로 설치된 /usr/bin/chromium 사용."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,1200")
    options.add_argument(f"user-agent={UA}")
    options.binary_location = os.environ.get('CHROME_BIN', '/usr/bin/chromium')
    return webdriver.Chrome(options=options)


def fetch_article_detail(source: dict, article_id: int, nid_aut: str, nid_ses: str) -> dict:
    """ca-fe(구버전) 경로를 열어 본문 텍스트 + 첨부이미지 URL 추출.
    [검증 20260922] /f-e/... 로 열면 내용이 비어서(원인: 클라이언트 하이드레이션 실패로 추정,
    봇탐지 아님) 반드시 /ca-fe/... 경로를 써야 한다."""
    import time
    cafe_id, menu_id = source['cafe_id'], source['menu_id']
    url = (f'https://cafe.naver.com/ca-fe/cafes/{cafe_id}/articles/{article_id}'
           f'?menuid={menu_id}&referrerAllArticles=false&fromNext=true')

    driver = _get_chrome_driver()
    try:
        # 쿠키는 해당 도메인에 먼저 진입한 뒤에만 설정 가능
        driver.get('https://cafe.naver.com/robots.txt')
        driver.add_cookie({'name': 'NID_AUT', 'value': nid_aut, 'domain': '.naver.com', 'path': '/'})
        driver.add_cookie({'name': 'NID_SES', 'value': nid_ses, 'domain': '.naver.com', 'path': '/'})

        driver.get(url)
        time.sleep(4)  # SPA 하이드레이션 대기 (networkidle 상당의 고정 대기)

        body_text = driver.execute_script('return document.body.innerText')
        img_urls = driver.execute_script(
            'return [...document.querySelectorAll("img")].map(e => e.src)'
            '.filter(s => s && (s.includes("cafeptthumb") || s.includes("phinf")))'
        )
    finally:
        driver.quit()

    # [검증 20260922] 로그인 세션이 만료되면 본문이 통째로 비고(사이드바 메뉴만 ~400자),
    # 첨부이미지도 0장으로 나온다 - 조용히 빈 결과를 내보내는 대신 명확히 실패시킨다.
    if len(body_text) < 600 or not img_urls:
        raise RuntimeError(
            f'게시글 본문을 제대로 못 읽었습니다(본문 {len(body_text)}자, 이미지 {len(img_urls)}장) - '
            f'네이버 세션 쿠키(naver-cafe-cookies)가 만료됐을 가능성이 높습니다'
        )

    filename_to_label = source.get('filename_to_label', {})
    images = []
    for u in img_urls:
        path = urllib.parse.urlparse(u).path
        fname = urllib.parse.unquote(os.path.basename(path))
        stem = os.path.splitext(fname)[0]
        label = filename_to_label.get(stem, stem)
        images.append({'carrier': label, 'filename': fname, 'url': u})

    return {'body_text': body_text, 'images': images}


def download_image(url: str) -> bytes:
    r = requests.get(url, headers={'User-Agent': UA}, timeout=20)
    r.raise_for_status()
    return r.content


def extract_prices_from_image(image_bytes: bytes) -> dict:
    """Gemini Vision으로 정책표 이미지에서 요금제별 데이터 제공량 + 4개 가격 컬럼을
    전부 뽑아서, 데이터 제공량이 7GB/11GB인 요금제 중 "내국인 MNP" 컬럼 최고가를 채택.
    (busung 소스 전용 - mode='image')

    [수정이력]
    - 20260923 1차: 요금제명에 "7GB"/"11GB" 문자열 포함 여부로 판단하던 것을
      데이터 컬럼 기준으로 변경 (이름과 실제 제공량이 다를 수 있다는 지적)
    - 20260923 2차: "내국인 MNP 하나만 골라서 알려줘" 방식이 내국인/외국인 컬럼을
      계속 헷갈려서(KTM 11G가 20만인데 19만으로 두 번 연속 잘못 나옴), 4개 가격
      컬럼(내국인/외국인 × 010신규/MNP)을 전부 이름표 붙여서 받아오고 "내국인 MNP"
      선택은 우리 코드에서 하도록 변경 - LLM이 표 안에서 값을 고르는 판단을 줄이고
      순수 전사(transcribe)만 시키는 게 더 안정적이라는 판단."""
    import google.generativeai as genai

    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = (
        '이 이미지는 통신사 요금제 정책표입니다. 표 오른쪽에 "내국인(또는 내국인 외국인비자포함)" '
        '섹션과 "외국인" 섹션이 나란히 붙어있고, 각 섹션 안에 "010신규"와 "MNP" 두 컬럼이 있어 '
        '총 4개의 가격 숫자(내국인_010신규, 내국인_MNP, 외국인_010신규, 외국인_MNP)가 한 행에 있습니다.\n'
        '각 요금제 행에 대해 아래 필드를 전부 채워서 JSON 배열로만 응답하세요. 판단하지 말고 '
        '표에 보이는 숫자를 그대로 각 필드에 옮겨 적으세요:\n'
        '- name: 요금제명\n'
        '- data_gb: "데이터"/"무료제공량" 컬럼의 기본 데이터 제공량 숫자만 '
        '(예: "11GB+일2GB"→11, "7GB+"→7, "100GB"→100, "2.2GB"→2.2)\n'
        '- domestic_new: 내국인 섹션의 "010신규" 컬럼 숫자\n'
        '- domestic_mnp: 내국인 섹션의 "MNP" 컬럼 숫자\n'
        '- foreign_new: 외국인 섹션의 "010신규" 컬럼 숫자\n'
        '- foreign_mnp: 외국인 섹션의 "MNP" 컬럼 숫자\n'
        '예: [{"name":"M 스페셜 7GB(밀리의서재)","data_gb":7,"domestic_new":140000,'
        '"domestic_mnp":180000,"foreign_new":140000,"foreign_mnp":180000}, ...] '
        '다른 설명 없이 JSON만 출력하세요.'
    )
    # [수정 20260923] 4개 컬럼 다 받게 바꾸니 응답이 길어져서 가끔 504 타임아웃 발생
    # (KTM처럼 행이 40개+인 표에서 확인) - 재시도 1회로는 부족해서 3회+간격으로 늘림
    # (request_options={'timeout':...}는 google-generativeai==0.3.2에서 미지원이라 뺌
    # - "Unknown field for GenerateContentRequest: request_options" 에러로 확인)
    import time
    last_err = None
    for attempt in range(3):
        try:
            resp = model.generate_content([prompt, {'mime_type': 'image/png', 'data': image_bytes}])
            text = resp.text.strip()
            text = re.sub(r'^```json\s*|\s*```$', '', text.strip())
            plans = json.loads(text)
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(5)
    else:
        raise last_err

    # [수정 20260923] 내국인 MNP가 없는(=외국인전용, "내국인 개통불가") 요금제만 있는
    # 구간은 예전엔 그냥 공백으로 나왔는데, 외국인 MNP라도 있으면 그걸로 채우라는 지시
    def max_price(gb):
        rows = [p for p in plans if isinstance(p.get('data_gb'), (int, float)) and p['data_gb'] == gb]
        dom = [p['domestic_mnp'] for p in rows if isinstance(p.get('domestic_mnp'), (int, float))]
        if dom:
            return max(dom)
        for_ = [p['foreign_mnp'] for p in rows if isinstance(p.get('foreign_mnp'), (int, float))]
        return max(for_) if for_ else None

    return {'seven': max_price(7), 'eleven': max_price(11), 'raw_plan_count': len(plans), 'plans': plans}


def extract_prices_from_summary_image(source: dict, image_bytes: bytes) -> dict:
    """vision 소스 전용 (mode='image_summary'). 여러 통신사가 한 장에 합쳐진 "요약본"
    이미지 1장에서 전체 통신사의 7GB/11GB 내국인 MNP 최고가를 한 번에 추출.
    busung의 extract_prices_from_image()와 로직은 같되(데이터컬럼 기준 매칭,
    내국인/외국인 컬럼 혼동 방지를 위해 4개 컬럼 전부 전사), 한 이미지에 여러 통신사
    섹션이 있어서 "carrier" 필드로 행을 구분해야 하는 점이 다름.
    반환: {msg_label: {'seven':, 'eleven':, 'raw_plan_count':, 'plans':[...]}, ...}"""
    import google.generativeai as genai
    import time

    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
    genai.configure(api_key=key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = (
        '이 이미지는 여러 통신사 요금제 정책표를 하나로 합친 "요약본"입니다. 표는 통신사별로 '
        '구분된 섹션(예: SK JOYTEL, SK 7mobile, KT M mobile, kt skylife, LG U+ Hello mobile, '
        'U+ U MOBILE 등)이 위아래로 이어져 있고, 각 섹션 오른쪽에 "내국인 정책(R/B)"과 '
        '"외국인 정책(R/B)" 두 블록이 나란히 있으며 각 블록 안에 "010(신규)"와 "MNP(번호이동)" '
        '두 컬럼이 있습니다.\n'
        '표에 있는 모든 요금제 행에 대해 아래 필드를 전부 채워서 JSON 배열로만 응답하세요. '
        '판단하지 말고 표에 보이는 값을 그대로 옮겨 적으세요 (내국인/외국인 헷갈리지 말 것 - '
        '두 블록 컬럼 순서가 같아서 헷갈리기 쉬우니 반드시 왼쪽=내국인, 오른쪽=외국인으로 정확히 구분):\n'
        '- carrier: 그 행이 속한 통신사 섹션 제목 (로고/헤더에 적힌 그대로, 예: "SK 7mobile")\n'
        '- name: 요금제명\n'
        '- data_gb: "기본 제공량"의 데이터 컬럼 숫자만 (예: "11GB+일2GB"→11, "7GB+5GB"→7)\n'
        '- domestic_mnp: 왼쪽 "내국인 정책" 블록의 "MNP(번호이동)" 컬럼 숫자. "내국인 개통불가"처럼 '
        '숫자가 없으면 null\n'
        '- foreign_mnp: 오른쪽 "외국인 정책" 블록의 "MNP(번호이동)" 컬럼 숫자\n'
        '예: [{"carrier":"SK 7mobile","name":"글로벌 300 (11GB+/통화맘껏)","data_gb":11,'
        '"domestic_mnp":150000,"foreign_mnp":150000}, ...] 다른 설명 없이 JSON만 출력하세요.'
    )
    last_err = None
    for attempt in range(3):
        try:
            resp = model.generate_content([prompt, {'mime_type': 'image/png', 'data': image_bytes}])
            text = resp.text.strip()
            text = re.sub(r'^```json\s*|\s*```$', '', text.strip())
            plans = json.loads(text)
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(5)
    else:
        raise last_err

    carrier_map = source.get('carrier_header_to_label', {})
    by_carrier = {}
    for p in plans:
        carrier_raw = (p.get('carrier') or '').strip()
        label = carrier_map.get(carrier_raw, carrier_raw)
        by_carrier.setdefault(label, []).append(p)

    # [수정 20260923] 내국인 MNP가 없는(=외국인전용, "내국인 개통불가") 요금제만 있는
    # 구간은 예전엔 그냥 공백으로 나왔는데, 외국인 MNP라도 있으면 그걸로 채우라는 지시
    result = {}
    for label, rows in by_carrier.items():
        def max_price(gb, rows=rows):
            gb_rows = [r for r in rows if isinstance(r.get('data_gb'), (int, float)) and r['data_gb'] == gb]
            dom = [r['domestic_mnp'] for r in gb_rows if isinstance(r.get('domestic_mnp'), (int, float))]
            if dom:
                return max(dom)
            for_ = [r['foreign_mnp'] for r in gb_rows if isinstance(r.get('foreign_mnp'), (int, float))]
            return max(for_) if for_ else None
        result[label] = {'seven': max_price(7), 'eleven': max_price(11),
                          'raw_plan_count': len(rows), 'plans': rows}
    return result


def extract_prices_from_body(source: dict, body_text: str) -> dict:
    """본문의 "《주력 단가》" 섹션에서 "◆ 통신사명 MNP 최대 N만원!" 패턴을 정규식으로 파싱.
    (vision 소스 전용 - mode='body_price', 이미지 재추출 없이 게시자가 이미 적어둔
    대표가격을 그대로 신뢰 - 20260923 사장님 지시로 이 방식 채택)"""
    # [수정 20260923] "《주력 단가》――――" 처럼 헤더 줄 끝에 구분선이 바로 붙어있어서
    # 예전 정규식(다음 "――"에서 멈춤)이 헤더 줄 자체에서 멈춰버려 내용을 못 뽑았음.
    # 헤더 뒤 구분선은 건너뛰고, "다음" 구분선(3개 이상 연속)에서 멈추도록 수정.
    m = re.search(r'《주력\s*단가》―*\s*(.*?)(?:―{3,}|$)', body_text, re.DOTALL)
    if not m:
        return {}
    section = m.group(1)
    label_map = source.get('body_label_to_msg_label', {})
    prices = {}
    for carrier_raw, price_str in re.findall(
        r'◆\s*([가-힣A-Za-z0-9 ]+?)\s*MNP\s*최대\s*([\d.]+)\s*만원', section
    ):
        label = label_map.get(carrier_raw.strip(), carrier_raw.strip())
        prices[label] = {'main': float(price_str) * 10000}
    return prices


def _fmt_man(price):
    if price is None:
        return ''
    man = price / 10000
    return f'{man:g}만'


def _disp_width(s: str) -> int:
    """한글/한자 등 '넓은' 글자는 화면에서 영문/숫자의 2배 폭을 차지한다.
    [수정 20260923] len()로만 패딩하면 텔링크/KTM처럼 한글-영문 라벨이 안 맞는다는
    지적을 받고, 실제 표시폭 기준 패딩으로 변경."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + ' ' * max(0, width - _disp_width(s))


def extract_highlights(source: dict, body_text: str) -> list:
    """변경사항 하이라이트 추출. 소스별로 본문 포맷이 달라서 mode에 따라 분기.
    반환: [(label, 변경문구), ...]

    busung(mode='image'): "N. 통신사명 (...)" 섹션별 "☞" 불릿, "정책 유지"는 제외
    vision(mode='body_price'): "《변동사항》" 섹션의 "◆ 통신사명" + "- " 불릿"""
    label_map = source.get('body_label_to_msg_label', {})

    if source['mode'] == 'image':
        pattern = re.compile(r'^\d+\.\s*(\S+)\s*\([^)]*\)\s*$', re.MULTILINE)
        matches = list(pattern.finditer(body_text))
        highlights = []
        for i, m in enumerate(matches):
            carrier_raw = m.group(1)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body_text)
            section = body_text[start:end]
            bullets = [ln.strip().lstrip('☞').strip() for ln in section.splitlines()
                       if ln.strip().startswith('☞')]
            changed = [b for b in bullets if b and b != '정책 유지']
            if changed:
                label = label_map.get(carrier_raw, carrier_raw)
                highlights.append((label, changed[0]))
        return highlights

    # mode == 'body_price'
    m = re.search(r'《변동사항》(.*?)(?:《|$)', body_text, re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    parts = re.split(r'◆\s*', section)
    highlights = []
    for part in parts[1:]:
        lines = [ln.strip() for ln in part.splitlines() if ln.strip()]
        if not lines:
            continue
        carrier_raw = lines[0]
        bullets = [ln.lstrip('- ').strip() for ln in lines[1:] if ln.strip().startswith('-')]
        if bullets:
            label = label_map.get(carrier_raw, carrier_raw)
            highlights.append((label, bullets[0]))
    return highlights


LABEL_WIDTH_ADJUST = {'KTM': -1, '헬로': 1}  # busung 라벨 실측 미세조정 (가변폭 글꼴)
HEADER_EXTRA_INDENT = 2


def _price_diff_lines_image(label: str, prev: dict, cur: dict) -> list:
    """7G/11G 가격이 이전 게시글 대비 바뀌었으면 "18.5만 → 20.7만 (+2.2만)" 형태로 반환"""
    p, c = prev.get(label, {}), cur.get(label, {})
    out = []
    for gb_name, key in (('7G', 'seven'), ('11G', 'eleven')):
        old, new = p.get(key), c.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != new:
            sign = '+' if new > old else '-'
            out.append(f'  {gb_name} {_fmt_man(old)} → {_fmt_man(new)} ({sign}{_fmt_man(abs(new - old))})')
    return out


def _price_diff_line_single(label: str, prev: dict, cur: dict) -> list:
    """단일 대표가격이 이전 게시글 대비 바뀌었으면 "15만 → 21만 (+6만)" 형태로 반환"""
    old = prev.get(label, {}).get('main')
    new = cur.get(label, {}).get('main')
    if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != new:
        sign = '+' if new > old else '-'
        return [f'  {_fmt_man(old)} → {_fmt_man(new)} ({sign}{_fmt_man(abs(new - old))})']
    return []


# 7G/11G 2컬럼 표를 쓰는 모드들 (이미지 기반 - busung은 통신사당 이미지 1장,
# vision은 여러 통신사가 합쳐진 요약본 이미지 1장, 추출 방식만 다르고 표 형태는 동일)
TWO_COLUMN_MODES = {'image', 'image_summary'}


def format_message(source: dict, round_no: str, write_date: datetime, prices_by_label: dict,
                    highlights: list = None, prev_prices_by_label: dict = None) -> str:
    row_order = source['row_order']
    mode = source['mode']
    two_col = mode in TWO_COLUMN_MODES
    diff_fn = _price_diff_lines_image if two_col else _price_diff_line_single

    lines = [
        source['msg_prefix'],
        f'{round_no}차 정책, {write_date.strftime("%y.%m.%d")}~ (게시 {write_date.strftime("%H:%M")})',
    ]
    for label, change_text in (highlights or []):
        lines.append(f'★ {label} {change_text}')
        lines.extend(diff_fn(label, prev_prices_by_label or {}, prices_by_label))

    label_width = max(_disp_width(l) for l in row_order) + 1

    if two_col:
        price_width = 7  # "18.5만" 기준 여유폭
        header = f"{_pad('', label_width + HEADER_EXTRA_INDENT)}  {_pad('7G', price_width)}| 11G"
        lines += ['', header, '-' * _disp_width(header)]
        for label in row_order:
            p = prices_by_label.get(label, {})
            seven = _fmt_man(p.get('seven'))
            eleven = _fmt_man(p.get('eleven'))
            w = label_width + LABEL_WIDTH_ADJUST.get(label, 0)
            lines.append(f'{_pad(label, w)}: {_pad(seven, price_width)}| {eleven}')
    else:
        lines += ['', '-' * (label_width + 10)]
        for label in row_order:
            val = prices_by_label.get(label, {}).get('main')
            lines.append(f'{_pad(label, label_width)}: {_fmt_man(val)}')

    return '\n'.join(lines)


def _extract_round_no(subject: str) -> str:
    m = re.search(r'(\d+)차', subject)
    return m.group(1) if m else '?'


def get_previous_prices_by_label(source: dict, before_article_id: int) -> dict:
    """이 글보다 article_id가 작은 것 중 가장 최근 게시글의 prices_by_label을 가져온다.
    (가격 변동폭 표시용 - 이전 게시글이 없으면 {} 반환, 변동폭 라인은 그냥 생략됨)"""
    from google.cloud import firestore
    db = _get_db()
    q = (db.collection(source['firestore_collection'])
           .where('article_id', '<', before_article_id)
           .order_by('article_id', direction=firestore.Query.DESCENDING)
           .limit(1))
    docs = list(q.stream())
    if not docs:
        return {}
    return (docs[0].to_dict() or {}).get('prices_by_label', {})


def process_new_article(source: dict, article: dict) -> dict:
    """새 글 하나를 통째로 처리: 상세수집 -> 가격추출(이미지 or 본문) -> 메시지포맷 -> DB저장"""
    article_id = article['article_id']
    nid_aut, nid_ses = _get_cookies()
    detail = fetch_article_detail(source, article_id, nid_aut, nid_ses)

    image_records = []       # DB 저장용 (bytes 제외)
    images_with_bytes = []   # 텔레그램 전송용 (bytes 포함, DB엔 안 넣음)

    # 파일명에 특정 문자열이 들어간 이미지만 쓰는 소스(vision의 "요약본" 등) - 나머지
    # 통신사별 개별표/QR코드 등은 추출도 텔레그램 전송도 안 함 (20260923 사장님 지시)
    name_filter = source.get('image_filename_filter')
    images = detail['images']
    if name_filter:
        images = [img for img in images if name_filter in img['filename']]

    # [수정 20260923] 게시글이 수정(edit)되면 같은 파일명의 이미지가 URL만 다르게(재업로드)
    # DOM에 중복으로 남아있는 경우가 있어("...수정1" 글에서 확인, 내용은 동일) 텔레그램에
    # 같은 사진이 2번 가는 문제 발생 - 파일명 기준으로 중복 제거(먼저 나온 것 = DOM 순서상
    # 최신 버전으로 간주하고 유지)
    seen_fnames = set()
    deduped = []
    for img in images:
        if img['filename'] in seen_fnames:
            continue
        seen_fnames.add(img['filename'])
        deduped.append(img)
    images = deduped

    mode = source['mode']
    if mode == 'image':
        prices_by_label = {}
        for img in images:
            label = img['carrier']
            img_bytes = None
            try:
                img_bytes = download_image(img['url'])
                prices = extract_prices_from_image(img_bytes)
            except Exception as e:
                prices = {'error': str(e)}
            prices_by_label[label] = prices
            image_records.append({
                **img, 'prices': prices,
                'carrier_full': PROVIDER_CANONICAL_NAME.get(label, label),
            })
            if img_bytes:
                images_with_bytes.append({**img, 'bytes': img_bytes})

    elif mode == 'image_summary':
        prices_by_label = {}
        for img in images:
            img_bytes = None
            try:
                img_bytes = download_image(img['url'])
                prices_by_label.update(extract_prices_from_summary_image(source, img_bytes))
            except Exception as e:
                prices_by_label['error'] = {'error': str(e)}
            image_records.append(img)
            if img_bytes:
                images_with_bytes.append({**img, 'bytes': img_bytes})

    else:  # mode == 'body_price'
        prices_by_label = extract_prices_from_body(source, detail['body_text'])
        for img in images:
            try:
                img_bytes = download_image(img['url'])
                image_records.append(img)
                images_with_bytes.append({**img, 'bytes': img_bytes})
            except Exception:
                pass

    write_date = datetime.fromtimestamp(article['write_ts_ms'] / 1000, tz=KST)
    round_no = _extract_round_no(article['subject'])
    highlights = extract_highlights(source, detail['body_text'])
    prev_prices_by_label = get_previous_prices_by_label(source, article_id)
    message = format_message(source, round_no, write_date, prices_by_label,
                              highlights, prev_prices_by_label)

    telegram_sent, telegram_error = False, None
    try:
        send_telegram_with_images(message, images_with_bytes)
        telegram_sent = True
    except Exception as e:
        telegram_error = str(e)

    # [추가 20260924] prices_by_label은 화면표시용 짧은 라벨(부성="텔링크"/비전="세븐"
    # 처럼 소스별로 다를 수 있음)이 키라서 그대로 두고, DB 조회 시 부성/비전 두 소스를
    # 같은 사업자 기준으로 비교할 수 있도록 정식 사업자명을 키로 쓰는 버전을 추가 저장
    prices_by_provider = {
        PROVIDER_CANONICAL_NAME.get(label, label): v
        for label, v in prices_by_label.items()
    }

    record = {
        'article_id': article_id,
        'subject': article['subject'],
        'writer': article['writer'],
        'write_date': write_date,
        'body_text': detail['body_text'],
        'images': image_records,
        'prices_by_label': prices_by_label,
        'prices_by_provider': prices_by_provider,
        'formatted_message': message,
        'telegram_sent': telegram_sent,
        'telegram_error': telegram_error,
        'created_at': datetime.now(KST),
    }

    # [수정 20260923] 문서ID를 article_id(예: "987")가 아니라 날짜(예: "2026-09-23")로 변경 -
    # 나중에 콘솔에서 훑어볼 때 article_id만으론 언제 글인지 바로 안 보여서 해석이 어렵다는
    # 지적. article_id는 필드로는 계속 남겨둠(get_previous_prices_by_label의 정렬/조회에 필요).
    # 같은 날 수정글이 다시 올라오면 그 날짜 문서를 덮어씀(최신본 유지가 맞는 동작).
    doc_id = write_date.strftime('%Y-%m-%d')

    # [주의] merge=True는 안 씀 - Firestore는 중첩 맵(prices_by_label 등)을 재귀적으로
    # 합쳐버려서, 예전 실행의 실패 기록(예: error 필드)이 새 성공 값과 뒤섞여 남는 문제가 있었음.
    # 매번 완전히 새로운 레코드를 만드는 구조라 merge 자체가 불필요.
    db = _get_db()
    db.collection(source['firestore_collection']).document(doc_id).set(record)
    set_last_seen_article_id(source, article_id)
    return record


def _get_secret_json(secret_name: str) -> dict:
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    name = f'projects/mvno-484509/secrets/{secret_name}/versions/latest'
    resp = client.access_secret_version(request={'name': name})
    return json.loads(resp.payload.data.decode('utf-8'))


def send_telegram_message(text: str) -> dict:
    """cafe-notify-telegram 시크릿(JSON: {"bot_token":..., "chat_id":...})으로 텍스트만 전송.
    [수정 20260923] <pre> monospace 박스 스타일이 채팅 말풍선과 안 어울린다는 피드백으로
    되돌림 - format_message()의 폭 기반 패딩(_pad)만으로 가변폭 글꼴에서도 최대한 맞춤."""
    cfg = _get_secret_json('cafe-notify-telegram')
    bot_token, chat_id = cfg['bot_token'], cfg['chat_id']
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    r = requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=15)
    r.raise_for_status()
    return r.json()


def send_telegram_with_images(text: str, images: list) -> dict:
    """메시지 + 첨부 정책표 이미지들을 앨범(sendMediaGroup)으로 같이 전송.
    캡션은 텔레그램 제약상 첫 번째 사진에만 붙는다."""
    cfg = _get_secret_json('cafe-notify-telegram')
    bot_token, chat_id = cfg['bot_token'], cfg['chat_id']

    if not images:
        return send_telegram_message(text)

    files = {}
    media = []
    for i, img in enumerate(images[:10]):  # 텔레그램 앨범 제한 10장
        field = f'photo{i}'
        files[field] = (img.get('filename', f'{field}.png'), img['bytes'], 'image/png')
        entry = {'type': 'photo', 'media': f'attach://{field}'}
        if i == 0:
            entry['caption'] = text
        media.append(entry)

    url = f'https://api.telegram.org/bot{bot_token}/sendMediaGroup'
    r = requests.post(url, data={'chat_id': chat_id, 'media': json.dumps(media)}, files=files, timeout=60)
    r.raise_for_status()
    return r.json()


def poll_and_process(source: dict, page_size: int = 15) -> tuple:
    """스케줄러가 주기적으로 호출: 새 글 있으면 전부 처리.
    반환값 (results, errors) - errors가 있으면 호출부(runner)가 "신규 없음"으로
    조용히 넘기지 말고 반드시 실패를 알려야 한다 (실패와 무소식을 구분하기 위함)."""
    last_seen = get_last_seen_article_id(source)
    articles = fetch_latest_articles(source, page_size=page_size)
    new_ones = [a for a in articles if a['article_id'] > last_seen]
    new_ones.sort(key=lambda a: a['article_id'])  # 오래된 것부터 순서대로 처리

    results, errors = [], []
    for a in new_ones:
        try:
            results.append(process_new_article(source, a))
        except Exception as e:
            print(f"[cafe_collector:{source['msg_prefix']}] 게시글 {a['article_id']} 처리 실패: {e}")
            errors.append({'article_id': a['article_id'], 'subject': a['subject'], 'error': str(e)})
    return results, errors
