# Elysium launchpad research — offline and paper-only

As of 10 November 2026, STOCKIUM, BOXA and ASCEND are **research leads**, not verified trade opportunities. Telegram promotions, third-party dashboards and snapshots can be stale, manipulated or misattributed. Never infer profitability from reported volume.

Run `python elysium_watch.py` to produce a **NOT READY** report for all three. No network calls, credentials, wallets, order submission or account access are included. An optional manually independently verified JSON snapshot can be screened:

```bash
python elysium_watch.py --snapshot reviewed_snapshots.json --output elysium-risk-report.md
python -m unittest discover -s tests -p 'test_elysium_watch.py' -v
```

The snapshot must be an array containing at most one item per project. Fields:
`project` (STOCKIUM, BOXA, ASCEND), `source_url` (HTTPS reference),
`chain`, `contract_address`, `observed_at` (ISO 8601 with timezone),
`liquidity_usd`, `volume_24h_usd`, `top10_holder_pct`,
`round_trip_cost_pct` (including entry and exit fees, token taxes, and
conservative slippage), `sell_simulation_verified`, and
`contract_permissions_reviewed`. **Do not enter fabricated values.**

The screen fails closed for missing/invalid values, data older than two hours,
liquidity below $50,000, 24-hour volume below $25,000, holder concentration over
35%, or estimated round-trip costs over 3%. The quantitative thresholds are
provisional conservative research heuristics, **not proof of safety or
an approved strategy**. A successful screen never authorizes trading.

Before any actual paper-trading strategy is developed, independently verify
contract addresses against official project sources, explorer transactions,
sale restrictions, mint/freeze/upgrade permissions, holder distribution, and
historical executable quotes. Paper results must include fees and realistic
price impact. Use multiple market regimes, out-of-sample evaluation and risk
limits. Do not merge this research into exchange order execution.

No live-market scan, paper P&L, ongoing job or profitability claim is provided
by this change. Existing Binance/Hyperliquid BTC simulation remains unchanged.
