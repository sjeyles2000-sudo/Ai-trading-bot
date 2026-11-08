"""Isolated five-role paper-only research; never signs or sends orders."""
import json
import math
import sys
import time
from datetime import datetime, timezone
from bot import (DAILY_LOSS_LIMIT_PCT, FEE_PCT, INTERVAL_MS, LONG_WINDOW,
                 MAX_POSITION_PCT, SHORT_WINDOW, SLIPPAGE_PCT, STARTING_BALANCE,
                 MarketDataError, fetch_binance, fetch_hyperliquid)

LIVE_ORDERS_ENABLED = False
STOP_LOSS_PCT = 0.02
MAX_CANDLE_RANGE_PCT = 0.05


def place_live_order(*args, **kwargs):
    raise RuntimeError("Real orders are not supported")


def check_candles(candles):
    if not isinstance(candles, list) or len(candles) < LONG_WINDOW + 2:
        raise ValueError("Insufficient hourly candles")
    prior = None
    for c in candles:
        if not isinstance(c, dict) or not all(k in c for k in ("end_ms", "open", "high", "low", "close")):
            raise ValueError("Malformed candle")
        ts = c["end_ms"]
        if type(ts) is not int or ts < 0 or (prior is not None and abs(ts - prior - INTERVAL_MS) > 2000):
            raise ValueError("Non-hourly, duplicate, missing or invalid timestamps")
        prior = ts
        values = [c[k] for k in ("open", "high", "low", "close")]
        if any(type(v) not in (float, int) or not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Invalid price")
        if c["low"] > min(c["open"], c["close"]) or c["high"] < max(c["open"], c["close"]) or c["low"] > c["high"]:
            raise ValueError("Inconsistent OHLC")


def market_scanner(history):
    """Agent 1: last known COMPLETED bars, without any future candles."""
    if len(history) < LONG_WINDOW + 1:
        raise ValueError("Insufficient warmup")
    closes = [c["close"] for c in history[-(LONG_WINDOW + 1):]]
    fast = sum(closes[-SHORT_WINDOW:]) / SHORT_WINDOW
    slow = sum(closes[-LONG_WINDOW:]) / LONG_WINDOW
    old_fast = sum(closes[-SHORT_WINDOW-1:-1]) / SHORT_WINDOW
    old_slow = sum(closes[-LONG_WINDOW-1:-1]) / LONG_WINDOW
    last = history[-1]
    return {"asof_ms": last["end_ms"], "fast_sma": round(fast, 6),
            "slow_sma": round(slow, 6),
            "cross_up": fast > slow and old_fast <= old_slow,
            "cross_down": fast < slow and old_fast >= old_slow,
            "range_pct": (last["high"] - last["low"]) / last["close"]}


def strategy_agent(scan):
    """Agent 2: fixed SMA baseline, not a calibrated AI predictor."""
    return "BUY_WATCH" if scan["cross_up"] else "SELL_WATCH" if scan["cross_down"] else "HOLD"


def risk_manager(signal, equity, cash, units, day_open_equity, paused, range_pct):
    """Agent 3: virtual position cap, loss pause and volatility veto."""
    if signal == "SELL_WATCH" and units:
        return {"action": "SELL", "allocation": 0.0}
    if signal != "BUY_WATCH" or units or paused or equity <= day_open_equity * (1 - DAILY_LOSS_LIMIT_PCT) or range_pct > MAX_CANDLE_RANGE_PCT:
        return {"action": "HOLD", "allocation": 0.0}
    amount = min(cash, equity * MAX_POSITION_PCT)
    return {"action": "BUY" if amount > 0 else "HOLD", "allocation": max(0, amount)}


def paper_trader(candles):
    """Agent 4: hypothetical next-open fills; stop-first, long-only, no leverage."""
    check_candles(candles)
    cash, units, stop, cost = STARTING_BALANCE, 0.0, 0.0, 0.0
    day, day_open, paused = "", STARTING_BALANCE, False
    trades, equity_curve, closed_pnl = [], [], []

    def sell(kind, candle_ms, raw_price):
        nonlocal cash, units, stop, cost
        fill = raw_price * (1 - SLIPPAGE_PCT)
        fee = units * fill * FEE_PCT
        proceeds = units * fill - fee
        closed_pnl.append(proceeds - cost)
        trades.append({"asof_ms": candle_ms, "action": kind, "fill": fill,
                       "units": units, "fee": fee})
        cash += proceeds
        units, stop, cost = 0.0, 0.0, 0.0

    for i in range(LONG_WINDOW + 1, len(candles)):
        c = candles[i]
        date = datetime.fromtimestamp(c["end_ms"] / 1000, timezone.utc).strftime("%Y-%m-%d")
        if date != day:
            day, paused = date, False
            day_open = cash + units * c["open"]
        scan = market_scanner(candles[:i])
        plan = risk_manager(strategy_agent(scan), cash + units * c["open"],
                            cash, units, day_open, paused, scan["range_pct"])
        exited = False
        if units and c["open"] <= stop:
            sell("STOP_SELL", c["end_ms"], c["open"])
            exited = True
        elif units and plan["action"] == "SELL":
            sell("SIGNAL_SELL", c["end_ms"], c["open"])
            exited = True
        elif units and c["low"] <= stop:
            sell("STOP_SELL", c["end_ms"], stop)
            exited = True

        if not exited and not units and plan["action"] == "BUY":
            allocation = min(cash, plan["allocation"])
            fill = c["open"] * (1 + SLIPPAGE_PCT)
            units = allocation / (fill * (1 + FEE_PCT))
            cost = allocation
            cash -= allocation
            stop = fill * (1 - STOP_LOSS_PCT)
            trades.append({"asof_ms": c["end_ms"], "action": "BUY",
                           "fill": fill, "units": units, "fee": units * fill * FEE_PCT})
            # Unknown OHLC intrabar order: count stop as hit on entry bar.
            if c["low"] <= stop:
                sell("STOP_SELL", c["end_ms"], min(c["open"], stop))

        equity = cash + units * c["close"]
        if equity <= day_open * (1 - DAILY_LOSS_LIMIT_PCT):
            if units:
                sell("DAILY_LIMIT_SELL", c["end_ms"], c["close"])
            paused = True
            equity = cash
        equity_curve.append(equity)
    return {"final_equity": cash + units * candles[-1]["close"],
            "trades": trades, "closed_pnl": closed_pnl,
            "equity_curve": equity_curve, "open_units": units}


def performance_analyst(result):
    """Agent 5: report realized + unrealized virtual return and observed drawdown."""
    peak, max_dd = STARTING_BALANCE, 0.0
    for equity in result["equity_curve"]:
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    closed = result["closed_pnl"]
    return {"starting_virtual_usd": STARTING_BALANCE,
            "ending_virtual_usd": round(result["final_equity"], 2),
            "return_pct": round(100 * (result["final_equity"] / STARTING_BALANCE - 1), 4),
            "max_closed_bar_drawdown_pct": round(max_dd * 100, 4),
            "virtual_transactions": len(result["trades"]),
            "closed_round_trips": len(closed),
            "win_rate_pct": round(100 * sum(p > 0 for p in closed) / len(closed), 2) if closed else None,
            "assumed_fees_usd": round(sum(t["fee"] for t in result["trades"]), 4),
            "open_virtual_btc": round(result["open_units"], 8)}


def evaluate_market(candles):
    check_candles(candles)
    scan = market_scanner(candles)
    watch = strategy_agent(scan)
    return {"scanner": scan, "strategy_watch": watch,
            "latest_hypothetical_risk_gate": risk_manager(watch, STARTING_BALANCE,
                    STARTING_BALANCE, 0, STARTING_BALANCE, False, scan["range_pct"]),
            "paper_performance": performance_analyst(paper_trader(candles))}


def run(now_ms=None, feeds=None):
    if LIVE_ORDERS_ENABLED is not False:
        raise RuntimeError("Live trading hard lock changed")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    feeds = feeds if feeds is not None else {
        "binance_spot": fetch_binance, "hyperliquid_perpetual": fetch_hyperliquid}
    markets = {}
    for name, fetch in feeds.items():
        markets[name] = evaluate_market(fetch(now_ms))
    return {"mode": "PAPER_RESEARCH_ONLY", "real_orders_enabled": False,
            "asof_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
            "warning": "Short historical simulation; no proven edge. Funding and liquidity not modelled.",
            "markets": markets}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, sort_keys=True))
    except (MarketDataError, ValueError, OSError) as error:
        print("PAPER LAB FAILED: " + str(error), file=sys.stderr)
        raise SystemExit(1)
