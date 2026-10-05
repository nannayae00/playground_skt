# 텔레그램 → 사내 이메일 브릿지

VDI(Citrix) 환경에서 로컬 파일을 사내 메일로 전달하기 위한 텔레그램 봇입니다.

## 동작 방식

```
텔레그램에서 파일 전송
        ↓
Cloud Run (봇 서버)
        ↓
Gmail SMTP로 발송
        ↓
사내 메일 수신 → VDI에서 다운로드
```

## 1단계: 준비

### 텔레그램 봇 생성
1. @BotFather → /newbot → 이름 입력
2. 토큰 복사 (TELEGRAM_BOT_TOKEN)

### 내 텔레그램 user_id 확인
1. @userinfobot 에서 /start 입력
2. 숫자 ID 복사 (ALLOWED_USER_IDS)

### Gmail 앱 비밀번호 발급
1. Google 계정 → 보안 → 2단계 인증 활성화
2. 앱 비밀번호 → 기타 → 생성
3. 16자리 복사 (GMAIL_APP_PASSWORD)

---

## 2단계: Cloud Run 배포

```bash
# 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID

# 이미지 빌드 & 배포 (한 번에)
gcloud run deploy tg-mail-bridge \
  --source . \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "TELEGRAM_BOT_TOKEN=YOUR_TOKEN" \
  --set-env-vars "TELEGRAM_WEBHOOK_URL=https://PLACEHOLDER" \
  --set-env-vars "ALLOWED_USER_IDS=YOUR_USER_ID" \
  --set-env-vars "GMAIL_ADDRESS=your@gmail.com" \
  --set-env-vars "GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx" \
  --set-env-vars "OFFICE_MAIL=your@company.com"
```

배포 완료 후 출력되는 URL을 복사해서 TELEGRAM_WEBHOOK_URL 업데이트:

```bash
gcloud run services update tg-mail-bridge \
  --region asia-northeast3 \
  --update-env-vars "TELEGRAM_WEBHOOK_URL=https://실제-URL.run.app"
```

---

## 3단계: Webhook 등록

브라우저에서 접속:
```
https://실제-URL.run.app/set_webhook
```

`{"ok": true}` 응답이 오면 완료!

---

## 4단계: 사용

텔레그램 봇에서:
- `/start` → 봇 소개 및 수신 메일 확인
- `/status` → 현재 설정 확인
- **파일 전송** → 사내 메일로 자동 발송
- **파일 + 메모 입력** → 메모가 메일 본문에 포함

---

## 지원 파일 형식

모든 파일 형식 지원 (텔레그램 파일 크기 제한 20MB 이하)

| 종류 | 설명 |
|------|------|
| document | Excel, Word, PDF, ZIP 등 모든 파일 |
| photo | 이미지 (최고 화질) |
| video | 동영상 |
| audio | 음악 파일 |
| voice | 음성 메시지 |

---

## 환경변수 목록

| 변수명 | 설명 | 예시 |
|--------|------|------|
| TELEGRAM_BOT_TOKEN | 봇 토큰 | `1234:ABCdef...` |
| TELEGRAM_WEBHOOK_URL | Cloud Run URL | `https://xxx.run.app` |
| ALLOWED_USER_IDS | 허용 user_id (쉼표 구분) | `123456789` |
| GMAIL_ADDRESS | 발신 Gmail | `name@gmail.com` |
| GMAIL_APP_PASSWORD | Gmail 앱 비밀번호 | `xxxx xxxx xxxx xxxx` |
| OFFICE_MAIL | 수신 사내 메일 | `name@company.com` |
