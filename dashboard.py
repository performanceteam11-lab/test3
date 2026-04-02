"""
브랜드검색 모니터링 대시보드 (Flask)
"""

import os
from datetime import date
from pathlib import Path
from urllib.parse import quote

from flask import Flask, render_template, request, send_file, abort, jsonify

from database import get_results_by_date, get_available_dates, get_summary_by_date

BASE_DIR = Path(__file__).parent
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))


@app.template_filter("url_quote")
def url_quote_filter(s):
    return quote(str(s), safe="")


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _process_results(rows: list[dict]) -> list[dict]:
    """DB 결과 후처리: screenshot_paths 문자열 → 리스트"""
    for r in rows:
        raw = r.get("screenshot_paths") or ""
        r["screenshots"] = [p for p in raw.split(",") if p.strip()] if raw else []
    return rows


def _build_stats(results: list[dict]) -> dict:
    total   = len(results)
    exposed = sum(1 for r in results if r["exposed"])
    return {
        "total":       total,
        "exposed":     exposed,
        "not_exposed": total - exposed,
        "rate":        round(exposed / total * 100) if total else 0,
    }


# ── 라우트 ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    available_dates = get_available_dates()
    selected_date   = request.args.get("date", date.today().isoformat())

    # 선택 날짜가 없으면 가장 최근 날짜로 대체
    if available_dates and selected_date not in available_dates:
        selected_date = available_dates[0]

    results = _process_results(get_results_by_date(selected_date))

    ninja_pc  = [r for r in results if r["brand"] == "ninja" and r["device"] == "pc"]
    ninja_mo  = [r for r in results if r["brand"] == "ninja" and r["device"] == "mo"]
    shark_pc  = [r for r in results if r["brand"] == "shark" and r["device"] == "pc"]
    shark_mo  = [r for r in results if r["brand"] == "shark" and r["device"] == "mo"]

    stats = _build_stats(results)
    ninja_stats = _build_stats(ninja_pc + ninja_mo)
    shark_stats = _build_stats(shark_pc + shark_mo)

    return render_template(
        "dashboard.html",
        ninja_pc        = ninja_pc,
        ninja_mo        = ninja_mo,
        shark_pc        = shark_pc,
        shark_mo        = shark_mo,
        stats           = stats,
        ninja_stats     = ninja_stats,
        shark_stats     = shark_stats,
        available_dates = available_dates,
        selected_date   = selected_date,
    )


@app.route("/screenshot")
def screenshot():
    path = request.args.get("path", "")
    full = Path(path)
    if not full.exists() or not full.is_file():
        abort(404)
    # 보안: screenshots 폴더 내부에 있는 파일만 허용
    try:
        full.relative_to(BASE_DIR / "screenshots")
    except ValueError:
        abort(403)
    return send_file(str(full), mimetype="image/png")


@app.route("/api/results")
def api_results():
    selected_date = request.args.get("date", date.today().isoformat())
    results = _process_results(get_results_by_date(selected_date))
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
