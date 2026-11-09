"""Read-only 1-minute BTC breakout research, NOT a copied proprietary system.

A documented HYPOTHESIS: completed 5m EMA50 trend filter + 1m close above
previous ten 1m highs, with local-support stop and a 3R price target.
LONG ONLY, 2% max virtual notional. No credentials, orders or ledger writes.
"""
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from bot import BINANCE_URL, HYPERLIQUID_URL, MarketDataError, read_json

MINUTE = 60_000
HISTORY = 4_000                 # Hyperliquid only exposes 5,000 recent candles
START_CASH = 10_000.0
NOTIONAL = 0.02
FEE = 0.001
SLIPPAGE = 0.0005
R_MULTIPLE = 3.0
MAX_HOLD_MINUTES = 30
WARMUP = 270                    # >=50 fully completed five-minute bars


def validate(bars, minimum=320):
    if not isinstance(bars, list) or len(bars) < minimum:
        raise MarketDataError("Insufficient consecutive one-minute data")
    prev = None
    for bar in bars:
        try:
            stamp = bar["end_ms"]
            op, hi, lo, close = (float(bar[k]) for k in ("open", "high", "low", "close"))
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            raise MarketDataError("Malformed minute candle") from exc
        if type(stamp) is not int or stamp % MINUTE != MINUTE - 1:
            raise MarketDataError("Unaligned minute timestamp")
        if prev is not None and stamp - prev != MINUTE:
            raise MarketDataError("Missing, duplicated, or unordered minute candles")
        if (not all(math.isfinite(v) and v > 0 for v in (op, hi, lo, close))
                or lo > min(op, close) or max(op, close) > hi):
            raise MarketDataError("Invalid minute OHLC")
        prev = stamp


