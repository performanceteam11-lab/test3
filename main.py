"""
브랜드검색 모니터링 — 진입점
- 매일 오전 9:50 자동 크롤링 (APScheduler)
- Flask 대시보드 서버 실행 (http://localhost:5000)

실행 방법:
    python main.py               ← 서버 시작 + 스케줄 등록
    python crawler.py            ← 즉시 크롤링만 실행 (테스트용)
"""

import asyncio
import threading
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import init_db
from crawler import run_crawler
from dashboard import app

# ── 로깅 설정 ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


# ── 크롤링 잡 ─────────────────────────────────────────────────────────────────
def crawl_job():
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[스케줄] 브랜드검색 모니터링 시작 — {now}")
    try:
        asyncio.run(run_crawler())
        logger.info("[스케줄] 모니터링 완료")
    except Exception as e:
        logger.error(f"[스케줄] 오류 발생: {e}")


# ── 스케줄러 ──────────────────────────────────────────────────────────────────
def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=KST)
    scheduler.add_job(
        crawl_job,
        CronTrigger(hour=9, minute=50, timezone=KST),
        id="brand_search_monitor",
        name="브랜드검색 모니터링",
        replace_existing=True,
        misfire_grace_time=300,   # 5분 이내 지연은 허용
    )
    scheduler.start()
    next_run = scheduler.get_job("brand_search_monitor").next_run_time
    logger.info(f"스케줄러 등록 완료 — 다음 실행: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    return scheduler


# ── 메인 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # DB 초기화
    init_db()
    logger.info("DB 초기화 완료")

    # 스케줄러 시작 (백그라운드 스레드)
    scheduler = start_scheduler()

    logger.info("=" * 50)
    logger.info("  브랜드검색 모니터링 서비스 시작")
    logger.info("  대시보드: http://localhost:5000")
    logger.info("  매일 오전 9:50 자동 실행")
    logger.info("  종료: Ctrl+C")
    logger.info("=" * 50)

    try:
        # Flask 대시보드 서버 (메인 스레드)
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,  # 스케줄러 중복 실행 방지
        )
    except KeyboardInterrupt:
        logger.info("서비스 종료 중...")
        scheduler.shutdown(wait=False)
        logger.info("종료 완료")
