"""Stage dispatcher for scheduled runs (GitHub Actions / cron).

IMPORTANT: GitHub Actions cron is best-effort and frequently delayed by 1-3
hours. So we must NOT decide the stage from the current wall-clock time (a
delayed 7 AM cron would otherwise run the 9:30 AM stage). Instead we key off
WHICH cron line fired, passed in via --schedule "${{ github.event.schedule }}".

Each cron line lists two candidate UTC times to cover EST/EDT, so a stage can
fire twice a day; per-day idempotency (db.run_log) makes the second fire a
no-op. This is also resilient to GitHub dropping one of the two fires.

Usage:
  python scripts/dispatch.py --schedule "0 11,12 * * 1-5"   # scheduled
  python scripts/dispatch.py --stage morning                # manual (forced)
  python scripts/dispatch.py                                # local: pick by ET time
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = None

# Cron line (as written in .github/workflows/daily.yml) -> stage script.
# Must match daily.yml exactly — the cron string is the routing key.
SCHEDULE_MAP = {
    "0 11,12,13 * * 1-5": "morning_scan.py",
    "30 13,14,15 * * 1-5": "market_open_check.py",
    "30 20,21,22 * * 1-5": "post_market_update.py",
    "0 22,23 * * 1-5": "grader.py",
}

# Manual alias -> stage script.
ALIAS = {
    "morning": "morning_scan.py",
    "open": "market_open_check.py",
    "post": "post_market_update.py",
    "grade": "grader.py",
}

# Fallback (local cron): target ET time -> stage.
STAGES_BY_TIME = {
    (7, 0): "morning_scan.py",
    (9, 30): "market_open_check.py",
    (16, 30): "post_market_update.py",
    (18, 0): "grader.py",
}
TOLERANCE_MIN = 90


def _run(script: str) -> int:
    print(f"[dispatch] running {script}")
    return subprocess.call([sys.executable, str(SRC / script)], cwd=str(SRC))


def _pick_by_time(now: datetime) -> str | None:
    now_min = now.hour * 60 + now.minute
    best, best_delta = None, TOLERANCE_MIN + 1
    for (h, m), script in STAGES_BY_TIME.items():
        delta = abs(now_min - (h * 60 + m))
        if delta <= TOLERANCE_MIN and delta < best_delta:
            best, best_delta = script, delta
    return best


def resolve_script(schedule: str, stage: str) -> str | None:
    if stage:
        return ALIAS.get(stage.strip().lower(), stage.strip())
    if schedule:
        return SCHEDULE_MAP.get(schedule.strip())
    now = datetime.now(ET) if ET else datetime.utcnow()
    if now.weekday() >= 5:
        print(f"[dispatch] {now:%Y-%m-%d} is a weekend — skipping.")
        return None
    return _pick_by_time(now)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule", default="", help="the cron string that fired")
    ap.add_argument("--stage", default="", help="force a stage (morning|open|post|grade)")
    ap.add_argument("stage_pos", nargs="?", default="", help="positional stage (back-compat)")
    args = ap.parse_args(argv[1:])

    stage = args.stage or args.stage_pos
    forced = bool(stage)  # manual invocations always run, bypassing idempotency

    script = resolve_script(args.schedule, stage)
    if not script:
        print("[dispatch] no stage matched — no-op.")
        return 0

    stage_name = script.replace(".py", "")

    import db
    db.init_db()
    if not forced and db.already_ran_today(stage_name):
        print(f"[dispatch] {stage_name} already ran today — skipping (idempotent).")
        return 0

    rc = _run(script)
    if rc == 0:
        db.log_run(stage_name)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
