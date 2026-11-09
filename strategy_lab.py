"""Isolated read-only BTC research: breakout trend vs trend-filtered pullback.

Public completed 1h candles, next-bar simulated fills, no exchange orders,
no private keys, no changes to the running persistent paper ledger.
"""
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from bot import BINANCE_URL, HYPERLIQUID_URL, MarketDataError, read_json
from profitability_gate import screen as profitability_screen

HOUR = 3_600_000
BARS = 4000
START = 10_000.0
ALLOCATION = .02                 # 2% of equity per entry
FEE = .001                       # hypothetical fee each side
SLIP = .0005                     # hypothetical slippage each side
STOP = .025                      # price-based stop; gaps can lose more
DAY_LIMIT = .01                  # virtual daily loss pause
WARMUP = 220
STRATEGIES = ("breakout", "pullback", "sma", "breakout_confirmed", "pullback_rebound")
FIELDS = ("open", "high", "low", "close")


def validate(bars):
    if len(bars) < 600:
        raise MarketDataError("Insufficient history for training and untouched holdout")
    prev = None
    for b in bars:
        stamp = b.get("end_ms")
        prices = [b.get(k) for k in FIELDS]
        if not isinstance(stamp, int) or isinstance(stamp, bool):
            raise MarketDataError("Invalid candle timestamp")
        if prev is not None and abs(stamp - prev - HOUR) > 2000:
            raise MarketDataError("Duplicate/missing/non-hourly candle")
        if any(not isinstance(p, (float, int)) or isinstance(p, bool)
               or not math.isfinite(p) or p <= 0 for p in prices):
            raise MarketDataError("Nonfinite or nonpositive price")
        op, hi, lo, cl = prices
        if not lo <= min(op, cl) <= max(op, cl) <= hi:
            raise MarketDataError("Inconsistent OHLC candle")
        prev = stamp


