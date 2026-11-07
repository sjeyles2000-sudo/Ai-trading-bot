"""Read-only short-term strategy lab: 5m scalping and 15m candlesticks.

Historical, hypothetical fills only. No credentials, signing, real orders,
paper-results branch writes, or changes to the running hourly paper strategy.
"""
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from bot import (BINANCE_URL, HYPERLIQUID_URL, FEE_PCT, SLIPPAGE_PCT,
                 MarketDataError, read_json)

STRATEGIES = {"scalp_5m": ("5m", 300_000, 0.005),
              "engulf_15m": ("15m", 900_000, 0.01)}
MARKETS = ("binance", "hyperliquid")
START_CASH = 10_000.0
MAX_NOTIONAL = 0.02  # maximum 2% of virtual equity for each entry
DAILY_PAUSE = 0.01
HISTORY = 4000  # bounded to Hyperliquid's most recent 5000 candles


def validate(bars, duration, minimum=90):
    if not isinstance(bars, list) or len(bars) < minimum:
        raise MarketDataError(f"Need at least {minimum} consecutive completed candles")
    previous = None
    for bar in bars:
        try:
            ts = bar["end_ms"]
            op, hi, lo, cl, vol = (float(bar[k]) for k in
                                   ("open", "high", "low", "close", "volume"))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MarketDataError("Invalid OHLCV candle") from exc
        if type(ts) is not int or (previous is not None and ts-previous != duration):
            raise MarketDataError("Missing, duplicate or unordered completed candle")
        previous = ts
        if (not all(math.isfinite(v) for v in (op, hi, lo, cl, vol))
                or min(op, hi, lo, cl) <= 0 or vol < 0
                or lo > min(op, cl) or hi < max(op, cl) or lo > hi):
            raise MarketDataError("Invalid candle values")
    return bars


def fetch_history(market, strategy, now_ms):
    """Fetch up to 4000 completed OHLCV candles without trading privileges.

    Binance limits each page to 1000 rows; paginate *backwards* with endTime
    while deduplicating and verifying strict time continuity. Hyperliquid only
    retains its most recent 5000 candles per interval.
    """
    interval, duration, _ = STRATEGIES[strategy]
    if market == "binance":
        all_rows = []
        cursor = now_ms
        while len(all_rows) < HISTORY + 1:
            remaining = HISTORY + 1 - len(all_rows)
            limit = min(1000, remaining)
            params = urlencode({"symbol": "BTCUSDT", "interval": interval,
                                "endTime": cursor, "limit": limit})
            data = read_json(f"{BINANCE_URL}?{params}")
            if not isinstance(data, list) or not data or len(data) > limit:
                raise MarketDataError("Unexpected Binance candle page")
            try:
                new_rows = [{"open_ms": int(r[0]), "end_ms": int(r[6]),
                             "open": float(r[1]), "high": float(r[2]),
                             "low": float(r[3]), "close": float(r[4]),
                             "volume": float(r[5])} for r in data]
            except (TypeError, ValueError, IndexError, OverflowError) as exc:
                raise MarketDataError("Malformed Binance OHLCV") from exc
            if new_rows[0]["open_ms"] > cursor or (
                    all_rows and new_rows[-1]["open_ms"] >= all_rows[0]["open_ms"]):
                raise MarketDataError("Binance pagination cursor did not advance")
            all_rows = new_rows + all_rows
            cursor = new_rows[0]["open_ms"] - 1
            if len(data) < limit:
                break
        bars = [{k:v for k,v in row.items() if k != "open_ms"} for row in all_rows]
    elif market == "hyperliquid":
        data = read_json(HYPERLIQUID_URL, {
            "type": "candleSnapshot", "req": {"coin": "BTC", "interval": interval,
            "startTime": now_ms - (HISTORY + 3)*duration, "endTime": now_ms}})
        if not isinstance(data, list):
            raise MarketDataError("Unexpected Hyperliquid response")
        try:
            bars = [{"end_ms": int(r["T"]), "open": float(r["o"]),
                     "high": float(r["h"]), "low": float(r["l"]),
                     "close": float(r["c"]), "volume": float(r["v"])} for r in data]
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise MarketDataError("Malformed Hyperliquid OHLCV") from exc
    else:
        raise ValueError("Unknown market")
    bars = [b for b in bars if b["end_ms"] <= now_ms][-HISTORY:]
    validate(bars, duration, minimum=300)
    if now_ms - bars[-1]["end_ms"] > 2*duration:
        raise MarketDataError("Market feed stale")
    return bars


