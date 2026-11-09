# Secure automated trading architecture — PAPER FIRST

**Status: DESIGN AND READ-ONLY RESEARCH ONLY. Not connected to any funded account. NO REAL ORDERS.**

This branch adds a public-price preflight and simulated risk-validation boundary. It does not deploy a server, access exchange accounts, create API keys, migrate Grok credentials, or enable signing, withdrawals, spot orders, futures orders, leverage or margin. The already-scheduled paper trading workflow on `main` is unchanged.

## Markets and legal/operational gates
- **Binance Australia:** Spot market data and spot paper trading research only. Binance Australia's derivatives business was closed in 2023. Do not attempt to bypass geographic, account, licensing or retail eligibility restrictions by using alternate accounts, VPNs or API endpoints.
- **Hyperliquid:** Public mid-price checks; spot research and **simulated** perp leverage up to 2x. This simulation is not a real derivatives account. Before any live derivatives capability, independently verify Australian legal/regulatory requirements, the user's eligibility, exchange terms and actual available instruments. If unresolved, block live perps.
- Polymarket remains separate read-only research and is not a leverage venue for this project.

## Current features
- Fetch unauthenticated public Binance hourly BTC/USDT candles and Hyperliquid BTC mids. No API key or account address is needed. Public snapshots are **not** an exchange-authorization test or account connection.
- `check_risk_request` rejects non-paper requests, wrong venues/symbols, nonfinite inputs, virtual notional greater than 2% of simulated equity, daily losses at or above 1% of stated equity and leveraged spot requests. Hyperliquid leverage is **simulation-only**, limited to 2x.
- `reject_real_order` intentionally always raises and has **no exchange order interface**. No config/flag to enable it.
- Offline tests and branch-only GitHub Actions check; sanitized report artifact is public-price status only. No secrets or account balances.
- Existing scheduled paper bot does not use this preflight automatically; integration is a future separately reviewed task.

## Future always-on server plan, NOT YET DEPLOYED
1. Decide on a reliable VPS/cloud service in a region lawfully allowed by each exchange; choose a static outbound IP, managed firewall, encrypted disk and automatic security patches. Confirm monthly cost, service availability and operator responsibility.
2. Put code in a separate, reviewed production repository/release pipeline. Restrict deployment to signed/reviewed commits and explicit human approval for any live mode. The current research branch never deploys real trades.
3. Introduce a **distinct read-only** Binance API key with no withdrawal/transfer/trade/margin/futures permissions. Prefer IP restriction to the eventual server. Store the secret in a managed secrets store, **never** in GitHub files, issue comments, ChatGPT messages, screenshots or logs. Rotate/revoke legacy Grok keys/Hyperliquid API wallets after confirming there are no open positions/orders.
4. Hyperliquid public API can be queried without an API wallet. A trading agent wallet is a signing credential, not a read-only requirement: **do not create or import one** for this stage.
5. Build a dedicated trade executor only after separate review. No withdrawals, transfers, or unlimited permissions. Install independent pre-trade risk checks for total exposure, max leverage, liquidation-buffer, contract size, volatility, spread, stale candles, funding and exchange limits. Add a kill switch, order idempotency, retries with reconciliation, margin and position monitoring, exchange downtime handling, alerting and audit trail.
6. Test sandbox/testnet or simulated execution with realistic bid/ask, fees, funding, slippage, partial fills, rejected orders, gaps, funding and forced liquidation. Compare against a no-trade baseline over long data windows across regimes. No profit assurance.
7. Run a read-only account reconciliation test with the server and separately granted minimum scopes. Observe the paper bot for sustained periods, then ask for **new, explicit approval** before implementing or enabling any live-order permissions. At that stage scope credentials by account, venue, IP and allowed strategy, with a local emergency-stop procedure.
8. No autonomous operation is available within a chat; a deployed and monitored independent service would perform any future orders. GitHub Actions hourly schedules are not suitable for low-latency real trade execution.

## Your account security checklist
- Confirm that removing Grok also revoked old Binance API keys and Hyperliquid agent wallets. Deleting the Grok app by itself may not revoke exchange-side credentials.
- Verify no open orders or positions remain, including conditional/trigger orders.
- Do not share keys, secrets, passwords, private keys or wallet seed phrases with ChatGPT.
- **Do not enable Binance trading or Hyperliquid agent-wallet permissions during this phase.**

## Commands
`python -m unittest discover -s tests -v` — mocked regression tests.
`python read_only_preflight.py` — public-price read-only check only, with no credentials.

This phase is complete only when the branch CI is green. **Live trading remains disabled regardless of CI status.**
