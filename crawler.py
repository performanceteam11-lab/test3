"""
브랜드검색 모니터링 크롤러
- 네이버에서 키워드별 브랜드검색 영역을 캡처
- PC / 모바일 각각 처리
- 키워드당 6회 새로고침으로 멀티 소재 수집
- 4개 병렬 처리
"""

import asyncio
import csv
import os
import hashlib
import random
from datetime import date
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright

from database import save_result, init_db, get_results_by_date
from notifier import send_result
from export_github import run_export_and_push

# ── 설정 ──────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
SCREENSHOT_DIR = BASE_DIR / "screenshots"
CSV_PATH       = BASE_DIR / "브랜드검색 raw.csv"

NAVER_SEARCH   = "https://search.naver.com/search.naver?query={}"
REFRESH_COUNT  = 6
PARALLEL_LIMIT = 4

# 네이버 브랜드검색 DOM 셀렉터 (우선순위 순)
BRAND_SELECTORS = [
    ".brand_search",          # PC 브랜드검색 메인 컨테이너
    ".brand_new_ui",
    ".sp_brand",              # 모바일 브랜드검색 메인 컨테이너
    "#brand_area",
    ".brand_area",
    "[data-area='brand']",
    ".brand_wrap",
    ".ad_brand",
    "#adinfo_wrap",
    ".adinfo_wrap",
]

# 모바일 에뮬레이션 설정 (Galaxy S21)
MOBILE_CONFIG = {
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 12; SM-G991B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "viewport": {"width": 390, "height": 844},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}

PC_CONFIG = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1440, "height": 900},
    "is_mobile": False,
}
# ─────────────────────────────────────────────────────────────────────────────


def load_keywords() -> list[dict]:
    keywords = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            campaign = row["캠페인"].strip()
            group    = row["그룹"].strip()
            keyword  = row["키워드"].strip()
            if not keyword:
                continue
            device = "mo" if campaign.endswith("-mo") else "pc"
            brand  = "ninja" if campaign.startswith("nj_") else "shark"
            keywords.append({
                "campaign": campaign,
                "group":    group,
                "keyword":  keyword,
                "device":   device,
                "brand":    brand,
            })
    return keywords


def image_hash(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()


def safe_filename(keyword: str) -> str:
    for ch in r'/\:*?"<>|':
        keyword = keyword.replace(ch, "_")
    return keyword.replace(" ", "_")


async def find_brand_element(page):
    """브랜드검색 DOM 요소 탐색 - 여러 셀렉터를 순서대로 시도"""
    for selector in BRAND_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return el
        except Exception:
            continue

    # 최후 수단: 페이지 상단에 "광고" 텍스트가 포함된 큰 박스 탐색
    try:
        el = await page.query_selector(".total_wrap:first-child")
        if el and await el.is_visible():
            text = await el.inner_text()
            if "광고" in text:
                return el
    except Exception:
        pass

    return None


async def capture_keyword(context, keyword_info: dict, check_date: str):
    keyword  = keyword_info["keyword"]
    device   = keyword_info["device"]
    brand    = keyword_info["brand"]

    date_dir = SCREENSHOT_DIR / check_date
    date_dir.mkdir(parents=True, exist_ok=True)

    page = await context.new_page()
    screenshots = []
    seen_hashes: set[str] = set()

    try:
        url = NAVER_SEARCH.format(quote(keyword))

        for i in range(REFRESH_COUNT):
            try:
                if i == 0:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                else:
                    await page.reload(wait_until="domcontentloaded", timeout=30_000)

                # 콘텐츠 렌더링 대기 (0.8~1.5초 랜덤)
                await asyncio.sleep(random.uniform(0.8, 1.5))

                brand_el = await find_brand_element(page)

                if brand_el:
                    img_bytes = await brand_el.screenshot()
                    h = image_hash(img_bytes)
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        fname = f"{safe_filename(keyword)}_{device}_{len(screenshots)+1}.png"
                        fpath = date_dir / fname
                        fpath.write_bytes(img_bytes)
                        screenshots.append(str(fpath))

            except Exception as e:
                print(f"    [새로고침 {i+1}회 오류] {keyword} ({device}): {e}")
                continue

        exposed = len(screenshots) > 0
        status  = f"노출 {len(screenshots)}개 소재" if exposed else "미노출"
        icon    = "[OK]" if exposed else "[X]"
        print(f"  {icon} [{device.upper()}] {keyword} - {status}")

    except Exception as e:
        print(f"  ✗ [{device.upper()}] {keyword} — 오류: {e}")
        exposed = False

    finally:
        await page.close()

    save_result(
        check_date     = check_date,
        keyword        = keyword,
        device         = device,
        brand          = brand,
        campaign       = keyword_info["campaign"],
        group_name     = keyword_info["group"],
        exposed        = exposed,
        creative_count = len(screenshots),
        screenshot_paths = screenshots,
    )


async def run_crawler():
    init_db()
    check_date = date.today().isoformat()
    keywords   = load_keywords()

    print(f"\n{'='*60}")
    print(f"  브랜드검색 모니터링 시작  [{check_date}]")
    print(f"  총 {len(keywords)}개 키워드 | 병렬 {PARALLEL_LIMIT}개")
    print(f"{'='*60}\n")

    semaphore = asyncio.Semaphore(PARALLEL_LIMIT)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        async def process(kw: dict):
            async with semaphore:
                cfg = MOBILE_CONFIG if kw["device"] == "mo" else PC_CONFIG
                context = await browser.new_context(
                    user_agent        = cfg["user_agent"],
                    viewport          = cfg["viewport"],
                    is_mobile         = cfg.get("is_mobile", False),
                    has_touch         = cfg.get("has_touch", False),
                    device_scale_factor = cfg.get("device_scale_factor", 1),
                    locale            = "ko-KR",
                    timezone_id       = "Asia/Seoul",
                )
                try:
                    await capture_keyword(context, kw, check_date)
                finally:
                    await context.close()

        await asyncio.gather(*[process(kw) for kw in keywords])
        await browser.close()

    print(f"\n{'='*60}")
    print(f"  모니터링 완료  [{check_date}]")
    print(f"{'='*60}\n")

    # Slack 결과 발송
    results = get_results_by_date(check_date)
    send_result(results)

    # GitHub Pages JSON 내보내기 + git push
    print("\n[Export] GitHub Pages 업데이트 중...")
    run_export_and_push(check_date)


if __name__ == "__main__":
    asyncio.run(run_crawler())
