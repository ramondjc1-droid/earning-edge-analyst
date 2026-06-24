"""Stage dispatcher for scheduled runs (GitHub Actions / cron).

GitHub Actions cron is UTC-only and does not observe US daylight saving. To stay
correct year-round we fire the workflow at every candidate UTC time and let this
dispatcher decide — based on the *current* America/New_York time — which stage
(if any) should actually run. Exactly one ET target matches per fire; the rest
no-op. You can also force a stage with: python scripts/dispatch.py <stage>.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = None

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# (target ET hour, minute) -> script. Tolerance is +/- 45 min so an 11:00 UTC
# fire still maps cleanly whether it's 6:00 or 7:00 ET across the DST boundary.
STAGES = {
    (7, 0):  "morning_scan.py",
    (9, 30): "market_open_check.py",
    (16, 30): "post_market_update.py",
    (18, 0): "grader.py",
}
TOLERANCE_MIN = 45


def _run(script: str) -> int:
    print(f"[dispatch] running {script}")
    return subprocess.call([sys.executable, str(SRC / script)], cwd=str(SRC))


def pick_stage(now: datetime) -> str | None:
    now_min = now.hour * 60 + now.minute
    best, best_delta = None, TOLERANCE_MIN + 1
    for (h, m), script in STAGES.items():
        delta = abs(now_min - (h * 60 + m))
        if delta <= TOLERANCE_MIN and delta < best_delta:
            best, best_delta = script, delta
    return best


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        forced = argv[1].lower()
        alias = {
            "morning": "morning_scan.py", "open": "market_open_check.py",
            "post": "post_market_update.py", "grade": "grader.py",
        }
        return _run(alias.get(forced, forced))

    now = datetime.now(ET) if ET else datetime.utcnow()
    # Skip weekends entirely (markets closed).
    if now.weekday() >= 5:
        print(f"[dispatch] {now:%Y-%m-%d %H:%M %Z} is a weekend — skipping.")
        return 0
    script = pick_stage(now)
    if not script:
        print(f"[dispatch] {now:%H:%M %Z} matches no stage window — no-op.")
        return 0
    print(f"[dispatch] {now:%Y-%m-%d %H:%M %Z} -> {script}")
    return _run(script)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
