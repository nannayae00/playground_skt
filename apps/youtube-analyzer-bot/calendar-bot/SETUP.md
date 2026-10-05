# 텔레그램 → 구글 캘린더 봇 셋업 가이드

> Cloud Run (GCP) + 개인 구글 캘린더 (OAuth2) 기준

---

## 파일 구성

```
calendar-bot/
├── main.py              # Flask 앱 + 텔레그램 webhook
├── gemini_handler.py    # Gemini로 일정 파싱 & 수정
├── calendar_handler.py  # Google Calendar API 등록
├── session_manager.py   # 사용자 대화 상태 관리
├── get_token.py         # OAuth2 토큰 발급 (로컬 1회 실행용)
├── requirements.txt
├── Dockerfile
└── deploy.sh            # Cloud Run 배포 스크립트
```

---

## STEP 1 — 텔레그램 봇 만들기

1. 텔레그램에서 **@BotFather** 검색 → 채팅 시작
2. `/newbot` 입력
3. 봇 이름 설정 (예: `내 캘린더봇`)
4. 봇 username 설정 (예: `my_calendar_bot`) — 끝이 `bot`으로 끝나야 함
5. 발급된 **TOKEN** 복사해두기

```
예시: 7812345678:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## STEP 2 — GCP 프로젝트 준비

기존 price-monitor 프로젝트 그대로 사용 가능합니다.

```bash
# 프로젝트 확인
gcloud config get-value project

# 필요한 API 활성화
gcloud services enable run.googleapis.com
gcloud services enable calendar-json.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

---

## STEP 3 — OAuth2 클라이언트 ID 만들기

> 구글 캘린더 개인 계정 연동은 서비스 계정이 아닌 OAuth2 방식 사용

1. [GCP Console](https://console.cloud.google.com) → **API 및 서비스** → **사용자 인증 정보**
2. 상단 **+ 사용자 인증 정보 만들기** → **OAuth 2.0 클라이언트 ID**
3. 애플리케이션 유형: **데스크톱 앱** 선택
4. 이름 적당히 입력 후 **만들기**
5. **JSON 다운로드** 클릭 → 파일명을 `client_secret.json` 으로 저장
6. `client_secret.json` 을 `calendar-bot/` 폴더에 넣기

> ⚠️ OAuth 동의 화면이 설정 안 됐다는 오류 뜨면:  
> API 및 서비스 → OAuth 동의 화면 → 외부 선택 → 앱 이름/이메일만 채우고 저장

---

## STEP 4 — Refresh Token 발급 (로컬 1회만 실행)

```bash
# calendar-bot 폴더에서 실행
pip install google-auth-oauthlib
python get_token.py
```

- 브라우저가 자동으로 열림
- 본인 구글 계정으로 로그인
- "액세스 허용" 클릭
- 터미널에 아래처럼 출력됨:

```
============================================================
✅ 인증 성공! 아래 값들을 Secret Manager에 저장하세요.
============================================================

GOOGLE_CLIENT_ID:
  123456789-xxxxxxxx.apps.googleusercontent.com

GOOGLE_CLIENT_SECRET:
  GOCSPX-xxxxxxxxxxxxxx

GOOGLE_REFRESH_TOKEN:
  1//0xxxxxxxxxxxxxxxxxxxxxxxx
============================================================
```

이 3개 값을 복사해두기.

---

## STEP 5 — Secret Manager에 저장

```bash
# 아래 명령어에서 각 값을 실제 값으로 교체해서 실행

echo -n "여기에_CLIENT_ID" | gcloud secrets create gcal-client-id --data-file=-
echo -n "여기에_CLIENT_SECRET" | gcloud secrets create gcal-client-secret --data-file=-
echo -n "여기에_REFRESH_TOKEN" | gcloud secrets create gcal-refresh-token --data-file=-

# 텔레그램 토큰도 저장
echo -n "여기에_TELEGRAM_TOKEN" | gcloud secrets create telegram-token --data-file=-
```

---

## STEP 6 — 배포

`deploy.sh` 파일 열어서 PROJECT_ID 수정:

```bash
PROJECT_ID="your-project-id"  # ← 본인 GCP 프로젝트 ID로 변경
```

배포 실행:

```bash
chmod +x deploy.sh
export TELEGRAM_TOKEN="여기에_TELEGRAM_TOKEN"
export GEMINI_API_KEY="여기에_GEMINI_API_KEY"
./deploy.sh
```

성공하면 아래처럼 출력:

```
✅ 배포 완료: https://calendar-bot-xxxxx-an.a.run.app
📡 텔레그램 Webhook 등록...
{"ok": true, "result": true, ...}
🎉 완료!
```

---

## STEP 7 — 동작 테스트

텔레그램에서 봇 검색 후 채팅 시작:

| 입력 | 동작 |
|------|------|
| `/start` | 봇 안내 메시지 |
| `3/21 하키 10시` | 일정 파싱 → 확인 요청 |
| 예약 문자 붙여넣기 | 일정 파싱 → 확인 요청 |
| 스케줄표 텍스트 | 여러 일정 파싱 → 확인 요청 |
| ✅ 등록 버튼 | 구글 캘린더에 등록 |
| ✏️ 수정 버튼 → 수정 내용 입력 | 수정 후 재확인 |
| ❌ 취소 버튼 | 취소 |

---

## 환경변수 정리

| 변수명 | 설명 | 저장 위치 |
|--------|------|-----------|
| `TELEGRAM_TOKEN` | 텔레그램 봇 토큰 | 환경변수 or Secret |
| `GEMINI_API_KEY` | Gemini API 키 | 환경변수 |
| `GOOGLE_CLIENT_ID` | OAuth2 클라이언트 ID | Secret Manager |
| `GOOGLE_CLIENT_SECRET` | OAuth2 클라이언트 시크릿 | Secret Manager |
| `GOOGLE_REFRESH_TOKEN` | OAuth2 리프레시 토큰 | Secret Manager |
| `GOOGLE_CALENDAR_ID` | 캘린더 ID (`primary` = 기본) | 환경변수 |

---

## 자주 막히는 곳

**Q. `get_token.py` 실행 시 "액세스 차단됨" 오류**  
→ OAuth 동의 화면에서 본인 이메일을 테스트 사용자로 추가  
→ API 및 서비스 → OAuth 동의 화면 → 테스트 사용자 → 이메일 추가

**Q. Cloud Run 배포 후 캘린더 등록 안 됨**  
→ Secret Manager 권한 확인  
→ `gcloud run services describe calendar-bot --region asia-northeast3` 로 서비스 계정 확인  
→ 해당 서비스 계정에 Secret Manager 접근 권한 부여:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SA@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**Q. Webhook 등록은 됐는데 봇이 응답 안 함**  
→ Cloud Run 로그 확인:
```bash
gcloud run services logs read calendar-bot --region asia-northeast3 --limit 50
```
