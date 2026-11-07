# Laptop web monitor — public read-only page

The `docs/` directory is a static dashboard suitable for **GitHub Pages**.
It is separate from bot execution, requires no Python runtime on the laptop,
and includes **no trade buttons, credentials, order endpoints or keys**.

The page attempts to update publicly available Binance and Hyperliquid BTC
price quotes every 15 seconds while open. A public API may refuse requests
from browsers, and any last quote can become stale; status labels disclose
connection failures. No quotes are treated as profitable trading signals.

The page also polls the repo's public `paper-results` CSVs every minute
and `research-results` report files every five minutes. Those are
**saved snapshots**, not live exchange account balances or copy-trade
instructions. Paper trading is still run by scheduled GitHub Actions around
hourly. GitHub may skip or delay those runs.

## Set up the public website

After changes are reviewed and merged to `main`:
1. Open the repository's **Settings → Pages** page in a web browser.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select branch **main** and folder **/docs**, then **Save**.
4. Wait for GitHub Pages to display the published site URL.
5. Bookmark it in Microsoft Edge or Chrome on your laptop.

If you don't have permission to edit repository settings, an account
administrator must enable Pages. The web page is public; do not put
credentials or private wallet data in public GitHub repos.

This website is for *viewing only*. It cannot place real trades or run
continuous order execution. No third-party libraries or paid subscriptions
are required for the dashboard source. GitHub account Pages availability
and limits are subject to GitHub policy.
