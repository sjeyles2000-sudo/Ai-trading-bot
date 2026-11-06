"""Read public exchange candles and replay PAPER trades only. No order API."""
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

DEMO_MODE = True
STARTING_BALANCE = 10000.0
MAX_POSITION_PCT = 0.02
STOP_LOSS_PCT = 0.02
DAILY_LOSS_LIMIT_PCT = 0.01
FEE_PCT = 0.001  # Assumption, not actual fees
SLIPPAGE_PCT = 0.0005  # Assumption
SHORT_WINDOW = 5
LONG_WINDOW = 20
INTERVAL_MS = 3600000
HISTORY_CANDLES = 120
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"


class MarketDataError(Exception):
    """Reject missing, invalid, or stale public data."""


def read_json(url, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=body, headers={
        "User-Agent": "ai-trading-bot-paper/1.0",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if body is not None else {}),
    })
    try:
        with urlopen(req, timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError, TimeoutError, URLError, HTTPError) as exc:
        raise MarketDataError(f"Public data request failed: {exc}") from exc


def validate_candles(raw, now_ms):
    if not isinstance(raw, list):
        raise MarketDataError("Unexpected candle response")
    candles = []
    for row in raw:
        try:
            candle = {"end_ms": int(row["end_ms"]),
                      **{key: float(row[key]) for key in ("open", "high", "low", "close")}}
        except (TypeError, KeyError, ValueError, OverflowError) as exc:
            raise MarketDataError("Malformed candle") from exc
        prices = [candle[k] for k in ("open", "high", "low", "close")]
        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise MarketDataError("Invalid price")
        if candle["low"] > min(candle["open"], candle["close"]) or candle["high"] < max(candle["open"], candle["close"]) or candle["low"] > candle["high"]:
            raise MarketDataError("Inconsistent OHLC candle")
        if candle["end_ms"] <= now_ms:
            candles.append(candle)
    candles.sort(key=lambda c: c["end_ms"])
    if len({c["end_ms"] for c in candles}) != len(candles):
        raise MarketDataError("Duplicate timestamps")
    candles = candles[-HISTORY_CANDLES:]
    if len(candles) < LONG_WINDOW + 2:
        raise MarketDataError("Too few completed candles")
    if now_ms - candles[-1]["end_ms"] > 3 * INTERVAL_MS:
        raise MarketDataError("Stale market data")
    if any(b["end_ms"] - a["end_ms"] > INTERVAL_MS + 2000
           for a, b in zip(candles, candles[1:])):
        raise MarketDataError("Missing hourly candles")
    return candles


def fetch_binance(now_ms):
    params = urlencode({"symbol": "BTCUSDT", "interval": "1h", "limit": HISTORY_CANDLES + 3})
    rows = read_json(f"{BINANCE_URL}?{params}")
    if not isinstance(rows, list):
        raise MarketDataError("Invalid Binance response")
    try:
        candles = [{"end_ms": r[6], "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in rows]
    except (IndexError, TypeError) as exc:
        raise MarketDataError("Malformed Binance data") from exc
    return validate_candles(candles, now_ms)


def fetch_hyperliquid(now_ms):
    rows = read_json(HYPERLIQUID_URL, {
        "type": "candleSnapshot",
        "req": {"coin": "BTC", "interval": "1h",
                "startTime": now_ms - (HISTORY_CANDLES + 3) * INTERVAL_MS,
                "endTime": now_ms},
    })
    if not isinstance(rows, list):
        raise MarketDataError("Invalid Hyperliquid response")
    try:
        candles = [{"end_ms": r["T"], "open": r["o"], "high": r["h"], "low": r["l"], "close": r["c"]} for r in rows]
    except (TypeError, KeyError) as exc:
        raise MarketDataError("Malformed Hyperliquid data") from exc
    return validate_candles(candles, now_ms)


def simulate(market, candles, verbose=True):
    """Replay completed candles with a hypothetical long-only account."""
    cash, units, stop_price = STARTING_BALANCE, 0.0, 0.0
    trades, halted, today = 0, False, None
    day_open_equity = STARTING_BALANCE

    def report(action, quantity, price):
        if verbose:
            print(f"{market}: PAPER {action} {quantity:.6f} BTC at ${price:,.2f}")

    for index in range(LONG_WINDOW, len(candles)):
        candle = candles[index]
        close = candle["close"]
        day = datetime.fromtimestamp(candle["end_ms"] / 1000, timezone.utc).date()
        if day != today:
            today, halted = day, False
            day_open_equity = cash + units * candle["open"]
        closes = [c["close"] for c in candles[index - LONG_WINDOW:index + 1]]
        short = sum(closes[-SHORT_WINDOW:]) / SHORT_WINDOW
        long = sum(closes[-LONG_WINDOW:]) / LONG_WINDOW
        prev_short = sum(closes[-SHORT_WINDOW - 1:-1]) / SHORT_WINDOW
        prev_long = sum(closes[-LONG_WINDOW - 1:-1]) / LONG_WINDOW

        if units and candle["low"] <= stop_price:
            fill = min(candle["open"], stop_price) * (1 - SLIPPAGE_PCT)
            report("STOP SELL", units, fill)
            cash += units * fill * (1 - FEE_PCT)
            units, stop_price = 0.0, 0.0
            trades += 1
        elif units and short < long:
            fill = close * (1 - SLIPPAGE_PCT)
            report("SELL", units, fill)
            cash += units * fill * (1 - FEE_PCT)
            units, stop_price = 0.0, 0.0
            trades += 1

        equity = cash + units * close
        if equity <= day_open_equity * (1 - DAILY_LOSS_LIMIT_PCT):
            if units:
                fill = close * (1 - SLIPPAGE_PCT)
                report("DAILY LIMIT SELL", units, fill)
                cash += units * fill * (1 - FEE_PCT)
                units, stop_price = 0.0, 0.0
                trades += 1
            halted = True
        if not units and not halted and short > long and prev_short <= prev_long:
            allocation = min(cash, equity * MAX_POSITION_PCT)
            if allocation > 0:
                fill = close * (1 + SLIPPAGE_PCT)
                units = allocation / (fill * (1 + FEE_PCT))
                cash -= allocation
                stop_price = fill * (1 - STOP_LOSS_PCT)
                trades += 1
                report("BUY", units, fill)

    equity = cash + units * candles[-1]["close"]
    if verbose:
        print(f"{market}: historical paper equity ${equity:,.2f}; simulated transactions {trades}")
    return {"equity": equity, "trades": trades, "units": units}


def main():
    assert DEMO_MODE is True
    print("READ-ONLY HISTORICAL PAPER SIMULATION; NO REAL ORDERS")
    print("Not continuous live trading. Virtual balances reset every run.")
    now_ms = int(time.time() * 1000)
    successes = 0
    for name, fetch in (("Binance BTC/USDT spot", fetch_binance),
                        ("Hyperliquid BTC perpetual", fetch_hyperliquid)):
        try:
            candles = fetch(now_ms)
            print(f"{name}: {len(candles)} completed hourly candles")
            simulate(name, candles)
            successes += 1
        except MarketDataError as exc:
            print(f"{name}: SKIPPED - {exc}")
    return 0 if successes == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