def fetch(market, now_ms=None, reader=read_json):
    """Use public Binance and Hyperliquid OHLCV; never call authenticated APIs."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if market == "binance":
        rows, cursor = [], now_ms
        while len(rows) < HISTORY + 2:
            limit = min(1000, HISTORY + 2 - len(rows))
            query = urlencode({"symbol": "BTCUSDT", "interval": "1m",
                               "limit": limit, "endTime": cursor})
            raw = reader(BINANCE_URL + "?" + query)
            if not isinstance(raw, list) or not raw or len(raw) > limit:
                raise MarketDataError("Unusable Binance minute page")
            try:
                page = [dict(open_ms=int(r[0]), end_ms=int(r[6]),
                             open=float(r[1]), high=float(r[2]),
                             low=float(r[3]), close=float(r[4])) for r in raw]
            except (TypeError, ValueError, IndexError, OverflowError) as exc:
                raise MarketDataError("Malformed Binance minute page") from exc
            if (any(b["open_ms"] <= a["open_ms"] for a, b in zip(page, page[1:]))
                    or (rows and page[-1]["open_ms"] >= rows[0]["open_ms"])):
                raise MarketDataError("Overlapping or unordered Binance pages")
            rows = page + rows
            cursor = page[0]["open_ms"] - 1
            if len(raw) < limit:
                break
        bars = [{k: v for k, v in row.items() if k != "open_ms"} for row in rows]
    elif market == "hyperliquid":
        raw = reader(HYPERLIQUID_URL, {"type": "candleSnapshot",
                     "req": {"coin": "BTC", "interval": "1m",
                             "startTime": now_ms - (HISTORY + 3) * MINUTE,
                             "endTime": now_ms}})
        if not isinstance(raw, list):
            raise MarketDataError("Unusable Hyperliquid minute feed")
        try:
            bars = [dict(end_ms=int(r["T"]), open=float(r["o"]),
                         high=float(r["h"]), low=float(r["l"]),
                         close=float(r["c"])) for r in raw]
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            raise MarketDataError("Malformed Hyperliquid minute feed") from exc
    else:
        raise ValueError("Unknown market")
    bars = [b for b in bars if b["end_ms"] <= now_ms][-HISTORY:]
    if len(bars) != HISTORY:
        raise MarketDataError("Need 4000 completed one-minute candles")
    validate(bars)
    if not 0 <= now_ms - bars[-1]["end_ms"] <= 3 * MINUTE:
        raise MarketDataError("Stale or future-dated minute data")
    return bars


def closed_bar_signals(bars):
    """All signals use data available by bar i close; fill only on i+1 open.

    The 5m EMA is updated only at completed five-minute boundaries; it
    never uses an incomplete 5m candle.
    """
    validate(bars)
    alpha = 2 / 51
    count, ema, last_five_close = 0, None, None
    filtered, unfiltered, supports = [], [], []
    for i, bar in enumerate(bars):
        if (bar["end_ms"] + 1) % (5 * MINUTE) == 0:
            last_five_close = bar["close"]
            ema = (last_five_close if ema is None else
                   alpha * last_five_close + (1-alpha) * ema)
            count += 1
        if i < WARMUP:
            filtered.append(False); unfiltered.append(False); supports.append(None)
            continue
        resistance = max(x["high"] for x in bars[i-10:i])
        support = min(x["low"] for x in bars[i-9:i+1])
        breakout = bar["close"] > resistance
        bullish = count >= 50 and last_five_close > ema
        unfiltered.append(breakout)
        filtered.append(breakout and bullish)
        supports.append(support)
    return {"filtered": filtered, "unfiltered": unfiltered, "supports": supports}


def simulate(bars, strategy="filtered", first=None, last=None,
             fee=FEE, slippage=SLIPPAGE, signal_data=None):
    """Next-open hypothetical fills; ambiguous stop/target bar exits at STOP first."""
    validate(bars)
    if strategy not in ("filtered", "unfiltered"):
        raise ValueError("Unknown minute strategy")
    if not (0 <= fee <= 0.01 and 0 <= slippage <= 0.01):
        raise ValueError("Invalid hypothetical transaction costs")
    first = WARMUP + 1 if first is None else first
    last = len(bars) if last is None else last
    if not (WARMUP + 1 <= first < last <= len(bars)):
        raise ValueError("Invalid independent simulation window")
    signal_data = closed_bar_signals(bars) if signal_data is None else signal_data
    if (len(signal_data[strategy]) != len(bars)
            or len(signal_data["supports"]) != len(bars)):
        raise ValueError("Invalid signal data")
    cash, units, paid, stop, target, entry_i = START_CASH, 0., 0., 0., 0., -1
    pnl, sampled_equity, entries = [], [], 0

    def sell(price):
        nonlocal cash, units, paid, stop, target, entry_i
        proceeds = units * price * (1 - slippage) * (1 - fee)
        pnl.append(proceeds - paid)
        cash += proceeds
        units, paid, stop, target, entry_i = 0., 0., 0., 0., -1

    for i in range(first, last):
        bar = bars[i]
        exited = False
        if units:
            if bar["open"] <= stop:
                sell(bar["open"]); exited = True
            elif bar["low"] <= stop:
                sell(stop); exited = True
            elif bar["high"] >= target:
                sell(target); exited = True
            elif i - entry_i >= MAX_HOLD_MINUTES:
                sell(bar["open"]); exited = True
        if not units and not exited and signal_data[strategy][i-1]:
            candidate = signal_data["supports"][i-1]
            fill = bar["open"] * (1 + slippage)
            if candidate is not None:
                distance = (fill - candidate) / fill
                # Disallow unrealistically tight or uncontrolled price stops.
                if 0.0004 <= distance <= 0.004:
                    allocation = min(cash, NOTIONAL * cash)
                    if allocation > 0:
                        units = allocation / (fill * (1 + fee))
                        paid = allocation
                        cash -= allocation
                        stop = candidate
                        target = fill + R_MULTIPLE * (fill - stop)
                        entry_i = i
                        entries += 1
                        # OHLC ordering unknown. Conservative same-bar stop priority.
                        if bar["low"] <= stop:
                            sell(min(bar["open"], stop))
                        elif bar["high"] >= target:
                            sell(target)
        sampled_equity.append(cash + units * bar["close"])
    if units:
        sell(bars[last-1]["close"])   # liquidation cost in standalone comparison
        sampled_equity[-1] = cash

    peak, worst = START_CASH, 0.
    for equity in sampled_equity:
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    gains = sum(p for p in pnl if p > 0)
    losses = -sum(p for p in pnl if p < 0)
    return {"net_return_pct": 100 * (cash / START_CASH - 1),
            "max_sampled_dd_pct": 100 * worst, "trades": len(pnl),
            "entries": entries, "win_pct": 100*sum(p > 0 for p in pnl)/len(pnl)
            if pnl else None,
            "profit_factor": gains/losses if losses > 0 else None}


def compare(bars):
    validate(bars)
    if len(bars) < 1000:
        raise MarketDataError("Insufficient bars for independent holdout")
    split = int(len(bars) * 0.7)
    signals = closed_bar_signals(bars)
    result = {}
    for mode in ("filtered", "unfiltered"):
        result[mode] = {
            "train": simulate(bars, mode, last=split, signal_data=signals),
            "holdout": simulate(bars, mode, first=split, signal_data=signals),
            "double_cost": simulate(bars, mode, first=split,
                                    fee=2*FEE, slippage=2*SLIPPAGE,
                                    signal_data=signals)}
    return result


def render(markets):
    lines = [
        "# Research-only one-minute BTC scalping comparison", "",
        "**NO REAL TRADES, NO API KEYS, NO ORDERS. Historical hypotheses, not signals.**",
        "This is a *specified research hypothesis*, NOT independently verified",
        "as the exact rules or profitability of the MambaFx video.",
        "4,000 consecutive completed 1m BTC candles (~2.8 days) per venue;",
        "70/30 chronological train/holdout with fresh virtual capital.",
        "Compare one-minute close above prior 10 one-minute highs, with",
        "versus without a completed five-minute EMA50 bullish filter.",
        "Long-only virtual BTC (not actual Hyperliquid perpetual fills).",
        "Stop at signal bar/prior 9-bar local low; skip price-risk outside",
        "0.04%-0.40%. Target 3 times entry-to-stop price distance.",
        "Next-minute OPEN entry; conservative STOP-first ambiguous bars;",
        "maximum 30-minute hold; 2% virtual notional per entry.",
        "Cost assumption: fee 0.10% and slippage 0.05% per side,",
        "plus doubled-cost holdout stress; funding/spread/impact NOT modeled.",
        "Sample is far too short for a profitability claim; do NOT",
        "promote from an inspected holdout or switch on live trading.", "",
        "| Venue | Mode | Sample | Net return | Sampled max DD | Closed | Win rate | Profit factor |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for venue, results in markets.items():
        for mode in ("filtered", "unfiltered"):
            for period in ("train", "holdout", "double_cost"):
                value = results[mode][period]
                win = "N/A" if value["win_pct"] is None else f'{value["win_pct"]:.1f}%'
                pf = "N/A" if value["profit_factor"] is None else f'{value["profit_factor"]:.2f}'
                lines.append(f'| {venue} | {mode} | {period} | '
                             f'{value["net_return_pct"]:+.4f}% | '
                             f'{value["max_sampled_dd_pct"]:.4f}% | '
                             f'{value["trades"]} | {win} | {pf} |')
    return "\n".join(lines) + "\n"


def run(path=Path("minute-research/REPORT.md"), feeds=None):
    feeds = feeds or {"Binance spot": lambda now: fetch("binance", now),
                     "Hyperliquid perp": lambda now: fetch("hyperliquid", now)}
    now = int(time.time() * 1000)
    results = {}
    for venue, getter in feeds.items():
        results[venue] = compare(getter(now))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(results), encoding="utf-8")
    return results


if __name__ == "__main__":
    try:
        print(render(run()))
    except (MarketDataError, ValueError, OSError) as exc:
        print("Minute scalping research aborted:", exc)
        raise SystemExit(1)
