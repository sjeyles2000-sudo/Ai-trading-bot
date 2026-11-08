"""Standalone, read-only Trendilo-inspired BTC research. NOT the proprietary indicator.
No exchange credentials, orders, paper-ledger writes, or production imports.
Signals use completed 1h bars; simulated orders fill at NEXT bar open.
"""
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from bot import (FEE_PCT, SLIPPAGE_PCT, MarketDataError, read_json,
                 BINANCE_URL, HYPERLIQUID_URL)

START = 10_000.0
POSITION = .02
DAILY_LIMIT = .01
WARMUP = 60
HOUR_MS = 3_600_000
HISTORY = 4000


def fetch_history(market, now_ms, reader=read_json):
    """Fetch 4,000 completed, consecutive public BTC 1h bars per venue.

    Binance history is retrieved backwards in at most five bounded pages.
    Hyperliquid provides recent 5,000 candles. No exchange credentials.
    """
    if market == "binance":
        pages = []
        cursor = now_ms
        while len(pages) < HISTORY + 3:
            limit = min(1000, HISTORY + 3 - len(pages))
            url = BINANCE_URL + "?" + urlencode(
                {"symbol":"BTCUSDT","interval":"1h",
                 "endTime":cursor,"limit":limit})
            raw = reader(url)
            if not isinstance(raw,list) or not raw or len(raw)>limit:
                raise MarketDataError("Invalid or empty Binance history page")
            try:
                parsed=[{"open_ms":int(x[0]),"end_ms":int(x[6]),
                         "open":float(x[1]),"high":float(x[2]),
                         "low":float(x[3]),"close":float(x[4])} for x in raw]
            except (TypeError,ValueError,IndexError,OverflowError) as exc:
                raise MarketDataError("Bad Binance candles") from exc
            if any(b["open_ms"]<=a["open_ms"] for a,b in zip(parsed,parsed[1:])):
                raise MarketDataError("Nonascending Binance candle page")
            if pages and parsed[-1]["open_ms"]>=pages[0]["open_ms"]:
                raise MarketDataError("Binance history cursor failed to move")
            pages=parsed+pages
            cursor=parsed[0]["open_ms"]-1
            if len(raw)<limit:
                break
        bars=[{key:value for key,value in p.items() if key!="open_ms"} for p in pages]
    elif market == "hyperliquid":
        raw=reader(HYPERLIQUID_URL,{"type":"candleSnapshot",
            "req":{"coin":"BTC","interval":"1h",
                   "startTime":now_ms-(HISTORY+4)*HOUR_MS,"endTime":now_ms}})
        if not isinstance(raw,list):
            raise MarketDataError("Bad Hyperliquid response")
        try:
            bars=[{"end_ms":int(x["T"]),"open":float(x["o"]),
                   "high":float(x["h"]),"low":float(x["l"]),
                   "close":float(x["c"])} for x in raw]
        except (KeyError,TypeError,ValueError,OverflowError) as exc:
            raise MarketDataError("Bad Hyperliquid candles") from exc
    else:
        raise ValueError("Unknown exchange")
    bars=[x for x in bars if x["end_ms"]<=now_ms][-HISTORY:]
    if len(bars)!=HISTORY:
        raise MarketDataError("Incomplete 4000-hour research history")
    validate(bars)
    if now_ms-bars[-1]["end_ms"]>2*HOUR_MS:
        raise MarketDataError("Stale hourly data")
    return bars


def validate(bars):
    if len(bars) < 180:
        raise ValueError("Need >=180 completed 1h candles; no trade simulation")
    previous = None
    for b in bars:
        stamp = b.get("end_ms")
        vals = [b.get(k) for k in ("open", "high", "low", "close")]
        if not isinstance(stamp, int) or (previous is not None and abs(stamp-previous-HOUR_MS) > 2000):
            raise ValueError("Missing, repeated, or incorrectly timed hourly candle")
        if not all(isinstance(x, (float, int)) and math.isfinite(x) and x > 0 for x in vals):
            raise ValueError("Nonfinite or nonpositive OHLC")
        o,h,l,c = vals
        if not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError("Invalid candle range")
        previous = stamp


def alma(values, window=20, offset=.85, sigma=6.0):
    # Arnaud Legoux moving average: weighting recent samples, no future data.
    m = offset*(window-1)
    s = window/sigma
    weights = [math.exp(-((j-m)**2)/(2*s*s)) for j in range(window)]
    denom = sum(weights)
    return sum(w*v for w,v in zip(weights,values[-window:])) / denom


