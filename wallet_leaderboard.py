"""Public Hyperliquid leaderboard and top-wallet activity research ONLY.

This module does not sign, submit or simulate any real orders.
Leaderboard PnL is not audited proof of repeatable trader skill.
"""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bot import HYPERLIQUID_URL, MarketDataError, read_json

LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
VALID_WINDOWS = ("day", "week", "month")
MAX_ROWS = 100000
MIN_EQUITY = 20000
MIN_VOLUME = 100000
MAX_WALLETS = 5


def number(value):
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def load_public_board():
    request = Request(LEADERBOARD_URL, headers={"User-Agent": "ai-trader-paper-research/1.0",
                                                     "Accept": "application/json"})
    try:
        with urlopen(request, timeout=70) as response:
            # Large public feed: limit memory and fail on excessive response size.
            body = response.read(55_000_001)
        if len(body) > 55_000_000:
            raise MarketDataError("Leaderboard size limit exceeded")
        data = json.loads(body)
    except (OSError, ValueError, TimeoutError) as exc:
        raise MarketDataError(f"Could not load public leaderboard: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("leaderboardRows"), list):
        raise MarketDataError("Leaderboard response format changed")
    if len(data["leaderboardRows"]) > MAX_ROWS:
        raise MarketDataError("Leaderboard contains too many entries")
    return data["leaderboardRows"]


def shortlist(rows, limit=MAX_WALLETS):
    """Require consistent profits and meaningful volume; rank candidates, not guaranteed winners."""
    if not isinstance(rows, list):
        raise MarketDataError("Invalid leaderboard")
    result = []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        addr = entry.get("ethAddress")
        if not isinstance(addr, str) or len(addr) != 42 or not addr.startswith("0x"):
            continue
        if any(char not in "0123456789abcdefABCDEF" for char in addr[2:]):
            continue
        eq = number(entry.get("accountValue"))
        if eq is None or eq < MIN_EQUITY:
            continue
        windows = entry.get("windowPerformances")
        if not isinstance(windows, list):
            continue
        perf = {}
        for pair in windows:
            if isinstance(pair, list) and len(pair) == 2 and isinstance(pair[1], dict):
                perf[pair[0]] = pair[1]
        metrics = {}
        for window in VALID_WINDOWS:
            m = perf.get(window, {})
            pnl = number(m.get("pnl"))
            roi = number(m.get("roi"))
            vlm = number(m.get("vlm"))
            if pnl is None or roi is None or vlm is None:
                break
            metrics[window] = {"pnl": pnl, "roi": roi, "volume": vlm}
        if len(metrics) != len(VALID_WINDOWS):
            continue
        if any(metrics[w]["pnl"] <= 0 for w in VALID_WINDOWS):
            continue
        if metrics["month"]["volume"] < MIN_VOLUME:
            continue
        # Moderate ROI avoids promoting implausible extreme returns alone.
        if metrics["month"]["roi"] <= 0 or metrics["month"]["roi"] > 5:
            continue
        result.append({"address": addr.lower(), "account_value": eq,
                       "day_pnl": metrics["day"]["pnl"], "week_pnl": metrics["week"]["pnl"],
                       "month_pnl": metrics["month"]["pnl"], "month_roi": metrics["month"]["roi"],
                       "month_volume": metrics["month"]["volume"]})
    result.sort(key=lambda x: (-x["month_pnl"], -x["month_volume"], x["address"]))
    # Deduplicate addresses in case the source repeats a wallet.
    unique = []
    seen = set()
    for e in result:
        if e["address"] not in seen:
            unique.append(e)
            seen.add(e["address"])
        if len(unique) >= limit:
            break
    return unique


def recent_fills(wallets, now_ms):
    """Query last day's public fills for shortlisted addresses, never submit orders."""
    fills_out = []
    for wallet in wallets:
        raw = read_json(HYPERLIQUID_URL, {"type": "userFills", "user": wallet["address"]})
        if not isinstance(raw, list):
            raise MarketDataError("Wallet fill response changed")
        recent = []
        for fill in raw:
            if not isinstance(fill, dict):
                continue
            try:
                when = int(fill.get("time", 0))
                px, qty = number(fill.get("px")), number(fill.get("sz"))
                side = str(fill.get("dir", ""))[:32]
                coin = str(fill.get("coin", ""))[:20]
            except (ValueError, TypeError):
                continue
            if now_ms - 86400000 <= when <= now_ms and px is not None and qty is not None and px > 0 and qty > 0:
                recent.append({"time": when, "coin": coin, "side": side,
                               "price": px, "quantity": qty})
        recent.sort(key=lambda x: x["time"], reverse=True)
        fills_out.append({"address": wallet["address"], "fills": recent[:8]})
    return fills_out


def report(wallets, activity, now_ms):
    date = datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# Public wallet research leaderboard", "",
             f"Fetched: {date}", "",
             "**RESEARCH ONLY — NO REAL ORDERS, NO COPY TRADING.**", "",
             "Source: public Hyperliquid leaderboard. Ranking uses *reported* 30-day PnL,",
             "filters for positive daily/weekly/monthly PnL and minimum account size/volume.",
             "Survivorship bias, deposits/withdrawals, leverage, fees and liquidation risk",
             "can invalidate apparent performance. ROI is a source-reported fraction.",
             "", "| Wallet | Account value USD | 30d PnL USD | 30d ROI | 30d volume USD |",
             "|---|---:|---:|---:|---:|"]
    for w in wallets:
        lines.append(f"| \`{w['address']}\` | ${w['account_value']:,.0f} | ${w['month_pnl']:,.0f} | {100*w['month_roi']:.1f}% | ${w['month_volume']:,.0f} |")
    if not wallets:
        lines.append("| No wallets met all provisional filters | — | — | — | — |")
    lines += ["", "## Recent public fills (last 24h)", "",
              "Fills are **observations**, not authorized buy signals or evidence of profit.", "",
              "| Wallet | UTC | Coin | Fill direction | Price USD | Quantity |",
              "|---|---|---|---|---:|---:|"]
    count = 0
    for entry in activity:
        for fill in entry["fills"]:
            dt = datetime.fromtimestamp(fill["time"]/1000, timezone.utc).strftime("%m-%d %H:%M")
            lines.append(f"| \`{entry['address'][:12]}…\` | {dt} | {fill['coin']} | {fill['side']} | ${fill['price']:,.4f} | {fill['quantity']:.4f} |")
            count += 1
    if not count:
        lines.append("| No recent fills | — | — | — | — | — |")
    lines += ["", "The public feed is not audited or guaranteed complete. No wallets are connected or controlled.", ""]
    return "\n".join(lines)


def main(root=Path("."), now_ms=None):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    wallets = shortlist(load_public_board())
    activity = recent_fills(wallets, now_ms)
    output = Path(root) / "research" / "WALLETS.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report(wallets, activity, now_ms), encoding="utf-8")
    print(f"Read-only wallet report saved, {len(wallets)} accounts, no orders submitted.")


if __name__ == "__main__":
    import sys
    try:
        main(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("."))
    except (MarketDataError, OSError, ValueError) as exc:
        print(f"Wallet research not saved: {exc}", file=sys.stderr)
        sys.exit(1)
