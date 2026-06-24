# Earnings Edge Analyst

Automated daily earnings-play scanner. Every trading morning it scans the
earnings calendar, scores names across three play types, ranks the top plays,
writes an AI narrative for each, stores them, and pushes the cards to **Telegram**.
Heartbeats through the day track how the picks are doing and grade them at the close.

> ⚠️ **Informational only — not financial advice.** Picks and narratives are
> AI-generated screens, not recommendations. Do your own research, size your own
> risk. Nothing here is a solicitation to buy or sell any security.

---

## Three play types

| Play | When | Exit |
|------|------|------|
| 🚀 `PRE_RUNUP` | Buy before earnings, ride the pre-report drift | ~1 day before report |
| 💥 `IV_CRUSH` | Sell elevated options premium into the event | ~1 day after report |
| 📈 `POST_MOMENTUM` | Enter after a confirmed beat | 3–5 days after |

Scoring weights live in [`config/formula.yaml`](config/formula.yaml) and can be
tuned live with the `/tune` Telegram command.

---

## Quick start (local)

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in your keys (see below)
python src/morning_scan.py --dry-run     # preview, prints cards to console
python src/morning_scan.py               # live run (sends to Telegram)
```

The system runs even with **zero** API keys — narratives fall back to a
deterministic template and delivery prints to the console. Add keys to unlock
AI narratives and Telegram push.

---

## 1. Telegram setup (so picks reach your phone)

1. In Telegram, message **@BotFather** → send `/newbot` → follow prompts → copy the **bot token**.
2. Put it in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-yourtoken
   ```
3. Open a chat with your new bot and send it any message (e.g. "hi").
4. Discover your chat id:
   ```bash
   python src/telegram_bot.py chatid
   ```
   Copy the printed id into `.env`:
   ```
   TELEGRAM_CHAT_ID=987654321
   ```
5. Test the link:
   ```bash
   python src/telegram_bot.py        # sends a "Telegram link test" message
   ```
   You should receive it in Telegram. Then `python src/morning_scan.py` will
   deliver real pick cards.

---

## 2. Automated morning scans (recommended: GitHub Actions)

The cleanest hands-off option — runs in the cloud on a schedule, no PC required,
and it lives in this repo. See [`.github/workflows/daily.yml`](.github/workflows/daily.yml).

**Setup (one time):**

1. Push this repo to GitHub (already done if you're reading this there).
2. Go to **Settings → Secrets and variables → Actions → New repository secret**
   and add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ANTHROPIC_API_KEY` (optional — for AI narratives)
   - `POLYGON_API_KEY`, `UNUSUAL_WHALES_API_KEY`, `REDDIT_CLIENT_ID`,
     `REDDIT_CLIENT_SECRET` (all optional)
3. That's it. The workflow fires on this schedule (US Eastern, DST-aware via
   [`scripts/dispatch.py`](scripts/dispatch.py)):

   | Time (ET) | Stage |
   |-----------|-------|
   | 7:00 AM | `morning_scan` — the daily picks |
   | 9:30 AM | `market_open_check` — opening gaps |
   | 4:30 PM | `post_market_update` — EOD moves |
   | 6:00 PM | `grader` — grade & log P&L |

**Test it now without waiting for the schedule:** go to **Actions → Earnings
Edge — Daily Scans → Run workflow**, set *stage* to `morning`, and run. You
should get the pick cards in Telegram.

> **Notes**
> - GitHub disables scheduled workflows after **60 days** of repo inactivity —
>   any push (or a manual run) re-arms them.
> - Scheduled runs can lag a few minutes under GitHub load; that's normal.
> - Secrets are stored encrypted by GitHub and only exposed to the workflow.

### Alternative: run on your own machine

**Windows Task Scheduler** — create 4 tasks pointing at `python.exe` with
arguments, e.g. for the morning scan at 7:00 AM:
```
Program:   C:\Path\to\python.exe
Arguments: C:\Users\Ramon\...\earnings-edge-analyst\src\morning_scan.py
Start in:  C:\Users\Ramon\...\earnings-edge-analyst
```
Repeat for `market_open_check.py` (9:30), `post_market_update.py` (16:30),
`grader.py` (18:00). Your PC must be on at those times.

**Linux/Mac cron** (let the dispatcher handle timing; it self-skips off-target):
```cron
0  11,12 * * 1-5 cd /path/to/earnings-edge-analyst && python scripts/dispatch.py
30 13,14 * * 1-5 cd /path/to/earnings-edge-analyst && python scripts/dispatch.py
30 20,21 * * 1-5 cd /path/to/earnings-edge-analyst && python scripts/dispatch.py
0  22,23 * * 1-5 cd /path/to/earnings-edge-analyst && python scripts/dispatch.py
```

---

## 3. Interactive commands (optional)

To text the bot and get live answers (`/picks`, `/status`, `/iv $TSLA`, "why did
you pick FDX?"), run the long-poll listener on a machine that stays on:

```bash
python src/command_handler.py
```

| Command | Does |
|---------|------|
| `/picks` | today's picks |
| `/status` | system health |
| `/grade` | yesterday's results |
| `/week` · `/month` | rolling P&L |
| `/history $TICKER` | all picks on a ticker |
| `/calendar` | upcoming earnings in the watchlist |
| `/iv $TICKER` | IV-rank proxy check |
| `/tune path value` | adjust a formula weight, e.g. `/tune iv_crush.weights.iv_rank 0.5` |
| `/skip $TICKER` | exclude from today's scan |
| `/add $TICKER` | force-analyze any ticker now |
| _free text_ | natural-language Q&A about the picks |

The scheduled push (section 2) works **without** this listener — it's only
needed for two-way chat.

---

## Environment caveats (read if running in a sandbox/cloud shell)

- **Market data source.** Data comes from Yahoo Finance via `yfinance`. Some
  locked-down networks (including certain agent/cloud sandboxes) **block Yahoo's
  hosts by egress policy**, so a live scan there returns no data. This is a
  network-policy limitation, not a bug — run on a normal network (your machine
  or GitHub Actions runners, which have open internet).
- **IV rank is a proxy.** Yahoo doesn't expose a true 52-week IV history, so
  `iv_rank` is derived from current ATM implied vol vs the name's realized-vol
  range. Directionally useful, not a Bloomberg figure. Wire in Polygon/Unusual
  Whales for higher-fidelity vol data.

---

## Project layout

```
earnings-edge-analyst/
├── src/
│   ├── morning_scan.py        # MAIN daily script
│   ├── market_open_check.py   # 9:30 AM heartbeat
│   ├── post_market_update.py  # 4:30 PM heartbeat
│   ├── grader.py              # 6:00 PM grading
│   ├── command_handler.py     # slash commands + NL (long-poll)
│   ├── telegram_bot.py        # Telegram send + chat-id helper
│   ├── narratives.py          # AI narrative generation
│   ├── cards.py               # Telegram card formatting
│   ├── db.py                  # SQLite operations
│   ├── config.py              # .env + formula loader
│   ├── model/scoring.py       # the scoring formula
│   └── fetchers/              # yfinance + optional enrichments
├── scripts/dispatch.py        # ET-aware stage dispatcher for schedulers
├── config/formula.yaml        # tunable weights
├── tests/test_pipeline.py     # offline smoke tests
├── .github/workflows/         # daily.yml (schedule) + ci.yml (tests)
└── data/picks.db              # SQLite (created on first run)
```

## Models

- Data fetching, scoring, DB, commands — plain Python.
- Narratives & natural-language answers — Anthropic API (`NARRATIVE_MODEL`,
  default `claude-opus-4-8`). Optional; falls back to templates without a key.
