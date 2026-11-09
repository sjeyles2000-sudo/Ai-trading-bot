# Always-on *PAPER ONLY* worker

The Docker image runs the existing hourly `demo_runner.py` in an independently
hosted Python process. This is **not a real trading engine**. It makes only public
market-data calls; uses two independent $10,000 virtual accounts; and never signs,
submits or cancels an exchange order. Existing GitHub Actions paper trading is
unaffected. Do not run two writers against the same persistent volume.

## Deployment
A host with a persistent attached Linux volume and Docker/Compose is required.
No hosting purchase, deployment, account authorization or connection has been made.

From the repo root on a secured Linux server:
```sh
docker compose -f server/compose.yaml build
# Initialize the volume ONCE; no exchange keys are needed.
docker compose -f server/compose.yaml run --rm paper-worker python server/paper_worker.py --initialize
docker compose -f server/compose.yaml up -d
docker compose -f server/compose.yaml logs --tail 50 paper-worker
```

For Railway or another container platform: root directory must be the repository
root; Dockerfile path `server/Dockerfile`; provide a *persistent volume* mounted
at `/data` owned/writable by the container's non-root user. First initialize
it using a one-off command `python server/paper_worker.py --initialize` (only
on an empty durable volume), then run `python server/paper_worker.py` with
`TRADING_MODE=paper` and `PAPER_STATE_DIR=/data`. **Do not deploy** without
volume persistence, ability to inspect logs, and an operator who can stop it.
The default image does not open a web port; choose a background-worker service.
Some platforms require plan-specific always-on runtime and volume configuration.

The `/data/ledger/` files are local container results **and do not sync to the
GitHub `paper-results` branch**. They are separate virtual simulations.
Backup the entire persistent volume securely; before restoring, verify the
ledger and marker have consistent histories. Losing the persistent volume
is a stop condition, not a reason to silently reset accounts.
`/data/worker-status.json` gives the last result; it is *not* a monitoring or
emergency shutdown service. A failed feed records an error, then retries later.
Review errors, stale price feeds, duplicate workers and host outages manually.

## Non-negotiable restrictions
- Never add Binance API keys, secret keys, Hyperliquid agent wallets, private
  keys or seed phrases to this container, GitHub, screenshots or ChatGPT.
- This image contains no authenticated exchange API/order endpoint. The
  absence of permissions is intentional, not a missing configuration.
- Do not enable leverage or real trading. Actual Hyperliquid derivatives
  eligibility and Binance Australia restrictions require separate review.
- Only one paper worker per `/data` volume. No automatic horizontal scaling.
- Production engineering still needed: atomic multi-file ledger persistence,
  monitored backups, operational alerting, kill switch, verified regulatory
  eligibility, robust execution modeling and integration tests before
  contemplating real orders.
- This Docker worker is a preliminary deployment candidate; review and test it
  before merging. A successful build/CI does not prove uptime or profitability.

## Cost and control
Cloud hosting may have monthly charges even with a small application. Check
the provider's current offer and set usage/billing alerts before deploying.
No provider connection, subscription or deployment is required just to review
this draft PR.
