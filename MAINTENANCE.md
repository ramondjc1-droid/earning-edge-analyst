# Maintenance

## Routine
- **Watchlist** (`src/fetchers/earnings_whispers.py`) — add/remove tickers in
  `WATCHLIST`. Known-bad symbols go in `_BANNED`. Removed stale names from the
  original build: `GPS`, `GLD`, `SQ` (delisted/renamed). Expand toward the full
  S&P 500 for broader coverage.
- **Weights** (`config/formula.yaml`) — tune live with `/tune path value`
  (e.g. `/tune iv_crush.weights.iv_rank 0.5`) or edit the file directly.
- **Gates** — `min_confidence_to_send`, `min_avg_volume`, `min_price`,
  `max_picks_per_day` are the quickest dials for pick quantity/quality.

## Health checks
```bash
python tests/test_pipeline.py                 # offline logic smoke tests
cd src && python command_handler.py test /status   # dispatcher self-test
python src/morning_scan.py --dry-run          # full run, no Telegram send
python src/telegram_bot.py                     # Telegram link test
```

## Common issues
| Symptom | Cause / fix |
|---------|-------------|
| All fetches return `ok=False` with a proxy/403 error | Network egress policy blocks Yahoo Finance. Run on an open network or GitHub Actions. |
| Picks saved but not delivered | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` unset or wrong. Re-run the chat-id helper: `python src/telegram_bot.py chatid`. |
| Narratives look templated | `ANTHROPIC_API_KEY` not set — that's the graceful fallback. Set the key for AI narratives. |
| Scheduled workflow stopped firing | GitHub disables cron after 60 days of inactivity. Push any commit or run it manually to re-arm. |
| `404`/empty for a ticker | Symbol delisted/renamed — add it to `_BANNED` in `earnings_whispers.py`. |

## Secrets
- Local: `.env` (gitignored — never commit it).
- GitHub Actions: **Settings → Secrets and variables → Actions**.
- Rotating a key: update it in both places you use.

## Database
- SQLite at `data/picks.db` (gitignored). Recreated automatically on first run.
- To reset history: stop schedulers, delete `data/picks.db`, next run rebuilds it.
- Back it up by copying the file; it's the only stateful artifact.

## Cost
- yfinance: free.
- Anthropic narratives: ~5 calls/day on scan, a few hundred tokens each — cents/day.
- Optional Polygon/Unusual Whales: per their plans.
