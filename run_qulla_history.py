"""Public daily Binance/Hyperliquid candles for isolated breakout backtesting.

READ ONLY: no account authentication, API keys, trading orders, or paper
ledger reads/writes. This runs manually or via a branch-only research Action.
"""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import time

from bot import BINANCE_URL, HYPERLIQUID_URL, MarketDataError, read_json
from qulla_breakout_lab import (
    DAY_MS, FEE, SLIPPAGE, MAX_NOTIONAL, START_CASH, compare, validate,
)

DAYS = 900
MIN_DAYS = 500
# No new-market discovery, authenticated endpoints, or order API usage.
MARKETS = (
    ("binance", "BTC", "BTCUSDT spot"),
    ("binance", "ETH", "ETHUSDT spot"),
    ("hyperliquid", "BTC", "BTC perpetual"),
    ("hyperliquid", "ETH", "ETH perpetual"),
)


def fmt_utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def fetch_daily(venue, asset, now_ms):
    """Fetch latest 900 COMPLETED 1d bars; invalid/missing data fails closed."""
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("Invalid reference time")
    if asset not in ("BTC", "ETH") or venue not in ("binance", "hyperliquid"):
        raise ValueError("Unknown venue or research asset")
    if venue == "binance":
        params = urlencode({"symbol": asset + "USDT", "interval": "1d",
                            "limit": 1000})
        data = read_json(f"{BINANCE_URL}?{params}")
        if not isinstance(data, list) or len(data) > 1000:
            raise MarketDataError("Unexpected Binance daily candle data")
        try:
            bars = [{"end_ms": int(r[6]), "open": float(r[1]),
                     "high": float(r[2]), "low": float(r[3]),
                     "close": float(r[4]), "volume": float(r[5])}
                    for r in data]
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            raise MarketDataError("Malformed Binance daily OHLCV") from exc
    else:
        # The public /info candleSnapshot response includes at most recent
        # 5000 bars; a 910-day bounded 1d request stays well below that.
        data = read_json(HYPERLIQUID_URL, {
            "type": "candleSnapshot",
            "req": {"coin": asset, "interval": "1d",
                    "startTime": now_ms - (DAYS + 10) * DAY_MS,
                    "endTime": now_ms},
        })
        if not isinstance(data, list) or len(data) > 1100:
            raise MarketDataError("Unexpected Hyperliquid daily candle data")
        try:
            bars = [{"end_ms": int(r["T"]), "open": float(r["o"]),
                     "high": float(r["h"]), "low": float(r["l"]),
                     "close": float(r["c"]), "volume": float(r["v"])}
                    for r in data]
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            raise MarketDataError("Malformed Hyperliquid daily OHLCV") from exc

    # Only close timestamps in the past; ignore the current unfinished bar.
    bars = [b for b in bars if b["end_ms"] <= now_ms][-DAYS:]
    try:
        validate(bars, minimum=MIN_DAYS)
    except ValueError as exc:
        raise MarketDataError(f"Invalid {venue} {asset} daily series: {exc}") from exc
    if now_ms - bars[-1]["end_ms"] > 2 * DAY_MS:
        raise MarketDataError(f"Stale daily feed for {venue} {asset}")
    return bars


def passive_reference(bars, first):
    """2%-notional passive long; buy at first holdout open, sell last close.

    Uses both sides' fees/slippage, with independent $10k virtual balance.
    Not exposure/risk matched to the active strategy; perps funding omitted.
    """
    if not (0 <= first < len(bars)):
        raise ValueError("Invalid passive benchmark window")
    buy = bars[first]["open"] * (1 + SLIPPAGE)
    sell = bars[-1]["close"] * (1 - SLIPPAGE)
    budget = START_CASH * MAX_NOTIONAL
    units = budget / (buy * (1 + FEE))
    proceeds = units * sell * (1 - FEE)
    return 100 * (proceeds - budget) / START_CASH


