"""Offline, read-only virtual trading dashboard with research-only indicators.

No credentials, exchange order APIs, live positions or network requests in the HTML.
All prices are COMPLETED hourly candles, not streaming ticks.
"""
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from bot import STARTING_BALANCE


def sma(values, window):
    return [sum(values[i+1-window:i+1])/window if i+1>=window else None
            for i in range(len(values))]


def ema(values, window):
    alpha = 2/(window+1)
    result = []
    avg = values[0]
    for v in values:
        avg = alpha*v + (1-alpha)*avg
        result.append(avg)
    return result


def rsi(values, window=14):
    if len(values)<=window:
        raise ValueError("Insufficient prices for RSI")
    changes = [values[i]-values[i-1] for i in range(1,len(values))]
    gain = sum(max(v,0) for v in changes[:window])/window
    loss = sum(max(-v,0) for v in changes[:window])/window
    for delta in changes[window:]:
        gain = (gain*(window-1)+max(delta,0))/window
        loss = (loss*(window-1)+max(-delta,0))/window
    if loss==0:
        return 50.0 if gain==0 else 100.0
    return 100-100/(1+gain/loss)


def kama(values, period=10):
    if len(values)<=period:
        raise ValueError("Insufficient prices for KAMA")
    output = [None]*len(values)
    previous = values[period-1]
    fast, slow = 2/3, 2/31
    for i in range(period,len(values)):
        direction = abs(values[i]-values[i-period])
        volatility = sum(abs(values[j]-values[j-1]) for j in range(i-period+1,i+1))
        ratio = direction/volatility if volatility else 0.0
        previous += ((ratio*(fast-slow)+slow)**2)*(values[i]-previous)
        output[i] = previous
    return output


def indicators(candles):
    values = [float(c["close"]) for c in candles]
    if len(values)<30 or any(not math.isfinite(v) or v<=0 for v in values):
        raise ValueError("Need at least 30 positive, finite hourly closing prices")
    ma5, ma20 = sma(values,5),sma(values,20)
    adaptive = kama(values)
    macd = [a-b for a,b in zip(ema(values,12),ema(values,26))]
    histogram = macd[-1]-ema(macd,9)[-1]
    strength = rsi(values)
    # Three families, not 50 correlated votes and NOT calibrated probabilities.
    trend = 1 if ma5[-1]>ma20[-1] else (-1 if ma5[-1]<ma20[-1] else 0)
    adaptive_vote = (1 if values[-1]>adaptive[-1] and adaptive[-1]>adaptive[-2] else
                     -1 if values[-1]<adaptive[-1] and adaptive[-1]<adaptive[-2] else 0)
    momentum = (1 if strength>55 and histogram>0 else
                -1 if strength<45 and histogram<0 else 0)
    votes = {"Trend":trend,"Adaptive":adaptive_vote,"Momentum":momentum}
    bulls, bears = list(votes.values()).count(1),list(votes.values()).count(-1)
    watch = ("BULLISH_WATCH" if bulls>=2 and bears==0 else
             "BEARISH_WATCH" if bears>=2 and bulls==0 else "MIXED")
    return {"ma20":ma20,"kama":adaptive,"rsi":strength,"macd_histogram":histogram,
            "votes":votes,"watch":watch}


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(newline="",encoding="utf-8") as file:
        return list(csv.DictReader(file))[-500:]


