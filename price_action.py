"""Research-only breakout/retest price action. No API credentials or orders.

All decisions use fully completed candles; hypothetical fills occur at NEXT open.
No indicator is fitted to holdout data. Long-only, no leverage.
"""
from datetime import datetime, timezone
from backtesting import validate, VIRTUAL_START
from bot import FEE_PCT, SLIPPAGE_PCT

LOOKBACK = 20
TREND = 20
ALLOCATION = 0.02
RISK_FRACTION = 0.005
MAX_STOP_DISTANCE = 0.02
REWARD_RISK = 2.0
WARMUP = LOOKBACK + 4


def simulate(candles):
    validate(candles, minimum=45)
    cash, units, stop, target, entry_total = VIRTUAL_START, 0.0, 0.0, 0.0, 0.0
    exits, events, equity = [], [], []
    for i in range(WARMUP, len(candles)):
        bar = candles[i]
        signal_bar = candles[i - 1]
        breakout = candles[i - 2]
        historical = candles[i - 2 - LOOKBACK:i - 2]
        resistance = max(float(c["high"]) for c in historical)
        closes = [float(c["close"]) for c in candles[i - TREND - 2:i - 2]]
        trend = sum(closes) / TREND
        # Require prior confirmed breakout, then a retest that holds resistance.
        confirmed = (float(breakout["close"]) > resistance
                     and float(breakout["open"]) <= resistance
                     and float(breakout["close"]) > trend)
        retested = (float(signal_bar["low"]) <= resistance
                    and float(signal_bar["close"]) > resistance
                    and float(signal_bar["close"]) > float(signal_bar["open"]))
        opening = float(bar["open"])
        low, high = float(bar["low"]), float(bar["high"])
        stamp = datetime.fromtimestamp(bar["end_ms"] / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        exited = False
        if units:
            # Exits signalled on the last close, filled at the next open.
            failed_retest = float(signal_bar["close"]) < stop
            if opening <= stop or low <= stop or high >= target or failed_retest:
                # Conservative ordering when stop and target hit in the same bar.
                if opening <= stop:
                    price = opening
                    side = "GAP STOP SELL"
                elif low <= stop:
                    price = stop
                    side = "STOP SELL"
                elif failed_retest:
                    price = opening
                    side = "SIGNAL SELL"
                else:
                    price = target
                    side = "TARGET SELL"
                fill = price * (1 - SLIPPAGE_PCT)
                proceeds = units * fill * (1 - FEE_PCT)
                pnl = proceeds - entry_total
                cash += proceeds
                exits.append(pnl)
                events.append((stamp, side, fill, pnl))
                units, stop, target, entry_total = 0.0, 0.0, 0.0, 0.0
                exited = True
        if not units and not exited and confirmed and retested:
            # Stop must be below next opening, not more than 2% away.
            fill = opening * (1 + SLIPPAGE_PCT)
            proposed_stop = min(resistance, float(signal_bar["low"])) * (1 - 0.001)
            distance = (fill - proposed_stop) / fill
            if 0 < distance <= MAX_STOP_DISTANCE:
                budget = min(cash, VIRTUAL_START * ALLOCATION,
                             VIRTUAL_START * RISK_FRACTION / distance)
                if budget > 0:
                    units = budget / (fill * (1 + FEE_PCT))
                    cash -= budget
                    entry_total = budget
                    stop = proposed_stop
                    target = fill + REWARD_RISK * (fill - stop)
                    events.append((stamp, "BUY", fill, 0.0))
        equity.append(cash + units * float(bar["close"]))
    peak, max_drawdown = VIRTUAL_START, 0.0
    for value in equity:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    gain = sum(p for p in exits if p > 0)
    loss = -sum(p for p in exits if p < 0)
    return {"start": VIRTUAL_START, "end": equity[-1],
            "return_pct": (equity[-1] / VIRTUAL_START - 1) * 100,
            "max_drawdown_pct": 100 * max_drawdown,
            "closed_trades": len(exits),
            "win_rate_pct": 100 * sum(p > 0 for p in exits) / len(exits) if exits else None,
            "profit_factor": gain / loss if loss else None,
            "open_position": bool(units), "equity": equity, "events": events,
            "bar_count": len(candles)}


def walk_forward(candles):
    validate(candles, minimum=100)
    split = int(len(candles) * 0.7)
    if len(candles) - split < 25 or split < 45:
        raise ValueError("Not enough bars to test without leakage")
    training = simulate(candles[:split])
    # Separate holdout balances. A historical warmup only, no training trades carried over.
    holdout = simulate(candles[split - WARMUP:])
    return {"in_sample": training, "out_of_sample": holdout, "split": split}