def fetch(market, now_ms=None, reader=read_json):
    """Fetch up to 4000 consecutive, closed public hourly candles only."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if market == "binance":
        data, cursor = [], now_ms
        while len(data) < BARS + 2:
            limit = min(1000, BARS + 2 - len(data))
            query = urlencode({"symbol": "BTCUSDT", "interval": "1h",
                               "limit": limit, "endTime": cursor})
            raw = reader(BINANCE_URL + "?" + query)
            if not isinstance(raw, list) or not raw or len(raw) > limit:
                raise MarketDataError("Missing Binance historical page")
            try:
                page = [dict(open_ms=int(r[0]), end_ms=int(r[6]),
                             open=float(r[1]), high=float(r[2]),
                             low=float(r[3]), close=float(r[4])) for r in raw]
            except (ValueError, TypeError, IndexError, OverflowError) as exc:
                raise MarketDataError("Invalid Binance page") from exc
            if any(b["open_ms"] <= a["open_ms"] for a, b in zip(page, page[1:])):
                raise MarketDataError("Nonascending Binance page")
            if data and page[-1]["open_ms"] >= data[0]["open_ms"]:
                raise MarketDataError("Overlapping Binance pagination")
            data = page + data
            cursor = page[0]["open_ms"] - 1
            if len(raw) < limit:
                break
        bars = [{k: v for k, v in b.items() if k != "open_ms"} for b in data]
    elif market == "hyperliquid":
        raw = reader(HYPERLIQUID_URL, {"type": "candleSnapshot",
             "req": {"coin": "BTC", "interval": "1h",
                     "startTime": now_ms - (BARS + 3) * HOUR,
                     "endTime": now_ms}})
        if not isinstance(raw, list):
            raise MarketDataError("Missing Hyperliquid candles")
        try:
            bars = [dict(end_ms=int(r["T"]), open=float(r["o"]),
                         high=float(r["h"]), low=float(r["l"]),
                         close=float(r["c"])) for r in raw]
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise MarketDataError("Invalid Hyperliquid candles") from exc
    else:
        raise ValueError("Unsupported venue")
    bars = [b for b in bars if b["end_ms"] <= now_ms][-BARS:]
    if len(bars) != BARS:
        raise MarketDataError("Need 4000 completed historical candles")
    validate(bars)
    if now_ms - bars[-1]["end_ms"] > 2 * HOUR:
        raise MarketDataError("Latest candle too old")
    return bars


def rsi2(closes, end):
    gains = [max(closes[j] - closes[j-1], 0) for j in (end-1, end)]
    losses = [max(closes[j-1] - closes[j], 0) for j in (end-1, end)]
    up, down = sum(gains), sum(losses)
    return 50.0 if up == down == 0 else (100.0 if down == 0 else 100 * up / (up + down))


def signals(bars, strategy):
    """Decision at bar t uses only closes/highs up to t, fills at t+1 open."""
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy")
    closes = [b["close"] for b in bars]
    enters, exits = [False] * len(bars), [False] * len(bars)
    for i in range(WARMUP, len(bars)):
        price = closes[i]
        sma20 = statistics.fmean(closes[i-19:i+1])
        sma50 = statistics.fmean(closes[i-49:i+1])
        sma200 = statistics.fmean(closes[i-199:i+1])
        prior20 = statistics.fmean(closes[i-20:i])
        trend = price > sma200 and sma50 > sma200
        # Fixed, predeclared experimental regime filter. The 200-hour SMA
        # sixteen hours ago is computed from candles <= i-16, not future data.
        earlier_200 = statistics.fmean(closes[i-215:i-15])
        rising_long_trend = sma200 > earlier_200
        ranges = []
        for j in range(i-19, i+1):
            prev_close = closes[j-1]
            b = bars[j]
            tr = max(b["high"] - b["low"],
                     abs(b["high"] - prev_close),
                     abs(b["low"] - prev_close))
            ranges.append(tr / prev_close)
        normal_volatility = .002 <= statistics.fmean(ranges) <= .035
        regime = trend and rising_long_trend and normal_volatility
        if strategy == "breakout":
            top = max(x["high"] for x in bars[i-20:i])
            enters[i] = trend and price > top
            exits[i] = price < sma50
        elif strategy == "breakout_confirmed":
            # Breakout on a positive candle closing in its upper 25%.
            # All thresholds fixed before evaluating historical results.
            candle = bars[i]
            high20 = max(x["high"] for x in bars[i-20:i])
            bar_range = candle["high"] - candle["low"]
            upper_close = bar_range > 0 and (
                (price - candle["low"]) / bar_range >= .75
            )
            enters[i] = (regime and price > high20 and
                         price > closes[i-1] and upper_close)
            exits[i] = price < sma50
        elif strategy == "pullback":
            # Mean reversion only within a longer bullish trend.
            enters[i] = trend and price < sma20 * .99 and rsi2(closes, i) < 20
            exits[i] = price >= sma20 or price < sma200
        elif strategy == "pullback_rebound":
            # Require a completed reversal candle after a low RSI2 pullback:
            # do not buy while the falling candle is still forming.
            previous_sma20 = statistics.fmean(closes[i-20:i])
            was_oversold = (closes[i-1] < previous_sma20 * .99
                            and rsi2(closes, i-1) < 20)
            candle_up = price > bars[i]["open"] and price > closes[i-1]
            enters[i] = (regime and was_oversold and candle_up
                         and price < sma20)
            exits[i] = price >= sma20 or price < sma200
        else:
            fast = statistics.fmean(closes[i-4:i+1])
            slow = sma20
            prev_fast = statistics.fmean(closes[i-5:i])
            enters[i] = fast > slow and prev_fast <= prior20
            exits[i] = fast < slow
    return enters, exits


def simulate(bars, strategy, first=None, last=None, fee=FEE, slip=SLIP):
    validate(bars)
    if not (0 <= fee <= .01 and 0 <= slip <= .01):
        raise ValueError("Invalid fee/slippage assumptions")
    first = WARMUP+1 if first is None else first
    last = len(bars) if last is None else last
    if first <= WARMUP or not first < last <= len(bars):
        raise ValueError("Invalid independent segment")
    enters, exits = signals(bars, strategy)
    cash, units, paid, stop = START, 0.0, 0.0, 0.0
    wins, closed_pnl, buys = 0, [], 0
    peak, dd = START, 0.0
    paused, day, day_start, pending_daily_exit = False, None, START, False
    equity_curve = []
    for i in range(first, last):
        b = bars[i]
        utc_day = datetime.fromtimestamp(b["end_ms"]/1000, timezone.utc).date()
        if utc_day != day:
            day, paused = utc_day, False
            day_start = cash + units * b["open"]
        sold = False

        def sell(raw_fill):
            nonlocal cash, units, stop, paid, wins, sold
            proceeds = units * raw_fill * (1-slip) * (1-fee)
            pnl = proceeds - paid
            cash += proceeds
            closed_pnl.append(pnl)
            wins += pnl > 0
            units, stop, paid = 0.0, 0.0, 0.0
            sold = True

        if units and pending_daily_exit:
            sell(b["open"])
        elif units and exits[i-1]:
            sell(b["open"])
        elif units and b["open"] <= stop:
            sell(b["open"])       # gap down below stop
        elif units and b["low"] <= stop:
            sell(stop)
        pending_daily_exit = False
        if not units and not sold and not paused and enters[i-1]:
            allocation = min(cash, (cash + units * b["open"]) * ALLOCATION)
            if allocation > 0:
                price = b["open"] * (1+slip)
                units = allocation / (price * (1+fee))
                paid = allocation
                cash -= allocation
                buys += 1
                stop = price * (1-STOP)
                # A stop can also trigger in the entry bar. Conservative:
                # low of an hourly OHLC bar might precede the entry.
                if b["low"] <= stop:
                    sell(min(b["open"], stop))
        equity = cash + units * b["close"]
        if equity <= day_start * (1-DAY_LIMIT):
            paused = True
            if units:
                # Exit next bar open, never at a known close at same timestamp.
                pending_daily_exit = True
        peak = max(peak, equity)
        dd = max(dd, 100 * (peak - equity) / peak)
        equity_curve.append(equity)
    # Force sale at last bar close to account for exit fees and measure
    # independently reset train/holdout equity with no hidden open PnL.
    if units:
        sell(bars[last-1]["close"])
        equity_curve[-1] = cash
        dd = max(dd, 100 * (peak - cash) / peak)
    gross_wins = sum(p for p in closed_pnl if p > 0)
    gross_losses = -sum(p for p in closed_pnl if p < 0)
    factor = None if gross_losses == 0 else gross_wins / gross_losses
    return {"return_pct": 100*(cash/START-1), "max_dd_pct": dd,
            "buys": buys, "closed": len(closed_pnl),
            "win_pct": 100*wins/len(closed_pnl) if closed_pnl else None,
            "profit_factor": factor, "equity": cash}


def compare(bars):
    validate(bars)
    split = int(len(bars) * .7)
    if split <= WARMUP+1 or len(bars)-split < 200:
        raise ValueError("Insufficient holdout")
    results = {}
    for strategy in STRATEGIES:
        results[strategy] = {
            "train": simulate(bars, strategy, last=split),
            "holdout": simulate(bars, strategy, first=split),
            "stress": simulate(bars, strategy, first=split, fee=FEE*2, slip=SLIP*2),
        }
    # Buy/hold benchmarking: risk-normalized 2% BTC allocation with unused
    # funds idle, and whole-account 100% BTC exposure (not risk matched).
    def benchmark(first, last, allocation):
        opening = bars[first]["open"] * (1+SLIP)
        ending = bars[last-1]["close"] * (1-SLIP)
        return 100 * (allocation * (ending/opening * (1-FEE)/(1+FEE)-1))
    # Fixed consecutive, independent-capital windows. These use already
    # inspected history and are *robustness diagnostics*, not fresh evidence.
    if len(bars) >= 3200:
        windows = [(800, 1600), (1600, 2400), (2400, 3200),
                   (3200, len(bars))]
    else:
        windows = [(split, len(bars))]
    results["folds"] = {
        name: [
            {"start": a, "end": b, "ordinary": simulate(bars, name, a, b),
             "stress": simulate(bars, name, a, b, fee=2*FEE, slip=2*SLIP)}
            for a, b in windows
        ]
        for name in STRATEGIES
    }
    results["benchmarks"] = {
        "2pct_btc_holdout_pct": benchmark(split, len(bars), ALLOCATION),
        "100pct_btc_holdout_pct": benchmark(split, len(bars), 1),
        "cash_holdout_pct": 0.0,
    }
    return results


def render(result):
    lines = [
        "# BTC trend breakout vs pullback vs SMA baseline",
        "", "**RESEARCH-ONLY: simulated long-only trades; no account credentials or real orders.**",
        "Each venue: 4,000 completed 1h bars (~167 days), 70/30 chronological split.",
        "Signals use closed candle t and orders are simulated at t+1 open.",
        "All strategies: $10,000 independent virtual account; 2% equity entry;",
        "2.5% price-based stop; 1% UTC daily loss gate; hypothetical 0.1% fee",
        "and 0.05% slippage per side; doubled costs for holdout stress.",
        "Breakout: 20h high, SMA50>SMA200 confirmation; exit under SMA50.",
        "Pullback: RSI(2)<20, close <99% SMA20 in SMA50>SMA200 uptrend;",
        "exit at SMA20 or below SMA200. SMA: independent 5/20 crossover.",
        "Experimental breakout_confirmed: prior 20h high + bullish upper-",
        "quartile close, SMA200 rising over 16h and 0.2%-3.5% average TR.",
        "Experimental pullback_rebound: previous bar oversold RSI(2)<20",
        "and 1% below SMA20, now rising close; same trend/volatility gates.",
        "Both experimental rules were designed after the first holdout",
        "was inspected: reused holdout CANNOT validate an untested edge.",
        "Same-bar stop is pessimistically eligible; no funding, liquidation,",
        "spread depth, realistic execution queues, or guaranteed stop fills.",
        "No hyperparameter optimization, cross-validation, or live execution.",
        "", "| Venue | Strategy | Set | Return | Max drawdown | Closed | Win rate | Profit factor |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for venue, strategies in result.items():
        for name in STRATEGIES:
            for period, value in strategies[name].items():
                win = "N/A" if value["win_pct"] is None else f'{value["win_pct"]:.1f}%'
                pf = "N/A" if value["profit_factor"] is None else f'{value["profit_factor"]:.2f}'
                lines.append(f'| {venue} | {name} | {period} | {value["return_pct"]:+.3f}% | {value["max_dd_pct"]:.3f}% | {value["closed"]} | {win} | {pf} |')
        lines += ["", f"### {venue}: chronological block robustness (same previously seen history)",
                  "| Candidate | Block (bar indices) | Net return | Doubled-cost net return | Closed trades |",
                  "|---|---|---:|---:|---:|"]
        for name in STRATEGIES:
            for fold in strategies["folds"][name]:
                ordinary, stress = fold["ordinary"], fold["stress"]
                lines.append(
                    f'| {name} | {fold["start"]}-{fold["end"]} | '
                    f'{ordinary["return_pct"]:+.3f}% | '
                    f'{stress["return_pct"]:+.3f}% | {ordinary["closed"]} |'
                )
        bench = strategies["benchmarks"]
        lines += ["", f"### {venue}: fee-aware profitability screen (research only)",
                  "| Candidate | Decision | Reason(s) |", "|---|---|---|"]
        for name in STRATEGIES:
            gate = profitability_screen(
                strategies[name]["holdout"], strategies[name]["stress"],
                bench["2pct_btc_holdout_pct"])
            reasons = "; ".join(gate["reasons"]) if gate["reasons"] else (
                "Historical screen only; independent forward paper testing required")
            lines.append(f"| {name} | {gate['decision']} | {reasons} |")
        lines.append(f'| {venue} | 2% BTC buy/hold | holdout | {bench["2pct_btc_holdout_pct"]:+.3f}% | — | 1 | — | — |')
        lines.append(f'| {venue} | 100% BTC buy/hold (not risk matched) | holdout | {bench["100pct_btc_holdout_pct"]:+.3f}% | — | 1 | — | — |')
    lines += ["", "**Important:** the latest holdout has been repeatedly inspected,",
              "including while designing the experimental regime filters.",
              "Neither these folds nor that reused holdout are genuinely untouched",
              "validation for the new variants. Require new forward paper data.",
              "", "**Decision policy:** never promote a candidate if holdout or"
              "double-cost stress net return is nonpositive, if trades are",
              "too few to estimate reliability, or if drawdowns are unacceptable.",
              "Positive historical performance alone does not authorise live",
              "trading. Public-only feeds; untouched paper ledger and account funds."]
    return "\n".join(lines)+"\n"


def run(output=Path("strategy-results/REPORT.md"), feeds=None):
    feeds = feeds or {"Binance BTC spot": lambda now: fetch("binance", now),
                     "Hyperliquid BTC perp": lambda now: fetch("hyperliquid", now)}
    now = int(time.time() * 1000)
    result = {}
    # Commit report only if all venues deliver valid research histories.
    for venue, getter in feeds.items():
        candles = getter(now)
        result[venue] = compare(candles)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    try:
        print(render(run()))
    except (MarketDataError, ValueError, OSError) as exc:
        print("PAPER-ONLY RESEARCH ABORTED:", str(exc))
        raise SystemExit(1)
