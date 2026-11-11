# pinnradar: Pinnacle odds API client for Python

Python client for the [PinnRadar API](https://pinnradar.com): real-time **Pinnacle odds** as JSON. Live and prematch markets (moneyline, spreads, totals, team totals, every period), dropping-odds alerts over Server-Sent Events, and no-vig helpers.

Pinnacle closed its public API to most users in July 2025. PinnRadar is an independent service (not affiliated with Pinnacle) that serves Pinnacle's live and prematch prices over a simple REST API and push streams, with a free tier.

- No dependencies (standard library only), Python 3.8+
- Typed, with clear errors (`AuthError`, `RateLimitError`)
- Streams reconnect with backoff

```bash
pip install pinnradar
```

Get a free key at [pinnradar.com](https://pinnradar.com/panel#signup) (email only, no card, no Pinnacle account).

## Quick start

```python
from pinnradar import Client

pr = Client("YOUR_KEY")          # or set PINNRADAR_API_KEY

# Live soccer board (sport_id 1)
board = pr.markets(sport_id=1)
for ev in board["events"]:
    ml = ev["periods"]["num_0"].get("money_line") or {}
    print(ev["home"], "v", ev["away"], ml.get("home"), ml.get("draw"), ml.get("away"))

# Only what changed since the last call
board = pr.markets(sport_id=1, since=board["last"])
```

## Prematch

```python
fixtures = pr.prematch_fixtures(sport_id=3)          # basketball
event_id = fixtures["events"][0]["event_id"]
markets = pr.prematch_markets(event_id)               # every period and line
totals = pr.prematch_lines(event_id, market_type="totals")
```

## Dropping odds

Recent drops from the server-side buffer:

```python
for d in pr.drops(mode="live", sport_id=1, min_drop_pct=7, max_age_sec=600):
    print(d["home"], d["market"], d["side"], d["from"], "->", d["to"], f'{d["drop_pct"]:.1f}%')
```

Or follow them live over SSE (plans with SSE: Drops, Edge, Scale):

```python
for drop in pr.stream_drops(min_drop=5):              # prematch=True for /odds-drop-prematch
    print(drop["home"], drop["sect"], drop["outcome"], drop["from_price"], "->", drop["to_price"], "fair", drop["nvp"])
```

## No-vig (fair) odds

```python
from pinnradar import no_vig, margin

margin([1.952, 1.952])                  # 0.0246 -> 2.5 % margin
no_vig([2.10, 3.45, 3.70])              # fair 1X2 prices
no_vig([1.25, 4.20], method="power")    # takes more margin from the longshot
```

There is also an online [no-vig calculator](https://pinnradar.com/tools/no-vig-calculator).

## Sport ids

| id | sport | id | sport |
|---|---|---|---|
| 1 | Soccer | 5 | American football |
| 2 | Tennis | 6 | Baseball |
| 3 | Basketball | 11 | Esports |
| 4 | Hockey | | |

## Errors and limits

```python
from pinnradar import AuthError, RateLimitError

try:
    pr.markets(1)
except RateLimitError as e:
    print("slow down for", e.retry_after, "seconds")
except AuthError:
    print("check your key or plan")
```

Rate limits depend on the plan; see [pricing](https://pinnradar.com/pinnacle-api-pricing). Any other endpoint can be called with `pr.get("/path", **params)`.

## Links

- API docs: https://pinnradar.com/docs
- WebSocket feed and MCP server: https://pinnradar.com/docs
- Node.js client: https://www.npmjs.com/package/pinnradar

PinnRadar is an independent data service, not affiliated with Pinnacle. MIT licensed.
