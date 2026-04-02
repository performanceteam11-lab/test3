"""
크롤링 결과를 GitHub Pages용 JSON으로 내보내기
- 이미지: JPEG 45% / 최대 500px → 약 15~20KB/장
- 출력: docs/results.json
- 완료 후 git commit & push
"""

import base64
import io
import json
import os
import subprocess
from datetime import date
from pathlib import Path

from PIL import Image

from database import get_results_by_date

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
DOCS_DIR.mkdir(exist_ok=True)


# ── 이미지 압축 ───────────────────────────────────────────────────────────────
def compress_image(path: str, max_width: int = 500, quality: int = 45) -> str | None:
    try:
        with Image.open(path) as img:
            # 가로 max_width 기준 비율 축소
            if img.width > max_width:
                ratio  = max_width / img.width
                new_h  = int(img.height * ratio)
                img    = img.resize((max_width, new_h), Image.LANCZOS)

            # JPEG로 변환 (투명도 처리)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [이미지 압축 오류] {path}: {e}")
        return None


# ── JSON 내보내기 ─────────────────────────────────────────────────────────────
def export_results(check_date: str | None = None):
    if check_date is None:
        check_date = date.today().isoformat()

    rows = get_results_by_date(check_date)
    print(f"[Export] {check_date} — {len(rows)}개 결과 처리 중...")

    results = []
    for r in rows:
        raw_paths = (r.get("screenshot_paths") or "").strip()
        paths = [p for p in raw_paths.split(",") if p] if raw_paths else []

        # 이미지 압축
        images = []
        for p in paths:
            b64 = compress_image(p)
            if b64:
                images.append(b64)

        results.append({
            "keyword":       r["keyword"],
            "device":        r["device"],
            "brand":         r["brand"],
            "campaign":      r["campaign"],
            "group_name":    r["group_name"],
            "exposed":       bool(r["exposed"]),
            "creative_count": r["creative_count"],
            "images":        images,
        })

    # 통계
    total    = len(results)
    exposed  = sum(1 for r in results if r["exposed"])
    payload  = {
        "date":    check_date,
        "stats": {
            "total":       total,
            "exposed":     exposed,
            "not_exposed": total - exposed,
            "rate":        round(exposed / total * 100) if total else 0,
        },
        "results": results,
    }

    out_path = DOCS_DIR / "results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"[Export] 저장 완료: docs/results.json ({size_mb:.1f} MB)")
    return out_path


# ── Git push ──────────────────────────────────────────────────────────────────
def git_push(check_date: str):
    os.chdir(BASE_DIR)
    cmds = [
        ["git", "add", "docs/results.json", "docs/index.html"],
        ["git", "commit", "-m", f"result: {check_date}"],
        ["git", "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[Git] 오류: {result.stderr.strip()}")
            return False
    print("[Git] push 완료")
    return True


# ── 진입점 ────────────────────────────────────────────────────────────────────
def run_export_and_push(check_date: str | None = None):
    if check_date is None:
        check_date = date.today().isoformat()
    export_results(check_date)
    git_push(check_date)


if __name__ == "__main__":
    run_export_and_push()