def build_dashboard(markets, ledger_dir, updated_ms):
    """markets: exchange-key -> {name, candles, state}; returns full offline HTML."""
    ledger_dir=Path(ledger_dir)
    trades=read_csv(ledger_dir/"trades.csv")
    equities=read_csv(ledger_dir/"equity.csv")
    data={"updated":datetime.fromtimestamp(updated_ms/1000,timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
          "markets":{}}
    for key, record in markets.items():
        candles,state,name=record["candles"],record["state"],record["name"]
        result=indicators(candles)
        last_price=candles[-1]["close"]
        equity=state["cash"]+state["units"]*last_price
        data["markets"][key]={
            "name":name,"last_candle":datetime.fromtimestamp(state["last_candle_ms"]/1000,timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "price":last_price,"equity":equity,"change":100*(equity/STARTING_BALANCE-1),
            "units":state["units"],"stop":state["stop_price"],"transactions":state["trades"],
            "closes":[c["close"] for c in candles[-100:]],
            "times":[c["end_ms"] for c in candles[-100:]],
            "sma20":result["ma20"][-100:],"kama":result["kama"][-100:],
            "rsi":result["rsi"],"macd_histogram":result["macd_histogram"],
            "votes":result["votes"],"watch":result["watch"],
            "trades":[{"time":t["time_utc"],"side":t["side"],"price":float(t["virtual_price_usd"])}
                      for t in trades if t.get("market")==name],
            "equity_history":[float(e["virtual_equity_usd"]) for e in equities if e.get("market")==name][-100:]
        }
    # Do not allow untrusted market strings to close the script element.
    payload=json.dumps(data,allow_nan=False,separators=(",",":")).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    page=r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AI Trader — Paper Dashboard</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#080e1b;color:#eaf2ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(at top right,#182849,#080e1b 55%)}
main{max-width:1080px;margin:auto;padding:22px 15px 45px}
h1{font-size:26px;margin:0}h1 span{color:#69a7ff}h2{font-size:16px;margin:0 0 13px}
.head,.bar{display:flex;align-items:center;justify-content:space-between;gap:15px;flex-wrap:wrap}
.head{margin-bottom:22px}.small{font-size:12px;color:#a8b8d2;line-height:1.7}
.tag{border:1px solid #317750;background:#123c31;border-radius:30px;color:#9fffd1;padding:8px 12px;font-size:12px;font-weight:700}
select{background:#1a2a49;color:white;border:1px solid #345078;padding:11px;border-radius:10px}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}
.card{background:#111c31;border:1px solid #273958;border-radius:13px;padding:17px;min-width:0}
.value{font-size:23px;font-weight:750;margin:8px 0 3px;overflow-wrap:anywhere}
.good{color:#60eab2}.bad{color:#ff8793}.muted{color:#b5c0d1}
svg{width:100%;height:auto;display:block;min-height:160px}
.legend{color:#adbed6;font-size:12px}
.votes{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.votes>div{padding:12px;border:1px solid #324564;border-radius:8px;font-size:14px}
footer{margin-top:20px;color:#9caecc;font-size:12px;line-height:1.7}
@media(max-width:700px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}
.votes{grid-template-columns:1fr}.value{font-size:20px}}
</style></head><body><main>
<header class="head"><div><h1>◈ AI <span>Trader</span> Dashboard</h1>
<div class="small">Completed hourly candles · Generated <span id="updated"></span></div></div>
<div class="tag">● VIRTUAL MONEY ONLY</div></header>
<div class="bar"><h2>Read-only market overview</h2><select id="market" aria-label="Select exchange"></select></div>
<section class="cards"><div class="card"><div class="small">Last completed BTC price</div><div class="value" id="price"></div><div class="small" id="candle"></div></div>
<div class="card"><div class="small">Virtual account equity</div><div class="value" id="equity"></div><div class="small" id="change"></div></div>
<div class="card"><div class="small">Simulated transactions</div><div class="value" id="trades"></div><div class="small" id="position"></div></div>
<div class="card"><div class="small">Research indicator</div><div class="value" id="watch"></div><div class="small">Not a predicted win probability</div></div></section>
<section class="card"><div class="bar"><h2>BTC price · simulated trade markers</h2>
<div class="legend">🔵 Close &nbsp; 🟠 SMA20 &nbsp; 🟣 KAMA &nbsp; ▲ Buy / ▼ Sell</div></div>
<svg id="priceChart" viewBox="0 0 820 310" role="img" aria-label="Hourly price and moving averages"></svg></section>
<section class="card" style="margin-top:13px"><h2>Virtual equity history</h2>
<svg id="equityChart" viewBox="0 0 820 170" role="img" aria-label="Simulated account equity"></svg></section>
<section class="card" style="margin-top:13px"><h2>Research-only signal families</h2>
<div id="votes" class="votes"></div><p class="small" id="metrics"></p></section>
<footer>Estimated paper fills only. This offline snapshot does not stream market data or place orders.
The indicators have not been validated as profitable and do not affect the existing simulated trading logic.
Real trading, wallet connections, funding, order-book execution, leverage and live order submission are disabled.</footer>
</main><script>const DATA=__DATA__;
const $=id=>document.getElementById(id),ns="http://www.w3.org/2000/svg";
const usd=n=>new Intl.NumberFormat("en-US",{style:"currency",currency:"USD"}).format(n);
function svgEl(parent,tag,attrs,text){let el=document.createElementNS(ns,tag);
Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));
if(text!==undefined)el.textContent=text;parent.append(el);return el;}
function chart(id,series,height,markers=[]){const root=$(id);root.replaceChildren();
const vals=series.flatMap(s=>s.values.filter(Number.isFinite));
if(!vals.length){svgEl(root,"text",{x:400,y:90,fill:"#aabbd3"},"No snapshots yet");return;}
const n=series[0].values.length,minimum=Math.min(...vals),maximum=Math.max(...vals);
const pad=Math.max((maximum-minimum)*0.1,Math.abs(maximum)*0.0001,0.01);
const lo=minimum-pad,hi=maximum+pad;
const x=i=>55+i*748/Math.max(n-1,1),y=v=>12+(hi-v)/(hi-lo)*(height-40);
for(let i=0;i<4;i++){let v=lo+(hi-lo)*i/3,py=y(v);
svgEl(root,"line",{x1:55,x2:810,y1:py,y2:py,stroke:"#293a57","stroke-dasharray":"3 6"});
svgEl(root,"text",{x:49,y:py+4,fill:"#91a2bd","font-size":"12","text-anchor":"end"},v.toFixed(2));}
series.forEach(s=>{let d="",active=false;s.values.forEach((v,i)=>{if(!Number.isFinite(v)){active=false;return;}
d+=(active?"L":"M")+x(i).toFixed(1)+" "+y(v).toFixed(1)+" ";active=true;});
svgEl(root,"path",{d,fill:"none",stroke:s.color,"stroke-width":2.2,"stroke-linejoin":"round"});});
markers.forEach(m=>{if(m.index<0||m.index>=n)return;
const px=x(m.index),py=y(m.price),buy=m.side==="BUY";
svgEl(root,"path",{d:buy?`M${px} ${py-13} l-6 10 h12 Z`:`M${px} ${py+13} l-6 -10 h12 Z`,fill:buy?"#5ee9b1":"#ff8893"});});}
function show(key){const d=DATA.markets[key];if(!d)return;
$("price").textContent=usd(d.price);$("candle").textContent=d.last_candle;
$("equity").textContent=usd(d.equity);$("change").textContent=d.change.toFixed(2)+"% since virtual start";
$("change").className="small "+(d.change>=0?"good":"bad");
$("trades").textContent=d.transactions;$("position").textContent=d.units?"Holding "+d.units.toFixed(6)+" virtual BTC":"No paper position";
$("watch").textContent=d.watch.replace("_"," ");$("watch").style.fontSize="17px";
const marks=d.trades.map(trade=>({index:d.times.findIndex(t=>Math.abs(t-Date.parse(trade.time))<1500),
price:trade.price,side:trade.side}));
chart("priceChart",[{values:d.closes,color:"#72b2ff"},{values:d.sma20,color:"#f5b865"},{values:d.kama,color:"#b49aff"}],310,marks);
chart("equityChart",[{values:d.equity_history,color:"#5be5ac"}],170);
$("votes").replaceChildren();Object.entries(d.votes).forEach(([name,v])=>{const el=document.createElement("div");
el.textContent=name+": "+(v>0?"Bullish observation":v<0?"Bearish observation":"Neutral");
el.className=v>0?"good":v<0?"bad":"muted";$("votes").append(el);});
$("metrics").textContent="RSI (14): "+d.rsi.toFixed(1)+" · MACD histogram: "+d.macd_histogram.toFixed(4)+
" · KAMA: "+usd(d.kama[d.kama.length-1]);}
$("updated").textContent=DATA.updated;Object.entries(DATA.markets).forEach(([key,d])=>{
const option=document.createElement("option");option.value=key;option.textContent=d.name;$("market").append(option);});
$("market").addEventListener("change",e=>show(e.target.value));show($("market").value);
</script></body></html>''';
    return page.replace("__DATA__", payload)
