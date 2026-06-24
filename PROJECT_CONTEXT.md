# Project Context — Earnings Edge Analyst

## Purpose
A daily, automated earnings-play scanner. It answers one question every trading
morning: *which names reporting soon have a tradeable edge, and what's the play?*
Output is a ranked set of pick cards delivered to Telegram, each with a
confidence score and an AI-written narrative, followed by intraday heartbeats and
an end-of-day grade.

This is a **screening and tracking tool**, not an advisor. Every output carries an
"informational only, not financial advice" disclaimer.

## How a day flows
1. **07:00 ET — `morning_scan.py`**
   - Pulls the watchlist (~150 liquid names; see `fetchers/earnings_whispers.py`).
   - For each, `yfinance_fetcher.fetch()` computes price/volume/momentum/vol
     metrics, the next earnings date, an IV-rank proxy, and last earnings surprise.
   - Keeps names reporting within the lookahead window (default 10 days).
   - `model/scoring.py` scores each across all three play types; the best play per
     ticker is kept if it clears the confidence + liquidity + price gates.
   - Top N (default 5) get an AI narrative (`narratives.py`), are persisted to
     SQLite (`db.py`), and are delivered as Telegram cards (`cards.py`,
     `telegram_bot.py`).
2. **09:30 ET — `market_open_check.py`** — opening gap on each pick.
3. **16:30 ET — `post_market_update.py`** — EOD move vs entry.
4. **18:00 ET — `grader.py`** — grades the prior day's picks (WIN/LOSS/FLAT),
   logs P&L to the `grades` table.

Scheduling is handled by `scripts/dispatch.py` (ET/DST-aware) driven either by
GitHub Actions (`.github/workflows/daily.yml`) or a local scheduler.

## Scoring model (`model/scoring.py`)
Each play type blends normalized 0–1 features by the weights in
`config/formula.yaml`, producing a 0–1 score and a 0–10 confidence.

- **PRE_RUNUP** — momentum, relative volume, proximity to earnings, analyst drift.
- **IV_CRUSH** — IV rank (hard floor via `min_iv_rank`), IV-vs-realized richness,
  options liquidity, name stability (low beta).
- **POST_MOMENTUM** — earnings surprise magnitude (hard floor via
  `min_surprise_pct`), opening gap, volume confirmation, 5-day follow-through.

Global gates: `min_confidence_to_send`, `max_picks_per_day`, `min_avg_volume`,
`min_price`. All tunable at runtime via `/tune`.

## Data sources
- **yfinance (primary, required)** — prices, volume, options chain, earnings
  dates/surprise. Note: blocked on networks that egress-filter Yahoo hosts.
- **Polygon, Unusual Whales, Reddit/PRAW, Finviz (optional)** — enrichment;
  every fetcher degrades to a no-op when its key is missing, so the pipeline
  never breaks.

## Known approximations / limitations
- `iv_rank` is a proxy (current ATM IV vs realized-vol range), not a true
  52-week IV percentile — Yahoo doesn't provide IV history.
- `analyst_drift` is a coarse tilt from the recommendation mean.
- Grading marks-to-market on close price vs entry; it does not model the actual
  options structure of `IV_CRUSH`/`PRE_RUNUP` plays — treat P&L as a directional
  proxy, not a backtest.

## Persistence (`data/picks.db`)
- `picks` — every pick with metrics JSON, narrative, sent flag.
- `grades` — per-pick outcome and P&L.
- `skips` — per-day exclusions from `/skip`.

## Models used
- Narratives & NL answers: Anthropic API (`NARRATIVE_MODEL`, default
  `claude-opus-4-8`); optional, template fallback otherwise.
- Everything else is deterministic Python.

## Extension ideas
- Expand the watchlist toward the full S&P 500, or swap in a paid earnings
  calendar API for reliability.
- Replace the IV-rank proxy with Polygon/Unusual Whales real IV data.
- Add a webhook-based Telegram bot for real-time commands without a long-poll
  process.