def ema(values, window):
    a = 2 / (window + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(value*a + output[-1]*(1-a))
    return output


def signals(bars, strategy):
    closes = [b["close"] for b in bars]
    slow = ema(closes, 21 if strategy == "scalp_5m" else 20)
    fast = ema(closes, 8) if strategy == "scalp_5m" else None
    buy = [False]*len(bars)
    exit_ = [False]*len(bars)
    reasons = [""]*len(bars)
    for i in range(30, len(bars)):
        if strategy == "scalp_5m":
            typical = sum(b["volume"] for b in bars[i-20:i]) / 20
            buy[i] = (fast[i] > slow[i] and fast[i-1] <= slow[i-1]
                      and typical > 0 and bars[i]["volume"] >= 1.1*typical)
            exit_[i] = fast[i] < slow[i] or closes[i] < fast[i]
            reasons[i] = "EMA8 crossed EMA21 with >=1.1x prior volume"
        elif strategy == "engulf_15m":
            prev, curr = bars[i-1], bars[i]
            buy[i] = (prev["close"] < prev["open"] and curr["close"] > curr["open"]
                      and curr["open"] <= prev["close"] and curr["close"] >= prev["open"]
                      and curr["close"] > slow[i])
            exit_[i] = (curr["close"] < slow[i] or
                        (prev["close"] > prev["open"] and curr["close"] < curr["open"]
                         and curr["open"] >= prev["close"]
                         and curr["close"] <= prev["open"]))
            reasons[i] = "Bullish engulfing candle above EMA20"
        else:
            raise ValueError("Unknown strategy")
    return buy, exit_, reasons


def simulate(bars, strategy, first_bar=32, last_bar=None, signal_override=None,
             fee_pct=FEE_PCT, slippage_pct=SLIPPAGE_PCT):
    """Independent long-only account. All signal fills occur at NEXT bar open."""
    duration, stop_pct = STRATEGIES[strategy][1:]
    if not (0 <= fee_pct <= 0.01 and 0 <= slippage_pct <= 0.01):
        raise ValueError("Invalid hypothetical cost assumption")
    validate(bars, duration)
    last_bar = len(bars) if last_bar is None else last_bar
    if not (32 <= first_bar < last_bar <= len(bars)):
        raise ValueError("Invalid simulation window")
    entry, exit_, reasons = signal_override or signals(bars, strategy)
    if any(len(x) != len(bars) for x in (entry, exit_, reasons)):
        raise ValueError("Invalid signal lengths")
    cash, units, stop, paid = START_CASH, 0.0, 0.0, 0.0
    equity, pnls, events = [], [], []
    utc_day, day_start = None, START_CASH
    paused, emergency_exit = False, False
    for i in range(first_bar, last_bar):
        bar = bars[i]
        if utc_day != datetime.fromtimestamp(bar["end_ms"]/1000, timezone.utc).date():
            utc_day = datetime.fromtimestamp(bar["end_ms"]/1000, timezone.utc).date()
            day_start = cash + units*bar["open"]
            paused = False
        exited = False

        def sell(action, raw_price):
            nonlocal cash, units, stop, paid, exited
            price = raw_price*(1-slippage_pct)
            amount = units*price*(1-fee_pct)
            pnl = amount-paid
            cash += amount
            pnls.append(pnl)
            events.append((i, action, round(price, 6), round(pnl, 6)))
            units, stop, paid, exited = 0.0, 0.0, 0.0, True

        # Risk-triggered liquidation is delayed to next bar open; not assumed
        # to be filled at the previous close.
        if units and emergency_exit:
            sell("DAILY LOSS EXIT", bar["open"])
        elif units and exit_[i-1]:
            sell("SIGNAL EXIT", bar["open"])
        elif units and bar["low"] <= stop:
            sell("STOP EXIT", min(bar["open"], stop))
        emergency_exit = False
        if not units and not exited and not paused and entry[i-1]:
            budget = min(cash, cash*MAX_NOTIONAL)
            if budget > 0:
                price = bar["open"]*(1+slippage_pct)
                units = budget/(price*(1+fee_pct))
                paid = budget
                cash -= budget
                stop = price*(1-stop_pct)
                events.append((i, "BUY: "+reasons[i-1], round(price, 6), 0.0))
                # Conservative when entry and stop are touched within one candle.
                if bar["low"] <= stop:
                    sell("ENTRY BAR STOP", min(bar["open"], stop))
        marked = cash + units*bar["close"]
        equity.append(marked)
        if marked <= day_start*(1-DAILY_PAUSE):
            paused = True
            emergency_exit = bool(units)
    top, drawdown = START_CASH, 0.0
    for value in equity:
        top = max(top, value)
        drawdown = max(drawdown, (top-value)/top)
    wins = sum(p > 0 for p in pnls)
    profits = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    return {"return_pct": 100*(equity[-1]/START_CASH-1),
            "max_drawdown_pct": 100*drawdown, "closed_trades": len(pnls),
            "win_rate_pct": 100*wins/len(pnls) if pnls else None,
            "profit_factor": profits/losses if losses else None,
            "open_position": bool(units), "events": events, "equity": equity}


def compare(bars, strategy, fee_pct=FEE_PCT, slippage_pct=SLIPPAGE_PCT):
    validate(bars, STRATEGIES[strategy][1], minimum=300)
    split = (len(bars)*7)//10
    # Predefined, consecutive thirds of the untouched 30% holdout.
    # Fresh virtual capital at every boundary; only earlier bars warm indicators.
    # This is a stability diagnostic, NOT parameter selection or three independent
    # market regimes. Never choose the best window or tune on these outcomes.
    windows = []
    # Require at least 90 completed bars per segment (simulate's minimum).
    # Smaller fixtures and real-world partial samples report N/A, not invented
    # stability estimates from statistically tiny windows.
    if len(bars)-split >= 270:
        for index in range(3):
            first = split + (len(bars)-split)*index//3
            last = split + (len(bars)-split)*(index+1)//3
            windows.append({"start": first, "end": last,
                            "stats": simulate(bars, strategy, first_bar=first,
                                              last_bar=last, fee_pct=fee_pct,
                                              slippage_pct=slippage_pct)})
    return {"train": simulate(bars, strategy, last_bar=split,
                              fee_pct=fee_pct, slippage_pct=slippage_pct),
            "holdout": simulate(bars, strategy, first_bar=split,
                                fee_pct=fee_pct, slippage_pct=slippage_pct),
            "windows": windows, "split": split}


def report(results, now_ms):
    date = datetime.fromtimestamp(now_ms/1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# 5m scalping vs 15m candlestick test", "",
             f"Generated: {date}", "",
             "**VIRTUAL HISTORICAL RESEARCH ONLY — no real orders, credentials or paper ledger writes.**",
             "", "## Strategy decision tree", "",
             "1. Validate fresh consecutive public OHLCV data, otherwise stop.",
             "2. Use 5m EMA8/EMA21 bullish crossover with >=1.1x prior 20-candle volume, "
             "or 15m bullish engulfing above EMA20.",
             "3. If a signal exists on a COMPLETED candle and no virtual position is open, "
             "hypothetically buy at the NEXT candle open, with costs.",
             "4. Exit on a later signal, a stop, or daily-loss halt; never claim an exact market fill.",
             "5. Review win rate, drawdown, profitability AFTER fees and a separate untouched holdout.",
             "", "## Four market/strategy tests", "",
             f"Per side: {100*FEE_PCT:.2f}% hypothetical fee and "
             f"{100*SLIPPAGE_PCT:.2f}% hypothetical slippage.",
             "Virtual starting cash $10,000 per independent test, max 2% unleveraged position; "
             "stop 0.5% (5m) or 1% (15m), 1% daily-loss pause/next-bar exit.",
             "Fixed parameters; no optimization. 70% training/30% chronological holdout "
             "with fresh holdout virtual cash and indicator warmup.", "",
             "| Market | Strategy | Segment | Return | Max drawdown | Closed trades | Win rate | Profit factor |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for market in MARKETS:
        for strategy in STRATEGIES:
            for name in ("train", "holdout"):
                s = results[(market, strategy)][name]
                win = "N/A" if s["win_rate_pct"] is None else f"{s['win_rate_pct']:.1f}%"
                pf = "N/A" if s["profit_factor"] is None else f"{s['profit_factor']:.2f}"
                lines.append(f"| {market} | {strategy} | {name} | {s['return_pct']:+.3f}% | "
                             f"{s['max_drawdown_pct']:.3f}% | {s['closed_trades']} | {win} | {pf} |")
    lines.extend(["", "## Holdout robustness: doubled trading costs", "",
                  "The same fixed signals are independently rerun with 0.20% fees + 0.10% "
                  "slippage PER SIDE; positive base results are not enough if stress is negative.",
                  "", "| Market | Strategy | Completed bars | Base holdout | 2x cost holdout |",
                  "|---|---|---:|---:|---:|"])
    for market in MARKETS:
        for strategy in STRATEGIES:
            result = results[(market, strategy)]
            lines.append(f"| {market} | {strategy} | {result['history_count']} | "
                         f"{result['holdout']['return_pct']:+.3f}% | "
                         f"{result['stress_holdout']['return_pct']:+.3f}% |")
    lines.extend(["", "## Out-of-sample stability: three consecutive holdout windows", "",
                  "The fixed final 30% holdout is subdivided chronologically into "
                  "three disjoint windows. Each starts with fresh virtual $10,000; "
                  "results are **not additive** to the continuous holdout result. "
                  "Prior candles warm up indicators only. No parameters are tuned "
                  "or strategies chosen using these windows.", "",
                  "| Market | Strategy | Holdout window | Return after costs | Max drawdown | Closed trades |",
                  "|---|---|---:|---:|---:|---:|"])
    for market in MARKETS:
        for strategy in STRATEGIES:
            windows = results[(market, strategy)]["windows"]
            if not windows:
                lines.append(f"| {market} | {strategy} | N/A (insufficient bars) | N/A | N/A | N/A |")
            for index, window in enumerate(windows, start=1):
                stats = window["stats"]
                lines.append(f"| {market} | {strategy} | {index}/3 | "
                             f"{stats['return_pct']:+.3f}% | "
                             f"{stats['max_drawdown_pct']:.3f}% | "
                             f"{stats['closed_trades']} |")
    lines += ["", "## Critical review", "",
              "- **Stability diagnostic:** multiple non-overlapping windows can expose "
              "fragility but the small samples and shared BTC exposure do not "
              "establish independent market-regime validation.",
              "- **Zero-trade windows:** a zero return with no closed trades is "
              "insufficient evidence of a profitable strategy.",
              "- **Data limitations:** 4000 5m bars spans at most ~14 days and 4000 15m bars "
              "at most ~42 days. This is still insufficient to identify a reliable winner across market regimes.",
              "- **Trade model limitations:** no funding, order book depth, latency, spreads beyond "
              "assumed slippage, liquidation, real fills or actual market impact.",
              "- **No cherry-picking:** do not tune on holdout data then call it unbiased. "
              "Win rate and gross returns alone cannot establish an edge.",
              "- **N/A metrics:** no closed trades or no losing trades does NOT imply strong performance.",
              "- **Risk:** scalping can lose money even with a high win rate because costs are frequent.",
              "- **Next decision:** continue paper testing with longer and varied market history; "
              "do not enable real trading based on these results.", "",
              "This report does not change the existing hourly demo strategy.", ""]
    return "\n".join(lines)


def run(path=Path("backtest-results/short-term.md"), now_ms=None, fetcher=fetch_history):
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    results = {}
    # Fail closed: all four feeds/results must validate before writing anything.
    for market in MARKETS:
        for strategy in STRATEGIES:
            bars = fetcher(market, strategy, now_ms)
            result = compare(bars, strategy)
            result["history_count"] = len(bars)
            result["stress_holdout"] = simulate(
                bars, strategy, first_bar=result["split"],
                fee_pct=FEE_PCT*2, slippage_pct=SLIPPAGE_PCT*2)
            results[(market, strategy)] = result
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report(results, now_ms), encoding="utf-8")
    return results


if __name__ == "__main__":
    try:
        run()
        print(Path("backtest-results/short-term.md").read_text(encoding="utf-8"))
    except (MarketDataError, ValueError, OSError) as exc:
        print(f"SHORT-TERM RESEARCH FAILED: {exc}")
        raise SystemExit(1)