def indicators(bars):
    """Independent Trendilo-style oscillator: ALMA of 1-bar percentage changes,
    bands from previous 20 oscillator values; never uses future values.
    This is a research hypothesis, not a claim to reproduce paid code.
    """
    closes=[b["close"] for b in bars]
    change=[0.0]+[100*(closes[i]/closes[i-1]-1) for i in range(1,len(bars))]
    osc=[None]*len(bars)
    upper=[None]*len(bars)
    lower=[None]*len(bars)
    atr=[None]*len(bars)
    for i in range(20,len(bars)):
        osc[i]=alma(change[i-19:i+1])
        if i >= 40:
            prior=[x for x in osc[i-20:i] if x is not None]
            dev=statistics.pstdev(prior)
            middle=sum(prior)/len(prior)
            upper[i]=middle + 1.5*dev
            lower[i]=middle - 1.5*dev
        if i >= 14:
            ranges=[max(bars[j]["high"]-bars[j]["low"],
                        abs(bars[j]["high"]-closes[j-1]),
                        abs(bars[j]["low"]-closes[j-1]))
                    for j in range(i-13,i+1)]
            atr[i]=sum(ranges)/len(ranges)
    return osc,upper,lower,atr


def signals(bars, strategy):
    closes=[b["close"] for b in bars]
    osc,upper,lower,atr=indicators(bars)
    buy=[False]*len(bars)
    exit_=[False]*len(bars)
    for i in range(WARMUP,len(bars)):
        if strategy=="trendilo":
            trend=sum(closes[i-19:i+1])/20 > sum(closes[i-49:i+1])/50
            # Crossing above an upper band from prior values; conservative
            buy[i]=(trend and osc[i]>0 and osc[i]>upper[i]
                    and osc[i-1]<=upper[i-1])
            exit_[i]=osc[i]<0 or osc[i]<lower[i]
        elif strategy=="sma":
            fast=sum(closes[i-4:i+1])/5
            slow=sum(closes[i-19:i+1])/20
            previous_fast=sum(closes[i-5:i])/5
            previous_slow=sum(closes[i-20:i])/20
            buy[i]=fast>slow and previous_fast<=previous_slow
            exit_[i]=fast<slow
        else:
            raise ValueError("Unknown strategy")
    return buy,exit_,atr


def simulate(bars, strategy, first=None, last=None, fee=FEE_PCT, slip=SLIPPAGE_PCT):
    validate(bars)
    if strategy not in ("trendilo","sma") or not (0<=fee<=.01 and 0<=slip<=.01):
        raise ValueError("Invalid research settings")
    first=WARMUP+1 if first is None else first
    last=len(bars) if last is None else last
    if first<=WARMUP or not first<last<=len(bars):
        raise ValueError("Invalid segment")
    buy,exits,atr=signals(bars,strategy)
    cash,units,stop,spent=START,0.0,0.0,0.0
    daily_start=START
    day=None
    paused=False
    pending_exit=False
    peak=START
    dd=0.0
    wins=[]
    events=[]
    for i in range(first,last):
        b=bars[i]
        d=datetime.fromtimestamp(b["end_ms"]/1000,timezone.utc).date()
        if d!=day:
            day=d
            paused=False
            daily_start=cash+units*b["open"]
        sold=False
        def sell(reason,price):
            nonlocal cash,units,stop,spent,sold
            proceeds=units*price*(1-slip)*(1-fee)
            pnl=proceeds-spent
            cash+=proceeds
            wins.append(pnl)
            events.append((i,reason,round(pnl,4)))
            units=stop=spent=0.0
            sold=True
        # Signal from prior completed bar executes at this open.
        if units and pending_exit:
            sell("DAILY LIMIT EXIT",b["open"])
        elif units and exits[i-1]:
            sell("SIGNAL EXIT",b["open"])
        elif units and b["low"]<=stop:
            sell("STOP EXIT",min(b["open"],stop))
        pending_exit=False
        if not units and not sold and not paused and buy[i-1]:
            budget=min(cash,START*POSITION)
            if budget>0:
                price=b["open"]*(1+slip)
                units=budget/(price*(1+fee))
                spent=budget
                cash-=budget
                # ATR stop is capped at 2% to limit the assumed stop distance.
                distance=min(.02,2*atr[i-1]/price) if atr[i-1] else .02
                stop=price*(1-distance)
                events.append((i,"BUY",0.0))
                # Do not assume an entry bar cannot also hit the stop.
                if b["low"]<=stop:
                    sell("ENTRY BAR STOP",min(b["open"],stop))
        eq=cash+units*b["close"]
        if eq<=daily_start*(1-DAILY_LIMIT):
            paused=True
            pending_exit=bool(units)
        peak=max(peak,eq)
        dd=max(dd,(peak-eq)/peak)
    # Final open position is marked at close; exit costs not yet included.
    result={"return_pct":100*((cash+units*bars[last-1]["close"])/START-1),
            "drawdown_pct":dd*100,"closed":len(wins),"buys":sum(x[1]=="BUY" for x in events),
            "win_pct":(100*sum(p>0 for p in wins)/len(wins)) if wins else None,
            "open":bool(units)}
    return result


