"""Standalone hourly OHLC execution stress research. NO orders or account access."""
import argparse
import json
import math
from pathlib import Path

START_CASH = 10000.0


def check_candles(candles):
    if not isinstance(candles, list) or len(candles) < 80:
        raise ValueError("At least 80 hourly candles required")
    prev = None
    for c in candles:
        if not isinstance(c, dict) or type(c.get("end_ms")) is not int:
            raise ValueError("Invalid candle/timestamp")
        if prev is not None and c["end_ms"] - prev not in (3599999, 3600000, 3600001):
            raise ValueError("Missing or nonconsecutive hourly candle")
        prev = c["end_ms"]
        try:
            o, h, l, close = (float(c[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Malformed OHLC") from exc
        if not all(math.isfinite(x) and x > 0 for x in (o, h, l, close)):
            raise ValueError("Nonfinite or nonpositive price")
        if l > min(o, close) or h < max(o, close) or l > h:
            raise ValueError("Inconsistent OHLC")


def run_stress(candles, *, fee=0.001, slippage=0.0005, outages=(), delay=0):
    """Completed candle signals; next-open fills; blocked execution in outages.

    Missed orders are not executed during outage. Held positions may not exit
    until recovery, including stop breaches. This is a *model*, not execution
    replay. No funding, actual order book, or slippage estimation from depth.
    """
    check_candles(candles)
    if type(delay) is not int or delay not in (0, 1, 2, 3):
        raise ValueError("Delay must be 0-3 whole bars")
    if any(type(i) is not int or i < 0 or i >= len(candles) for i in outages):
        raise ValueError("Invalid outage indices")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or
           not math.isfinite(x) or not 0 <= x <= .1 for x in (fee, slippage)):
        raise ValueError("Invalid execution costs")
    offline = set(outages)
    closes = [float(c["close"]) for c in candles]
    cash, units, entry_cost, stop, pending = START_CASH, 0.0, 0.0, 0.0, False
    events, equity, closed_pnl = [], [], []
    missed_entries, exposed_hours = 0, 0

    def sell(i, quote, reason):
        nonlocal cash, units, entry_cost, stop, pending
        fill = quote * (1 - slippage)
        proceeds = units * fill * (1 - fee)
        pnl = proceeds - entry_cost
        cash += proceeds
        closed_pnl.append(pnl)
        events.append((i, reason, round(fill, 8), round(pnl, 4)))
        units, entry_cost, stop, pending = 0.0, 0.0, 0.0, False

    for i in range(22, len(candles)):
        bar = candles[i]
        opening, low, closing = float(bar["open"]), float(bar["low"]), closes[i]
        history = closes[:i-delay]  # never includes current/open execution candle
        fast = sum(history[-5:]) / 5
        slow = sum(history[-20:]) / 20
        prev_fast = sum(history[-6:-1]) / 5
        prev_slow = sum(history[-21:-1]) / 20
        buy = fast > slow and prev_fast <= prev_slow
        exit_signal = fast < slow and prev_fast >= prev_slow
        if i in offline:
            if units:
                exposed_hours += 1
                if low <= stop or exit_signal:
                    pending = True
            elif buy:
                missed_entries += 1
        else:
            if units and (pending or exit_signal):
                sell(i, opening, "DELAYED EXIT" if pending else "SIGNAL SELL")
            elif units and low <= stop:
                sell(i, min(opening, stop), "STOP SELL")
            elif not units and buy:
                allocation = min(cash, cash * .02)
                if allocation > 0:
                    fill = opening * (1 + slippage)
                    units = allocation / (fill * (1 + fee))
                    cash -= allocation
                    entry_cost = allocation
                    stop = fill * .98
                    events.append((i, "BUY", round(fill, 8), 0))
                    if low <= stop:  # pessimistic entry-hour stop assumption
                        sell(i, min(opening, stop), "ENTRY BAR STOP SELL")
        equity.append(cash + units * closing)

    peak, dd = START_CASH, 0.0
    for value in equity:
        peak = max(peak, value)
        dd = max(dd, (peak - value) / peak)
    profit = sum(max(0, p) for p in closed_pnl)
    loss = -sum(min(0, p) for p in closed_pnl)
    return {"ending_equity": round(equity[-1], 4),
            "return_pct": round(100 * (equity[-1] / START_CASH - 1), 5),
            "max_drawdown_pct": round(100 * dd, 5),
            "closed_trades": len(closed_pnl),
            "profit_factor": round(profit / loss, 4) if loss else None,
            "open_position": bool(units), "missed_entries": missed_entries,
            "outage_exposure_hours": exposed_hours, "events": events}


def compare(candles):
    """Fixed, predeclared stress cases; not optimized on outcomes."""
    start = int(len(candles) * .8)
    outage = range(start, min(start + 8, len(candles)))
    return {
        "Baseline": run_stress(candles),
        "Double trading costs": run_stress(candles, fee=.002, slippage=.001),
        "One-hour delay": run_stress(candles, delay=1),
        "Eight-hour outage": run_stress(candles, outages=outage),
        "Combined stress": run_stress(candles, fee=.002, slippage=.001,
                                      delay=1, outages=outage),
    }


def report(candles, market="BTC public hourly data"):
    results = compare(candles)
    lines = [f"# Execution-stress research: {market}", "",
             "**RESEARCH ONLY. NO REAL OR PAPER TRADES.**", "",
             f"{len(candles)} completed hourly candles, 5/20 SMA crossover, "
             "2% notional virtual allocation, 2% stop, US$10,000 starting cash.",
             "Signals use completed candles. Baseline fills at next hour open.",
             "Baseline per-side fee/slippage: 0.1%/0.05%; stressed: 0.2%/0.1%.",
             "Outage = eight modelled hours at 80% into the series. This is NOT "
             "a claim that any exchange experienced an eight-hour outage.",
             "A stop triggered during the modelled outage fills only after recovery.",
             "Hourly OHLC cannot model intrabar paths, funding, order books, "
             "liquidation, or realistic realized fills. Not proof of profitability.", "",
             "| Scenario | Net return | Drawdown | Closed trades | Profit factor | Missed entries | Exposed outage hours |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, x in results.items():
        pf = "N/A" if x["profit_factor"] is None else str(x["profit_factor"])
        lines.append(f'| {name} | {x["return_pct"]:+.3f}% | {x["max_drawdown_pct"]:.3f}% | '
                     f'{x["closed_trades"]} | {pf} | {x["missed_entries"]} | '
                     f'{x["outage_exposure_hours"]} |')
    lines += ["", "Small samples and few closed trades are inconclusive. Compare to cash",
              "and BTC holding; require longer independent unseen holdouts and forward testing.",
              "Existing scheduled bot, persistent ledger and exchange permissions are untouched.", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candles_json", type=Path,
                   help="Offline JSON array of completed 1h OHLC candles")
    p.add_argument("--market", default="BTC historical OHLC")
    p.add_argument("--output", type=Path, default=Path("execution-stress.md"))
    a = p.parse_args()
    candles = json.loads(a.candles_json.read_text(encoding="utf-8"))
    a.output.write_text(report(candles, a.market), encoding="utf-8")
    print("Wrote research report:", a.output)


if __name__ == "__main__":
    main()
