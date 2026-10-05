"""Cloud Run Job 진입점 - ktoa-collector(ktoa_scraper.py)와 동일한 방식으로
`python cafe_collector_runner.py` 커맨드로 실행된다.
Cloud Scheduler가 09/13/19시(KST) 하루 3번 이 Job을 트리거한다.

[수정 20260923] SOURCES(busung/vision) 전부 순회하도록 변경 - 소스 하나가 실패해도
다른 소스는 계속 처리하고, 실패는 실패한 소스만 보고한다(전체를 죽이지 않음).

[원칙] "신규 없음"과 "확인 실패"는 절대 같은 침묵으로 보이면 안 된다 -
소스별로 매 실행마다 반드시 텔레그램으로 뭔가는 간다: 새 정책 / 신규 없음 / 확인 실패 중 하나."""
import logging
from datetime import datetime, timezone, timedelta
from cafe_collector import SOURCES, poll_and_process, send_telegram_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('cafe_collector_runner')
KST = timezone(timedelta(hours=9))


def _now():
    return datetime.now(KST).strftime('%H:%M')


def run_source(source_key: str, source: dict) -> bool:
    """소스 하나 처리. 반환값: 이번 실행이 (전체적으로) 성공했는지 여부."""
    prefix = source['msg_prefix']
    try:
        results, errors = poll_and_process(source)
    except Exception as e:
        log.error(f'[{source_key}] poll_and_process 자체가 실패: {e}')
        try:
            send_telegram_message(f'{prefix} {_now()} 확인 실패 ⚠️\n원인: {e}')
        except Exception as e2:
            log.error(f'[{source_key}] 실패 알림 전송까지 실패: {e2}')
        return False

    for r in results:
        log.info(f"[{source_key}] 처리 완료: #{r['article_id']} {r['subject']} "
                  f"(telegram_sent={r['telegram_sent']})")

    if errors:
        log.error(f'[{source_key}] 일부 게시글 처리 실패: {errors}')
        lines = [f"#{e['article_id']} {e['subject']}: {e['error']}" for e in errors]
        try:
            send_telegram_message(f'{prefix} {_now()} 확인 실패 ⚠️\n' + '\n'.join(lines))
        except Exception as e2:
            log.error(f'[{source_key}] 실패 알림 전송까지 실패: {e2}')
        return False

    if not results:
        log.info(f'[{source_key}] 새 글 없음')
        try:
            send_telegram_message(f'{prefix} {_now()} 확인 - 신규 정책 없음')
        except Exception as e:
            log.error(f'[{source_key}] 무소식 알림 전송 실패: {e}')

    return True


if __name__ == '__main__':
    ok = True
    for source_key, source in SOURCES.items():
        if not run_source(source_key, source):
            ok = False
    if not ok:
        raise RuntimeError('하나 이상의 소스 처리에 실패했습니다 (위 로그 참조)')
