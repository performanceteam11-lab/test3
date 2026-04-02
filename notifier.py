"""
Slack 웹훅 알림 모듈
크롤링 완료 후 결과 요약을 슬랙으로 발송
"""

import json
import urllib.request
import urllib.error
from datetime import date

from config import SLACK_WEBHOOK_URL


def send_result(results: list[dict]):
    check_date  = date.today().isoformat()
    total       = len(results)
    exposed     = sum(1 for r in results if r["exposed"])
    not_exposed = total - exposed
    rate        = round(exposed / total * 100) if total else 0

    # 브랜드별 집계
    def brand_stat(brand):
        b = [r for r in results if r["brand"] == brand]
        e = sum(1 for r in b if r["exposed"])
        return len(b), e

    nj_total, nj_exp = brand_stat("ninja")
    sh_total, sh_exp = brand_stat("shark")

    # 헤더 이모지
    header_emoji = ":white_check_mark:" if not_exposed == 0 else ":warning:"

    lines = [
        f"{header_emoji} *브랜드검색 모니터링 완료* | {check_date}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f">전체  *{total}개* | 노출  *{exposed}개*  ({rate}%) | 미노출  *{not_exposed}개*",
        f">Ninja  {nj_exp}/{nj_total}   |   Shark  {sh_exp}/{sh_total}",
    ]

    # 미노출 키워드 목록
    if not_exposed > 0:
        lines.append("")
        lines.append(":x: *미노출 키워드*")
        for r in results:
            if not r["exposed"]:
                lines.append(f"  • `[{r['device'].upper()}]` {r['keyword']}")
    else:
        lines.append(":tada: 모든 키워드 정상 노출 중입니다!")

    lines.append("")
    lines.append(":bar_chart: 대시보드 확인: http://localhost:5000")

    payload = {"text": "\n".join(lines)}
    data    = json.dumps(payload).encode("utf-8")
    req     = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data    = data,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[Slack] 발송 완료 (status={resp.status})")
    except urllib.error.URLError as e:
        print(f"[Slack] 발송 실패: {e}")
