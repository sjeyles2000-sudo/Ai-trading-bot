"use strict";
/* Read-only paper account health checks and clearly labelled historical research.
   No credentials, order execution, wallet access, or trade recommendations. */
(() => {
  const root = "https://raw.githubusercontent.com/sjeyles2000-sudo/Ai-trading-bot/";
  const $ = id => document.getElementById(id);
  const money = n => Number.isFinite(n) ? new Intl.NumberFormat("en-US", {
    style:"currency", currency:"USD", maximumFractionDigits:2
  }).format(n) : "—";
  const now = () => Date.now();
  const freshHours = 3; // scheduled jobs can be late; show amber when aged
  const markets = {
    binance: "Binance BTC/USDT spot",
    hyperliquid: "Hyperliquid BTC perpetual"
  };
  function display(id, value) { $(id).textContent = value; }
  function parseCsv(text) {
    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) return [];
    const header = lines.shift().split(",");
    return lines.filter(Boolean).map(line => {
      const cells = line.split(",");
      return Object.fromEntries(header.map((h, i) => [h, cells[i] || ""]));
    });
  }
  async function read(path) {
    const url = root + "paper-results/" + path + "?v=" + now();
    const res = await fetch(url, {cache:"no-store",referrerPolicy:"no-referrer"});
    if (!res.ok) throw new Error("Paper snapshot HTTP " + res.status);
    return res.text();
  }
  function timeMs(value) {
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) ? timestamp : NaN;
  }
  function snapshots(rows, name) {
    const valid = rows.filter(r => r.market === name).map(r => ({
      t: timeMs(r.time_utc), equity:Number(r.virtual_equity_usd)
    })).filter(r => Number.isFinite(r.t) && Number.isFinite(r.equity) && r.equity >= 0);
    valid.sort((a,b)=>a.t-b.t);
    return valid;
  }
  function maxDrawdown(values) {
    let high = 10000, dd = 0;
    for (const v of values) {
      high=Math.max(high,v);
      dd=Math.max(dd, high>0 ? (high-v)/high : 0);
    }
    return dd*100;
  }
  function health(latest) {
    if (!latest || latest > now()+300000) return {text:"Invalid or future-dated report", cls:"bad"};
    const age = (now()-latest)/3600000;
    if (age<0 || !Number.isFinite(age)) return {text:"Invalid saved timestamp",cls:"bad"};
    if (age > freshHours) return {text:"Stale paper snapshot · "+age.toFixed(1)+"h old",cls:"warning"};
    return {text:"Recent paper snapshot · "+age.toFixed(1)+"h old",cls:"good"};
  }
  function metricRow(node, label, value, cls="") {
    const el=document.createElement("div");el.className="line";
    const a=document.createElement("span");a.textContent=label;
    const b=document.createElement("strong");b.textContent=value;b.className=cls;
    el.append(a,b);node.append(el);
  }
  async function refresh() {
    const status=$("performance-status");
    const results=await Promise.allSettled([
      read("ledger/equity.csv"), read("ledger/trades.csv")
    ]);
    if (results[0].status!=="fulfilled" || results[1].status!=="fulfilled") {
      status.textContent="Paper report unavailable — metrics not verified. Last successful display must not be treated as current.";
      status.className="hint warning";
      $("performance-list").replaceChildren();
      return;
    }
    const rows=parseCsv(results[0].value);
    const trades=parseCsv(results[1].value);
    const list=$("performance-list");list.replaceChildren();
    for (const [key,name] of Object.entries(markets)) {
      const series=snapshots(rows,name);
      const last=series.at(-1);
      const relevantTrades=trades.filter(t=>t.market===name);
      const pnl=last ? last.equity-10000 : NaN;
      const pct=last ? 100*(last.equity/10000-1) : NaN;
      const dd=series.length ? maxDrawdown(series.map(x=>x.equity)) : NaN;
      metricRow(list,name+" · recorded virtual P/L",
        Number.isFinite(pnl) ? money(pnl)+" ("+(pct>=0?"+":"")+pct.toFixed(3)+"%)" : "No data",
        Number.isFinite(pnl) ? (pnl<0?"bad":pnl>0?"good":"") : "");
      metricRow(list,name+" · maximum sampled drawdown",
        Number.isFinite(dd) ? dd.toFixed(3)+"%" : "No data");
      metricRow(list,name+" · simulated transactions",String(relevantTrades.length));
      const h=health(last?.t);
      metricRow(list,name+" · report age",h.text,h.cls);
    }
    const latest = Math.max(...Object.values(markets).map(name =>
      snapshots(rows,name).at(-1)?.t || 0));
    const h=health(latest);
    status.textContent = "Saved paper data only · "+h.text+" · not a live exchange account";
    status.className = "hint "+h.cls;
  }
  const latestResearch = $("strategy-lab-link");
  latestResearch.href="https://github.com/sjeyles2000-sudo/Ai-trading-bot/pull/11";
  refresh();
  setInterval(refresh,60000);
})();
