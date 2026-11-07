"""Offline, reproducible backtesting research using public historical candles.

Never submits orders, reads credentials, or mutates persistent virtual accounts.
Backtest signals form at bar close and fill at NEXT bar open to avoid lookahead.
"""
import csv
import math
from pathlib import Path
from datetime import datetime, timezone

from bot import FEE_PCT, SLIPPAGE_PCT

VIRTUAL_START=10000.0


def validate(candles,minimum=45):
    if len(candles)<minimum:
        raise ValueError(f"Need at least {minimum} consecutive completed hourly candles")
    prev=None
    for c in candles:
        ts=c["end_ms"]
        if not isinstance(ts,int) or (prev is not None and ts-prev not in (3600000, 3599999,3600001)):
            raise ValueError("Candles must be chronological consecutive 1h periods")
        prev=ts
        o,h,l,close=[float(c[k]) for k in ("open","high","low","close")]
        if not all(math.isfinite(x) and x>0 for x in (o,h,l,close)) or l>min(o,close) or h<max(o,close):
            raise ValueError("Bad OHLC candle")


def simulate(candles,short_window=5,long_window=20,position_pct=.02,stop_pct=.02):
    """A single long-only, no-leverage, 1-bar-delayed SMA crossover test."""
    validate(candles)
    if not (2<=short_window<long_window<=40):
        raise ValueError("Invalid MA windows")
    if not (0<position_pct<=.02 and 0<stop_pct<=.05):
        raise ValueError("Unsafe hypothetical allocation or stop")
    start=long_window+1
    cash=VIRTUAL_START
    units=0.0
    entry_total=0.0
    entry_time=None
    stop=0.0
    equity=[]
    exits=[]
    events=[]
    for i in range(start,len(candles)):
        bar=candles[i]
        exited=False
        close_history=[float(c["close"]) for c in candles[:i]]
        ma_short=sum(close_history[-short_window:])/short_window
        ma_long=sum(close_history[-long_window:])/long_window
        previous_short=sum(close_history[-short_window-1:-1])/short_window
        previous_long=sum(close_history[-long_window-1:-1])/long_window
        buy_signal=ma_short>ma_long and previous_short<=previous_long
        sell_signal=ma_short<ma_long and previous_short>=previous_long
        # Previous completed candle decides at NEXT candle opening price.
        opening=float(bar["open"])
        stamp=datetime.fromtimestamp(bar["end_ms"]/1000,timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if units:
            stop_hit=float(bar["low"])<=stop
            if stop_hit or sell_signal:
                fill=(min(opening,stop) if stop_hit else opening)*(1-SLIPPAGE_PCT)
                proceeds=units*fill*(1-FEE_PCT)
                pnl=proceeds-entry_total
                cash+=proceeds
                exits.append(pnl)
                events.append((stamp,"STOP SELL" if stop_hit else "SIGNAL SELL",fill,pnl))
                units=0.0
                exited=True
                entry_total=0.0
                entry_time=None
                stop=0.0
        if not units and not exited and buy_signal:
            budget=min(cash,cash*position_pct)
            if budget>0:
                fill=opening*(1+SLIPPAGE_PCT)
                units=budget/(fill*(1+FEE_PCT))
                cash-=budget
                entry_total=budget
                entry_time=stamp
                stop=fill*(1-stop_pct)
                events.append((stamp,"BUY",fill,0.0))
        eq=cash+units*float(bar["close"])
        equity.append(eq)
    peak=VIRTUAL_START
    max_dd=0.0
    for eq in equity:
        peak=max(peak,eq)
        max_dd=max(max_dd,(peak-eq)/peak)
    gain=sum(x for x in exits if x>0)
    losses=-sum(x for x in exits if x<0)
    return {
      "start":VIRTUAL_START,"end":equity[-1],"return_pct":100*(equity[-1]/VIRTUAL_START-1),
      "max_drawdown_pct":100*max_dd,"closed_trades":len(exits),
      "win_rate_pct":100*sum(p>0 for p in exits)/len(exits) if exits else None,
      "profit_factor":gain/losses if losses>0 else None,
      "open_position":bool(units),"equity":equity,"events":events,
      "bar_count":len(candles),"short_window":short_window,"long_window":long_window}


def walk_forward(candles,short_window=5,long_window=20):
    """Fixed parameters, chronological 70/30 split; each test has warmup history.

    No parameter selection on test data. Train/test segments are reported separately.
    """
    validate(candles,minimum=100)
    split=max(int(len(candles)*0.7),long_window+30)
    if len(candles)-split<25:
        raise ValueError("Insufficient holdout candles")
    train=simulate(candles[:split],short_window,long_window)
    # Keep a warmup buffer only. Statistics start after the split.
    warmup=long_window+2
    test=simulate(candles[split-warmup:],short_window,long_window)
    return {"in_sample":train,"out_of_sample":test,"split":split}


def report(result,market):
    def row(label,stats):
        win="N/A" if stats["win_rate_pct"] is None else f'{stats["win_rate_pct"]:.1f}%'
        pf="N/A" if stats["profit_factor"] is None else f'{stats["profit_factor"]:.2f}'
        return f'| {label} | {stats["return_pct"]:+.3f}% | {stats["max_drawdown_pct"]:.3f}% | {stats["closed_trades"]} | {win} | {pf} |'
    return "\n".join([
        f"# Offline backtest: {market}","",
        "**HYPOTHETICAL ONLY — NO REAL TRADES. NOT A PERFORMANCE FORECAST.**","",
        "SMA crossover; signal on completed candle, hypothetical fill at next open.",
        f"Assumed transaction costs: {FEE_PCT*100:.2f}% fee and {SLIPPAGE_PCT*100:.2f}% slippage per side.",
        "2% maximum notional allocation per trade, 2% stop. The demo bot has additional risk controls.",
        "Fixed 5/20 parameters; sequential 70/30 split. No optimization, leverage, funding, spread, market impact or real execution model.",
        "Training/holdout results are **separate standalone simulations**; holdout starts with fresh virtual capital and warmup price history.",
        "Very short samples and overlapping markets cannot establish future profitability.","",
        "| Sample | Return | Max drawdown | Closed trades | Win rate | Profit factor |",
        "|---|---:|---:|---:|---:|---:|",
        row("Training (70%)",result["in_sample"]),
        row("Holdout (30%)",result["out_of_sample"]), "",
        "N/A means insufficient closed trades or no recorded losses; it does not mean infinite profitability.",
        "Open positions are marked to the last candle but NOT counted as closed trade wins.",
        "Do not choose parameters based on holdout results and then call that same holdout unbiased.",""
    ])


def save_report(path,result,market):
    Path(path).write_text(report(result,market),encoding="utf-8")
