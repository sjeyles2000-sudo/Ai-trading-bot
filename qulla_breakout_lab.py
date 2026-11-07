"""Read-only, Qullamaggie-inspired DAILY crypto breakout research.

This is an ORIGINAL simplified rule hypothesis, not Qullamaggie's trading system.
No exchange I/O, authenticated endpoints, persistent state, or live orders.
"""
from datetime import datetime, timezone
import math

DAY_MS = 86_400_000
START_CASH = 10_000.0
FEE = 0.001
SLIPPAGE = 0.0005
MAX_NOTIONAL = 0.02
MAX_EQUITY_RISK = 0.0025
MAX_DAILY_LOSS = 0.01


def validate(bars, minimum=55):
    """Strict completed consecutive daily OHLCV; caller supplies a single market."""
    if not isinstance(bars, list) or len(bars) < minimum:
        raise ValueError("Insufficient daily OHLCV candles")
    prev = None
    for bar in bars:
        if not isinstance(bar, dict) or type(bar.get("end_ms")) is not int:
            raise ValueError("Bad daily candle timestamp")
        ts = bar["end_ms"]
        if prev is not None and ts - prev != DAY_MS:
            raise ValueError("Missing, duplicate or misordered daily candles")
        prev = ts
        try:
            o, h, l, c, v = (float(bar[k]) for k in
                             ("open", "high", "low", "close", "volume"))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Bad daily candle fields") from exc
        if (not all(math.isfinite(x) for x in (o,h,l,c,v)) or
                min(o,h,l,c) <= 0 or v < 0 or
                l > min(o,c) or h < max(o,c) or l > h):
            raise ValueError("Inconsistent daily OHLCV candle")
        prev = ts
    return bars


def breakout_signal(bars, i):
    """Close-confirmed breakout; resistance/volume exclude signal candle.

    Exploratory rules: above rising 20-day SMA, prior 10-day range at most
    12% of range over prior 30 bars, close > previous 10-day high and
    volume > 1.2x preceding 20-bar mean.
    """
    if i < 41:
        return False
    c = bars[i]
    prev10 = bars[i-10:i]
    prev30 = bars[i-30:i]
    high10 = max(b["high"] for b in prev10)
    span10 = high10 - min(b["low"] for b in prev10)
    span30 = max(b["high"] for b in prev30)-min(b["low"] for b in prev30)
    closes = [b["close"] for b in bars[i-21:i]]
    ma20 = sum(closes[-20:])/20
    ma20_prev = sum(closes[:-1])/20
    mean_vol = sum(b["volume"] for b in bars[i-20:i])/20
    return (span30 > 0 and span10/span30 <= 0.12 and
            c["close"] > high10 and c["close"] > ma20 and
            ma20 > ma20_prev and mean_vol > 0 and
            c["volume"] > mean_vol * 1.2)


def simulate(bars, first=42, last=None, fee=FEE, slippage=SLIPPAGE):
    """Historical, virtual only; signals at close, orders at NEXT bar open.

    Stop fills use the lower of stop and next open with slippage (gaps
    may exceed intended risk). Daily pause blocks NEW entries; no order API.
    """
    validate(bars)
    last = len(bars) if last is None else last
    if not (42 <= first < last <= len(bars)):
        raise ValueError("Invalid test window")
    if not (0 <= fee <= 0.01 and 0 <= slippage <= 0.01):
        raise ValueError("Invalid cost assumptions")
    cash, units, stop, cost = START_CASH, 0.0, 0.0, 0.0
    events, equity, pnls = [], [], []
    day, day_start, paused = None, START_CASH, False
    for i in range(first,last):
        bar = bars[i]
        utc_day = datetime.fromtimestamp(bar["end_ms"]/1000, timezone.utc).date()
        if day != utc_day:
            day, day_start, paused = utc_day, cash+units*bar["open"], False
        exited = False
        if units and (bar["low"] <= stop or bar["close"] < sum(
                b["close"] for b in bars[i-20:i])/20):
            stop_hit = bar["low"] <= stop
            raw_exit = min(stop,bar["open"]) if stop_hit else bar["open"]
            # For MA exits, use previous CLOSED bar signal (not today's close).
            if not stop_hit:
                prior_ma = sum(b["close"] for b in bars[i-21:i-1])/20
                if bars[i-1]["close"] >= prior_ma:
                    raw_exit = None
            if raw_exit is not None:
                fill = raw_exit * (1-slippage)
                proceeds = units * fill * (1-fee)
                pnl = proceeds - cost
                cash += proceeds
                pnls.append(pnl)
                events.append((i,"STOP" if stop_hit else "EXIT",round(fill,6)))
                units,stop,cost,exited = 0.0,0.0,0.0,True
        if not units and not exited and not paused and breakout_signal(bars,i-1):
            raw_stop = min(b["low"] for b in bars[i-10:i])
            fill = bar["open"]*(1+slippage)
            if raw_stop < fill:
                stop_fraction = (fill - raw_stop)/fill
                budget = min(cash, cash*MAX_NOTIONAL,
                             START_CASH*MAX_EQUITY_RISK/stop_fraction)
                if budget > 0:
                    units = budget/(fill*(1+fee))
                    cash -= budget
                    cost = budget
                    stop = raw_stop
                    events.append((i,"BUY",round(fill,6)))
                    # Entry-bar stop: conservative ambiguous intrabar sequence.
                    if bar["low"] <= stop:
                        proceeds = units*min(bar["open"],stop)*(1-slippage)*(1-fee)
                        cash += proceeds
                        pnls.append(proceeds-cost)
                        events.append((i,"ENTRY_BAR_STOP",round(proceeds/units,6)))
                        units,stop,cost,exited = 0.0,0.0,0.0,True
        value = cash + units*bar["close"]
        equity.append(value)
        if value < day_start*(1-MAX_DAILY_LOSS):
            paused = True
    high,dd=START_CASH,0.0
    for eq in equity:
        high=max(high,eq)
        dd=max(dd,(high-eq)/high)
    return {"return_pct":100*(equity[-1]/START_CASH-1),
            "max_drawdown_pct":dd*100,
            "closed_trades":len(pnls),
            "events":events,"equity":equity,
            "open_position":bool(units)}


def compare(bars, fee=FEE, slippage=SLIPPAGE):
    """Fixed 70/30 chronological split, no lookahead, fresh capital in holdout."""
    validate(bars, minimum=200)
    split = int(len(bars)*0.7)
    if len(bars)-split < 45:
        raise ValueError("Holdout too short")
    return {"train":simulate(bars,last=split,fee=fee,slippage=slippage),
            "holdout":simulate(bars,first=split,fee=fee,slippage=slippage),
            "stress_holdout":simulate(bars,first=split,fee=fee*2,
                                       slippage=slippage*2),
            "split":split}
