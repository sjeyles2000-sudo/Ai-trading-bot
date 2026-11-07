"""Scheduled, persistent, read-only PAPER trader. No credentials or order endpoints."""
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bot import (
    DEMO_MODE, STARTING_BALANCE, SHORT_WINDOW, LONG_WINDOW, INTERVAL_MS,
    MAX_POSITION_PCT, STOP_LOSS_PCT, DAILY_LOSS_LIMIT_PCT, FEE_PCT,
    SLIPPAGE_PCT, MarketDataError, fetch_binance, fetch_hyperliquid,
)

MARKETS = {"binance": ("Binance BTC/USDT spot", fetch_binance),
           "hyperliquid": ("Hyperliquid BTC perpetual", fetch_hyperliquid)}
STATE_VERSION = 1
TRADE_FIELDS = ["time_utc", "market", "side", "quantity_btc", "virtual_price_usd", "virtual_fee_usd", "virtual_equity_usd"]
EQUITY_FIELDS = ["time_utc", "market", "virtual_equity_usd", "virtual_cash_usd", "btc_units"]


def timestamp(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_account():
    return {"cash": STARTING_BALANCE, "units": 0.0, "entry_price": 0.0,
            "stop_price": 0.0, "last_candle_ms": 0, "utc_day": "",
            "day_start_equity": STARTING_BALANCE, "paused": False, "trades": 0}


def check_account(s):
    required = set(empty_account())
    if not isinstance(s, dict) or set(s) != required:
        raise MarketDataError("Invalid saved virtual account structure")
    for key in ("cash", "units", "entry_price", "stop_price", "day_start_equity"):
        v = s[key]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
            raise MarketDataError("Invalid virtual account value: " + key)
    if not isinstance(s["last_candle_ms"], int) or s["last_candle_ms"] < 0:
        raise MarketDataError("Invalid saved candle timestamp")
    if not isinstance(s["trades"], int) or s["trades"] < 0:
        raise MarketDataError("Invalid saved trade count")
    if not isinstance(s["paused"], bool) or not isinstance(s["utc_day"], str):
        raise MarketDataError("Invalid saved daily risk state")
    if s["units"] > 0 and (s["entry_price"] <= 0 or s["stop_price"] <= 0):
        raise MarketDataError("Position has no entry or stop")
    if s["units"] == 0 and (s["entry_price"] != 0 or s["stop_price"] != 0):
        raise MarketDataError("Flat account has entry or stop")


def load_state(path):
    if not path.exists():
        return {market: empty_account() for market in MARKETS}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MarketDataError("Cannot load saved paper state") from exc
    if not isinstance(doc, dict) or doc.get("version") != STATE_VERSION or set(doc.get("markets", {})) != set(MARKETS):
        raise MarketDataError("Saved paper state has an unexpected version or markets")
    for account in doc["markets"].values():
        check_account(account)
    return doc["markets"]


def process_candles(market, account, candles):
    """Replay only newly closed candles; no exchange order methods exist."""
    check_account(account)
    state = dict(account)
    last = state["last_candle_ms"]
    if last:
        times = [c["end_ms"] for c in candles]
        if last > times[-1]:
            raise MarketDataError("Market data is behind saved paper state")
        if last not in times:
            raise MarketDataError("Saved state older than available candles; manual review required")
        first = times.index(last) + 1
    else:
        # Begin from the most recent closed candle: no backdated paper profits.
        first = len(candles) - 1
    events, equity_rows = [], []
    for index in range(first, len(candles)):
        if index < LONG_WINDOW:
            raise MarketDataError("Not enough completed history for a paper decision")
        c = candles[index]
        prev = candles[index - LONG_WINDOW:index + 1]
        short = sum(x["close"] for x in prev[-SHORT_WINDOW:]) / SHORT_WINDOW
        long = sum(x["close"] for x in prev[-LONG_WINDOW:]) / LONG_WINDOW
        prev_short = sum(x["close"] for x in prev[-SHORT_WINDOW - 1:-1]) / SHORT_WINDOW
        prev_long = sum(x["close"] for x in prev[-LONG_WINDOW - 1:-1]) / LONG_WINDOW
        day = timestamp(c["end_ms"])[:10]
        if day != state["utc_day"]:
            state["utc_day"] = day
            state["paused"] = False
            state["day_start_equity"] = state["cash"] + state["units"] * c["open"]
        exited = False

        def sell(side, fill):
            nonlocal exited
            quantity = state["units"]
            fee = quantity * fill * FEE_PCT
            state["cash"] += quantity * fill - fee
            state["units"] = 0.0
            state["entry_price"] = 0.0
            state["stop_price"] = 0.0
            state["trades"] += 1
            exited = True
            events.append([timestamp(c["end_ms"]), market, side,
                           f"{quantity:.8f}", f"{fill:.4f}", f"{fee:.4f}", f"{state['cash']:.4f}"])

        if state["units"] > 0 and c["low"] <= state["stop_price"]:
            sell("STOP SELL", min(c["open"], state["stop_price"]) * (1 - SLIPPAGE_PCT))
        elif state["units"] > 0 and short < long:
            sell("SIGNAL SELL", c["close"] * (1 - SLIPPAGE_PCT))

        equity = state["cash"] + state["units"] * c["close"]
        if equity <= state["day_start_equity"] * (1 - DAILY_LOSS_LIMIT_PCT):
            if state["units"] > 0:
                sell("DAILY LIMIT SELL", c["close"] * (1 - SLIPPAGE_PCT))
            state["paused"] = True

        if not exited and state["units"] == 0 and not state["paused"] and short > long and prev_short <= prev_long:
            equity = state["cash"]
            allocation = min(state["cash"], equity * MAX_POSITION_PCT)
            if allocation > 0:
                fill = c["close"] * (1 + SLIPPAGE_PCT)
                qty = allocation / (fill * (1 + FEE_PCT))
                fee = qty * fill * FEE_PCT
                state["cash"] -= allocation
                state["units"] = qty
                state["entry_price"] = fill
                state["stop_price"] = fill * (1 - STOP_LOSS_PCT)
                state["trades"] += 1
                events.append([timestamp(c["end_ms"]), market, "BUY", f"{qty:.8f}",
                               f"{fill:.4f}", f"{fee:.4f}",
                               f"{state['cash'] + qty * c['close']:.4f}"])
        state["last_candle_ms"] = c["end_ms"]
        equity_rows.append([timestamp(c["end_ms"]), market,
                            f"{state['cash'] + state['units'] * c['close']:.4f}",
                            f"{state['cash']:.4f}", f"{state['units']:.8f}"])
    check_account(state)
    return state, events, equity_rows


def append_csv(path, fields, rows):
    exists = path.exists()
    if not rows and exists:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(fields)
        writer.writerows(rows)


def run(data_dir, fetchers=None, now_ms=None):
    if DEMO_MODE is not True:
        raise MarketDataError("Demo-only lock is not enabled")
    data_dir = Path(data_dir)
    existing = load_state(data_dir / "ledger" / "state.json")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    fetchers = fetchers if fetchers is not None else MARKETS
    updates, events, equities, prices = {}, [], [], {}
    # Fail closed: no state commits unless both exchange reads succeed.
    for key, (display, fetch) in fetchers.items():
        candles = fetch(now_ms)
        new, trades, snapshots = process_candles(display, existing[key], candles)
        updates[key] = new
        events.extend(trades)
        equities.extend(snapshots)
        prices[key] = candles[-1]["close"]

    led = data_dir / "ledger"
    led.mkdir(parents=True, exist_ok=True)
    (led / "state.json").write_text(json.dumps({"version": STATE_VERSION, "markets": updates}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_csv(led / "trades.csv", TRADE_FIELDS, events)
    append_csv(led / "equity.csv", EQUITY_FIELDS, equities)
    rows = ["# Paper trading dashboard", "", "**VIRTUAL FUNDS ONLY — NO REAL ORDERS.**",
            "", f"Updated UTC: {datetime.fromtimestamp(now_ms / 1000, timezone.utc):%Y-%m-%d %H:%M}", "",
            "| Market | Paper balance (USD) | Change from $10k | Virtual BTC | Simulated transactions | Latest candle UTC |",
            "|---|---:|---:|---:|---:|---|"]
    for key, (display, _) in fetchers.items():
        state = updates[key]
        equity = state["cash"] + state["units"] * prices[key]
        rows.append(f"| {display} | ${equity:,.2f} | {100 * (equity / STARTING_BALANCE - 1):+.2f}% | {state['units']:.6f} | {state['trades']} | {timestamp(state['last_candle_ms'])} |")
    rows += ["", "Trade log: [trades.csv](trades.csv) · Equity history: [equity.csv](equity.csv)",
             "", "Illustrative fills use assumed fees and slippage; not actual exchange execution or guaranteed performance."]
    report = "\n".join(rows) + "\n"
    (led / "REPORT.md").write_text(report, encoding="utf-8")
    print(report)
    return updates


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("."))
    except (MarketDataError, OSError, ValueError) as exc:
        print(f"PAPER RUN NOT SAVED: {exc}", file=sys.stderr)
        raise SystemExit(1)
