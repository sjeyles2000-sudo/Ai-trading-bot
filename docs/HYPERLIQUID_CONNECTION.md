# Hyperliquid secure connection preparation — READ ONLY

This change **does not implement live orders, testnet orders, signing, or copying traders**.
The existing paper simulation is unchanged. Live order capability is absent,
not merely hidden behind an environment flag. Both `submit_order` and
`cancel_order` reject every call.

## What to configure

1. Create or choose a Hyperliquid account. For initial checks use **testnet**.
2. Set `HYPERLIQUID_NETWORK=testnet` and
   `HYPERLIQUID_ACCOUNT_ADDRESS=0x...` in the runtime environment.
   The address is **public**, and should identify the master account whose
   information you want to inspect; it is not an API-wallet private key.
3. Run `python hyperliquid_connection.py` to check **public** account access
   through Hyperliquid's `/info` API. Only a short success message is printed.
4. Run `python -m unittest discover -s tests -v` for offline safety checks.

Do **not** paste keys, seed phrases or API-wallet private keys into chat,
GitHub files, pull requests, screenshots, logs, or issue comments.
No signing credential is necessary for this stage. When a future,
separately approved implementation needs a signing key, prefer a dedicated
low-permission API wallet and an encrypted secret manager at the deployment
host. Never use the master wallet seed phrase. Audit and rotate credentials
after any suspected exposure. Do not give a bot withdrawal permissions.

## Security and trading safeguards for a future, separate proposal

A future execution implementation requires a **new** review and explicit
owner approval before live activation. Plan to use:
- Testnet integration tests, strict account/chain identity checking,
  transaction simulation, and verified request signing;
- Hard server-side live-disable default and manual explicit arming workflow,
  with expiration and a hardware/operational kill switch;
- Separate API-wallet signing key from the master wallet, stored only in a
  dedicated secrets manager, not in Git or logs;
- Max leverage, size, open orders, notional exposure, daily loss, slippage,
  price freshness, liquidity and per-symbol allowlists;
- Position reconciliation, idempotency and duplicate-order protection,
  exchange error handling, circuit breakers and audit logs;
- Independent emergency close/cancel procedures to test on testnet;
- Extended forward paper trading, realistic fee/funding modelling,
  and careful examination of performance before considering real money.

A successful read-only check is **not** proof of trade readiness or profitability.
Geographic or regulatory restrictions may apply. Neither GitHub Actions nor
this ChatGPT conversation is a reliable continuously running live execution host.

API references:
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