def compare(bars):
    validate(bars)
    split=int(len(bars)*.7)
    if len(bars)-split<50:
        raise ValueError("Holdout too short")
    # Identical chronological split, independent $10k virtual account per test.
    results={}
    for s in ("trendilo","sma"):
        results[s]={"train":simulate(bars,s,last=split),
                    "holdout":simulate(bars,s,first=split),
                    "stress":simulate(bars,s,first=split,fee=FEE_PCT*2,
                                      slip=SLIPPAGE_PCT*2)}
    return results


def render(all_results):
    out=["# Trendilo-inspired research vs 5/20 SMA crossover","",
         "**READ-ONLY HISTORICAL RESEARCH; NOT LIVE PAPER TRADING OR REAL ORDERS.**","",
         "Independent Trendilo-style hypothesis: 20-bar ALMA of hourly percentage",
         "changes, previous-20 oscillator standard-deviation bands (1.5x),",
         "50/20-bar trend confirmation, zero/band exits and capped 2-ATR stop.",
         "Not a reproduction or endorsement of a proprietary Trendilo script.","",
         "Fixed parameters, 70/30 chronological split with warmup; no tuning on holdout.",
         "Completed bars only; next-open hypothetical fills; 2% of initial virtual",
         "capital max allocation; 0.1% fee + 0.05% slippage per side.",
         "Stress test doubles both costs. Separate independent virtual $10k account",
         "per strategy/segment; no leverage, funding, realistic order book or latency.",
         "Virtual profit figures may include open positions without final exit fees.",
         "At a daily loss threshold, existing exposure exits at the next open;",
         "large gaps can exceed risk caps. Not a production execution model.","",
         "| Venue | Strategy | Segment | Return | Drawdown | Buys | Closed | Win rate |",
         "|---|---|---|---:|---:|---:|---:|---:|"]
    for venue,results in all_results.items():
        for strategy,segments in results.items():
            for segment,r in segments.items():
                win="N/A" if r["win_pct"] is None else f'{r["win_pct"]:.1f}%'
                out.append(f'| {venue} | {strategy} | {segment} | {r["return_pct"]:+.4f}% | {r["drawdown_pct"]:.4f}% | {r["buys"]} | {r["closed"]} | {win} |')
    out+=["","**No strategy is approved for live capital.** 4000 hourly bars are
          " (~167 days), but these still span limited market conditions. ""
          "More data and forward",
          "testing are necessary; a 0-trade result is not evidence of an edge.",
          "The SMA comparator and new candidate are standalone research versions,",
          "not a simulation of every production risk rule. No changes to demo_runner.py.",""]
    return "\n".join(out)


def run(output=Path("trendilo-results/REPORT.md"),feeds=None):
    feeds=feeds or {"Binance BTC spot":lambda now:fetch_history("binance",now),
                    "Hyperliquid BTC perp":lambda now:fetch_history("hyperliquid",now)}
    now=int(time.time()*1000)
    all_results={}
    for venue,fetch in feeds.items():
        bars=fetch(now)
        all_results[venue]=compare(bars)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render(all_results),encoding="utf-8")
    return all_results


if __name__=="__main__":
    try:
        result=run()
        print(render(result))
    except (MarketDataError,ValueError,OSError) as exc:
        print(f"RESEARCH FAILED (NO REPORT WRITTEN): {exc}")
        raise SystemExit(1)