def build_report(results, now_ms):
    lines = [
        "# Historical breakout research — daily BTC/ETH",
        "",
        f"Generated (UTC): {datetime.fromtimestamp(now_ms/1000, timezone.utc):%Y-%m-%d %H:%M}",
        "",
        "**RESEARCH ONLY. ALL FUNDS VIRTUAL. NO ORDERS, WALLET, KEYS, OR RUNNING PAPER-LEDGER CHANGES.**",
        "",
        "Original Qullamaggie-inspired *crypto hypothesis*, NOT his verified rules.",
        "Uses up to 900 consecutive COMPLETED UTC 1d bars per market, no parameter tuning.",
        "Fixed 70/30 chronological train/holdout with fresh $10,000 virtual balance",
        "for each segment, 2% max virtual notional, 0.25% modeled equity stop risk.",
        f"Assumed per-side fee {FEE*100:.2f}% and slippage {SLIPPAGE*100:.2f}%; double-cost rerun.",
        "Entry signal known at prior close; fills at next open; gap stops may lose more.",
        "The 1% loss circuit is only a NEXT-DAILY-BAR entry cooldown, not intraday protection.",
        "",
        "## Results — net of assumed costs",
        "",
        "| Market | Completed daily bars | Sample UTC | Train return | Holdout return | 2x costs holdout | Holdout max DD | Closed holdout trades | 2%-notional passive benchmark |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        r = item["result"]
        bars = item["bars"]
        lines.append(
            f"| {item['venue']} {item['symbol']} | {len(bars)} | "
            f"{fmt_utc(bars[0]['end_ms'])} to {fmt_utc(bars[-1]['end_ms'])} | "
            f"{r['train']['return_pct']:+.3f}% | "
            f"{r['holdout']['return_pct']:+.3f}% | "
            f"{r['stress_holdout']['return_pct']:+.3f}% | "
            f"{r['holdout']['max_drawdown_pct']:.3f}% | "
            f"{r['holdout']['closed_trades']} | "
            f"{item['passive_return']:+.3f}% |"
        )
    lines.extend([
        "",
        "## Interpretation and risks",
        "",
        "- The passive 2%-notional comparison is **not risk matched**: its exposure lasts",
        "  for the entire holdout, while the strategy may spend most of its time in cash.",
        "- Zero-trade samples show NO evidence of an edge. An open position is marked",
        "  at the last close without a final liquidation commission; inspect separately.",
        "- Spot Binance and Hyperliquid perpetuals are different products. Funding,",
        "  collateral, liquidation, borrowing, spreads and market impact are not modeled.",
        "- A 900-day sample is too short to demonstrate durable robustness over regimes;",
        "  using the holdout to tune rules would invalidate the reported out-of-sample result.",
        "- No settings are changed in the running hourly Binance/Hyperliquid paper bot.",
        "- Even positive historical results would require independent time periods and",
        "  a much longer monitored forward virtual trial before considering real capital.",
        "",
        "Public data: https://data-api.binance.vision/api/v3/klines",
        "and https://api.hyperliquid.xyz/info (type=candleSnapshot).",
        "",
    ])
    return "\n".join(lines)


def run(path="backtest-results/qulla-daily.md", now_ms=None, fetcher=fetch_daily):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    results = []
    # Fail closed: no partial report unless all four public feeds validate.
    for venue, asset, label in MARKETS:
        bars = fetcher(venue, asset, now_ms)
        validate(bars, minimum=MIN_DAYS)
        r = compare(bars)
        results.append({"venue": venue, "symbol": label, "bars": bars,
                        "result": r, "passive_return": passive_reference(bars, r["split"])})
    report = build_report(results, now_ms)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return report


if __name__ == "__main__":
    try:
        print(run())
    except (MarketDataError, OSError, ValueError) as exc:
        print(f"DAILY BREAKOUT HISTORICAL RESEARCH FAILED CLOSED: {exc}")
        raise SystemExit(1)
