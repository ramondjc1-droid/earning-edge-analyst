"""Slash-command + natural-language handler, served over Telegram long-polling.

Run as a long-lived process (systemd / Task Scheduler / nohup):

    python src/command_handler.py

Supported:
  /picks            today's picks
  /status           system health
  /grade            yesterday's results
  /week             last 7 days P&L
  /month            current month P&L
  /history $TICKER  all picks on a ticker
  /calendar         next earnings in the watchlist
  /iv $TICKER       IV-rank proxy check
  /tune param value adjust a formula weight (dotted path, e.g. iv_crush.weights.iv_rank)
  /skip $TICKER     exclude a ticker from today
  /add $TICKER      force-analyze a ticker now
  free text         e.g. "why did you pick FDX?"
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import yaml

import cards
import db
import narratives
from config import FORMULA_PATH, ANTHROPIC_API_KEY, NARRATIVE_MODEL, reload_formula
from fetchers import earnings_whispers as cal
from fetchers import yfinance_fetcher as yfin
from model import scoring
from telegram_bot import configured, get_updates, send_message


def _clean_ticker(arg: str) -> str:
    return arg.strip().lstrip("$").upper()


def cmd_picks(_=None) -> str:
    rows = db.picks_for_date(date.today().isoformat())
    if not rows:
        return "No picks recorded today. Run the morning scan first."
    out = [cards.header(len(rows), 0)]
    for r in rows:
        out.append(f"\n${r['ticker']} — {r['play_type']} ({r['confidence']}/10)\n"
                   f"<i>{r['narrative']}</i>")
    return "\n".join(out)


def cmd_status(_=None) -> str:
    today = db.picks_for_date(date.today().isoformat())
    tg = "✅ linked" if configured() else "⚠️ not configured"
    ai = "✅ live model" if ANTHROPIC_API_KEY else "⚠️ template fallback"
    return (
        "🩺 <b>System Status</b>\n"
        f"Telegram: {tg}\n"
        f"Narratives: {ai} ({NARRATIVE_MODEL})\n"
        f"Watchlist size: {len(cal.WATCHLIST)}\n"
        f"Picks today: {len(today)}\n"
        f"DB: picks.db OK"
    )


def cmd_grade(_=None) -> str:
    y = (date.today() - timedelta(days=1)).isoformat()
    rows = db.pnl_since(y)
    rows = [r for r in rows if r["pick_date"] == y]
    if not rows:
        return f"No graded results for {y} yet. The grader runs at 6 PM ET."
    lines = [f"📋 <b>Grades — {y}</b>"]
    for r in rows:
        lines.append(f"${r['ticker']} ({r['play_type']}): {r['pnl_pct']:+.1f}% [{r['outcome']}]")
    return "\n".join(lines)


def _pnl_summary(since: str, label: str) -> str:
    rows = db.pnl_since(since)
    if not rows:
        return f"No graded picks in the {label} window yet."
    wins = sum(1 for r in rows if r["outcome"] == "WIN")
    losses = sum(1 for r in rows if r["outcome"] == "LOSS")
    avg = sum(r["pnl_pct"] or 0 for r in rows) / len(rows)
    return (f"📈 <b>{label} P&L</b>\n"
            f"{len(rows)} graded · {wins}W / {losses}L · avg {avg:+.1f}% per pick")


def cmd_week(_=None) -> str:
    return _pnl_summary((date.today() - timedelta(days=7)).isoformat(), "7-day")


def cmd_month(_=None) -> str:
    return _pnl_summary(date.today().replace(day=1).isoformat(), "month-to-date")


def cmd_history(arg: str) -> str:
    if not arg:
        return "Usage: /history $TICKER"
    t = _clean_ticker(arg)
    rows = db.picks_for_ticker(t)
    if not rows:
        return f"No picks on record for ${t}."
    lines = [f"🗂 <b>History — ${t}</b>"]
    for r in rows:
        lines.append(f"{r['pick_date']}: {r['play_type']} ({r['confidence']}/10)")
    return "\n".join(lines)


def cmd_calendar(_=None) -> str:
    names = cal.upcoming_earnings(lookahead_days=5)
    if not names:
        return "No watchlist names report in the next 5 days."
    names.sort(key=lambda d: d.days_to_earnings or 99)
    lines = ["📅 <b>Upcoming Earnings (5d)</b>"]
    for d in names[:25]:
        lines.append(f"${d.ticker}: {d.earnings_date} (in {d.days_to_earnings}d)")
    return "\n".join(lines)


def cmd_iv(arg: str) -> str:
    if not arg:
        return "Usage: /iv $TICKER"
    t = _clean_ticker(arg)
    d = yfin.fetch(t)
    if not d.ok:
        return f"Could not fetch ${t}: {d.error}"
    return (f"📊 <b>${t} IV check</b>\n"
            f"IV-rank proxy: {d.iv_rank:.0f}\n"
            f"ATM IV: {d.iv_atm:.2%}  Realized(20d): {d.realized_vol:.2%}\n"
            f"IV/RV: {d.iv_vs_historical:.2f}")


def cmd_tune(arg: str) -> str:
    parts = arg.split()
    if len(parts) != 2:
        return ("Usage: /tune <dotted.param> <value>\n"
                "e.g. /tune iv_crush.weights.iv_rank 0.5")
    path, raw = parts
    try:
        value = float(raw)
    except ValueError:
        return f"'{raw}' is not a number."
    with open(FORMULA_PATH) as fh:
        data = yaml.safe_load(fh)
    node = data
    keys = path.split(".")
    try:
        for k in keys[:-1]:
            node = node[k]
        if keys[-1] not in node:
            return f"Unknown parameter: {path}"
        old = node[keys[-1]]
        node[keys[-1]] = value
    except (KeyError, TypeError):
        return f"Unknown parameter path: {path}"
    with open(FORMULA_PATH, "w") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)
    reload_formula()
    return f"🔧 Tuned <code>{path}</code>: {old} → {value}"


def cmd_skip(arg: str) -> str:
    if not arg:
        return "Usage: /skip $TICKER"
    t = _clean_ticker(arg)
    db.add_skip(t)
    return f"🚫 ${t} will be excluded from today's scan."


def cmd_add(arg: str) -> str:
    if not arg:
        return "Usage: /add $TICKER"
    t = _clean_ticker(arg)
    d = cal.force_fetch(t)
    if not d.ok:
        return f"Could not fetch ${t}: {d.error}"
    ps = scoring.best_play(d)
    if not ps:
        return f"No scorable play for ${t}."
    return cards.pick_card(ps, narratives.generate(ps))


def cmd_help(_=None) -> str:
    return (
        "🤖 <b>Earnings Edge — Commands</b>\n"
        "/picks · /status · /grade · /week · /month\n"
        "/history $T · /calendar · /iv $T\n"
        "/tune path value · /skip $T · /add $T\n"
        "Or just ask: \"why did you pick FDX?\""
    )


COMMANDS = {
    "/picks": cmd_picks, "/status": cmd_status, "/grade": cmd_grade,
    "/week": cmd_week, "/month": cmd_month, "/history": cmd_history,
    "/calendar": cmd_calendar, "/iv": cmd_iv, "/tune": cmd_tune,
    "/skip": cmd_skip, "/add": cmd_add, "/help": cmd_help, "/start": cmd_help,
}


def natural_language(text: str) -> str:
    """Answer free-text questions, grounded in today's picks when possible."""
    rows = db.picks_for_date(date.today().isoformat())
    context = "\n".join(
        f"${r['ticker']} {r['play_type']} conf {r['confidence']}: {r['narrative']}"
        for r in rows
    ) or "No picks recorded today."
    if not ANTHROPIC_API_KEY:
        return ("Natural-language answers need ANTHROPIC_API_KEY set.\n\n"
                f"Today's picks:\n{context}")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=NARRATIVE_MODEL,
            max_tokens=400,
            system=("You answer questions about an earnings-play scanner's picks. "
                    "Be concise and specific. Informational only, never financial "
                    "advice. Ground answers in the provided picks."),
            messages=[{"role": "user",
                       "content": f"Today's picks:\n{context}\n\nQuestion: {text}"}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    except Exception as exc:
        return f"Could not generate an answer ({exc}).\n\nToday's picks:\n{context}"


def dispatch(text: str) -> str:
    text = text.strip()
    if not text:
        return cmd_help()
    if text.startswith("/"):
        head, _, rest = text.partition(" ")
        fn = COMMANDS.get(head.lower())
        if fn:
            return fn(rest.strip())
        return f"Unknown command {head}. Try /help."
    return natural_language(text)


def serve(poll_timeout: int = 25) -> None:
    if not configured():
        print("[handler] Telegram not configured (need TELEGRAM_BOT_TOKEN + "
              "TELEGRAM_CHAT_ID). Exiting.")
        return
    db.init_db()
    print("[handler] listening for Telegram commands… (Ctrl-C to stop)")
    offset = None
    while True:
        try:
            updates = get_updates(offset=offset, timeout=poll_timeout)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                reply = dispatch(text)
                send_message(reply, chat_id=chat_id)
        except KeyboardInterrupt:
            print("\n[handler] stopped.")
            break
        except Exception as exc:
            print(f"[handler] loop error: {exc}; backing off 5s")
            time.sleep(5)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Offline test of the dispatcher: python src/command_handler.py test /status
        print(dispatch(" ".join(sys.argv[2:]) or "/help"))
    else:
        serve()
