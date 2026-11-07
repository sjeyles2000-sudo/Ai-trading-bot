"use strict";
const $ = id => document.getElementById(id);
const ROOT = "https://raw.githubusercontent.com/sjeyles2000-sudo/Ai-trading-bot/";
const ns = "http://www.w3.org/2000/svg";
const markets = {
  binance: {name:"Binance BTC/USDT spot",price:null,updated:0},
  hyperliquid: {name:"Hyperliquid BTC perpetual",price:null,updated:0}
};
let equities=[],trades=[],radarMarkdown="",walletMarkdown="",lastPaperCheck=null;
const money = n => Number.isFinite(n) ? new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:2}).format(n) : "—";
const when = value => {const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleString():"Unknown";};
function line(container,left,right,rightClass=""){
  const div=document.createElement("div");div.className="line";
  const a=document.createElement("span");a.textContent=left;
  const b=document.createElement("strong");b.textContent=right;b.className=rightClass;
  div.append(a,b);container.append(div);
}
async function loadText(url){
  const response=await fetch(url+"?v="+Date.now(),{cache:"no-store",referrerPolicy:"no-referrer"});
  if(!response.ok)throw new Error("HTTP "+response.status);
  return await response.text();
}
const source=(branch,path)=>ROOT+encodeURIComponent(branch)+"/"+path.split("/").map(encodeURIComponent).join("/");
function csv(text){
  const rows=text.trim().split(/\r?\n/).filter(Boolean);
  if(!rows.length)return [];
  const headers=rows.shift().split(",");
  return rows.map(row=>{
    const vals=row.split(",");
    const obj={};headers.forEach((h,i)=>obj[h]=vals[i]??"");
    return obj;
  });
}
async function getBinance(){
  const response=await fetch("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT",{cache:"no-store"});
  if(!response.ok)throw new Error("Binance "+response.status);
  const value=Number((await response.json()).price);
  if(!Number.isFinite(value)||value<=0)throw new Error("Invalid Binance quote");
  return value;
}
async function getHyperliquid(){
  const response=await fetch("https://api.hyperliquid.xyz/info",{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:"allMids"}),cache:"no-store"
  });
  if(!response.ok)throw new Error("Hyperliquid "+response.status);
  const value=Number((await response.json()).BTC);
  if(!Number.isFinite(value)||value<=0)throw new Error("Invalid Hyperliquid quote");
  return value;
}
async function refreshPrices(){
  const feeds=[["binance",getBinance],["hyperliquid",getHyperliquid]];
  const outcomes=await Promise.allSettled(feeds.map(([,get])=>get()));
  let ok=0;
  outcomes.forEach((outcome,i)=>{
    const [key]=feeds[i];
    if(outcome.status==="fulfilled"){
      markets[key].price=outcome.value;markets[key].updated=Date.now();ok++;
    }
    const age=$(key+"-age");
    if(outcome.status==="fulfilled")age.textContent="Public quote checked "+when(Date.now());
    else age.textContent="Quote unavailable; "+(markets[key].updated?"last updated "+when(markets[key].updated):"no current quote");
    $(key+"-price").textContent=money(markets[key].price);
  });
  $("market-status").textContent=ok===2?"Both public quote feeds responded":
     ok===1?"One quote feed responded; some prices may be stale":"Price feeds unavailable; previous prices may be stale";
  $("clock").textContent="checked "+when(Date.now());
}
function renderEquities(){
  const key=$("market-select").value;
  const name=markets[key].name;
  const points=equities.filter(x=>x.market===name).slice(-250);
  const svg=$("equity-chart");svg.replaceChildren();
  if(!points.length){
    const n=document.createElementNS(ns,"text");n.setAttribute("x",20);n.setAttribute("y",120);
    n.setAttribute("fill","#a7b8d0");n.textContent="No paper snapshots yet";svg.append(n);return;
  }
  const vals=points.map(x=>Number(x.virtual_equity_usd)).filter(Number.isFinite);
  if(!vals.length)return;
  let low=Math.min(...vals),high=Math.max(...vals);const pad=Math.max((high-low)*.1,high*.0001,1);
  low-=pad;high+=pad;
  const X=i=>45+i*625/Math.max(vals.length-1,1);
  const Y=v=>18+(high-v)/(high-low)*175;
  for(let i=0;i<4;i++){
    const v=low+(high-low)*i/3;
    const l=document.createElementNS(ns,"line");l.setAttribute("x1","45");l.setAttribute("x2","684");
    l.setAttribute("y1",Y(v));l.setAttribute("y2",Y(v));l.setAttribute("stroke","#273b5a");svg.append(l);
    const t=document.createElementNS(ns,"text");t.setAttribute("x","40");t.setAttribute("y",Y(v)+5);
    t.setAttribute("fill","#94aac9");t.setAttribute("font-size","11");
    t.setAttribute("text-anchor","end");t.textContent=v.toFixed(0);svg.append(t);
  }
  const path=document.createElementNS(ns,"path");
  path.setAttribute("d",vals.map((v,i)=>(i?"L":"M")+X(i).toFixed(1)+","+Y(v).toFixed(1)).join(" "));
  path.setAttribute("fill","none");path.setAttribute("stroke","#65dda9");path.setAttribute("stroke-width","3");svg.append(path);
}
function renderPaper(){
  for(const key of ["binance","hyperliquid"]){
    const name=markets[key].name,points=equities.filter(x=>x.market===name);
    const point=points[points.length-1];
    const amount=point?Number(point.virtual_equity_usd):NaN;
    $(key+"-equity").textContent=money(amount);
    $(key+"-meta").textContent=point?"Saved snapshot "+when(point.time_utc)+" · BTC units "+point.btc_units:"No successful paper snapshot yet";
  }
  renderEquities();
  const list=$("trades-list");list.replaceChildren();
  $("trades-status").textContent=trades.length?trades.length+" recorded simulated transactions":"No simulated orders recorded yet";
  for(const item of trades.slice(-8).reverse()){
    line(list,when(item.time_utc)+" · "+item.market+" · "+item.side,
      money(Number(item.virtual_price_usd))+(item.quantity_btc?" · "+item.quantity_btc+" BTC":""));
  }
}
function markdownTable(text,section,limit=6){
  const start=text.indexOf(section);
  if(start===-1)return [];
  const rest=text.slice(start+section.length);
  const table=rest.split(/\n##\s/)[0].split(/\r?\n/).filter(l=>l.trim().startsWith("|"));
  return table.slice(2,2+limit).map(l=>l.split("|").slice(1,-1).map(s=>s.trim().replace(/\\`/g,""))).filter(row=>row.length>1);
}
function renderRadar(){
  const root=$("radar-cards");root.replaceChildren();
  const rows=markdownTable(radarMarkdown,"## 5-minute momentum and FOMO alerts",4);
  $("radar-status").textContent=rows.length?"Latest saved GitHub radar report (not streaming)":"No radar results available";
  rows.forEach(r=>line(root,r[0],r[1]+" · "+(r[2]||"")+" 15m",r[1]==="FOMO_RISK"?"warning":""));
  if(!rows.length)line(root,"Radar status","Unavailable");
}
function renderWallets(){
  const root=$("wallets-list");root.replaceChildren();
  const rows=markdownTable(walletMarkdown,"# Public wallet research leaderboard",5);
  $("wallet-status").textContent=rows.length?"Reported public leaderboard; unaudited and delayed":"Wallet report unavailable";
  rows.forEach(r=>line(root,(r[0]||"").slice(0,12)+"…",r[2]||"PnL not reported"));
  if(!rows.length)line(root,"Wallet status","Unavailable");
}
async function refreshResearch(){
  const feeds=[
    ["radar",source("research-results","research/RADAR.md")],
    ["wallet",source("research-results","research/WALLETS.md")]
  ];
  const results=await Promise.allSettled(feeds.map(([,url])=>loadText(url)));
  results.forEach((r,i)=>{
    if(r.status==="fulfilled"){
      if(i===0)radarMarkdown=r.value;else walletMarkdown=r.value;
    }
  });
  renderRadar();renderWallets();
}
async function refreshPaper(){
  const feeds=[
    ["trades",source("paper-results","ledger/trades.csv")],
    ["equities",source("paper-results","ledger/equity.csv")]
  ];
  const results=await Promise.allSettled(feeds.map(([,url])=>loadText(url)));
  if(results[0].status==="fulfilled")trades=csv(results[0].value);
  if(results[1].status==="fulfilled")equities=csv(results[1].value);
  renderPaper();
}
$("market-select").addEventListener("change",renderEquities);
refreshPrices();refreshPaper();refreshResearch();
setInterval(refreshPrices,15000);
setInterval(refreshPaper,60000);
setInterval(refreshResearch,300000);
