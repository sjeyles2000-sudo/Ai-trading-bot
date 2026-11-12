# Execution resilience research (draft, paper-only)

This **offline-only** research script adds a fixed-parameter stress comparison
without changing the scheduled Binance or Hyperliquid trading bot.

## Run

Provide your own public, completed 1-hour BTC OHLC bars as a local JSON array
containing `end_ms`, `open`, `high`, `low` and `close`, with at least 80
consecutive candles. This script does NOT fetch market data or access accounts.

```bash
python execution_stress.py hourly_btc.json --market 'BTC paper research'
python -m unittest discover -s tests -p 'test_execution_stress.py' -v
```

Generates `execution-stress.md`. No changes to `ledger/`, scheduled jobs,
trading positions, credentials or exchange permissions. No API calls or orders.

## What is compared?

- Fixed 5/20 completed-hour SMA crossover, next-hour open execution
- Doubled per-side fee and slippage
- A one-hour additional signal/execution delay
- A hypothetical eight-hour disconnected interval starting 80% into sample
- A combined fee, delay and outage scenario

New entries are skipped during outages. A held position can miss an exit
or stop and may gap adversely on reconnect; after recovery it exits at
the next available opening price with modelled slippage.

**Limitations:** This is simplified candle-based research, not realistic
exchange-native order-book or leveraged trading simulation. Historical outage
locations are invented stress scenarios, not claims about actual incidents.
An hourly bar cannot determine precise intrabar stop/entry ordering. Funding,
variable spreads, market impact and liquidation are not modelled. Small
sample sizes and low numbers of closed trades are inconclusive. This script
does not test profitable strategies or activate paper execution. Compare against
cash and holding BTC, and run longer independent holdout and prospective tests.

Do NOT merge into main until the tests and simulated fills have been reviewed.
