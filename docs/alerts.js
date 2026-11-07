"use strict";
/* Optional, browser-only trading research notifications. NO order execution.
   Alerts can run only while this web dashboard is open and allowed by browser. */
(() => {
  const root="https://raw.githubusercontent.com/sjeyles2000-sudo/Ai-trading-bot/";
  const storageKey="aiTraderResearchAlertsV1";
  const id=x=>document.getElementById(x);
  const ALERT_TYPES={momentum:"Momentum research",fomo:"FOMO risk",paper:"Paper transaction",price:"BTC price movement"};
  const CACHE_TTL=2*60*60*1000;
  let active=false,baseline=false,seen=new Set(),lastRadarStamp="",lastPaperStamp="";
  let priceAnchors={binance:null,hyperliquid:null};
  let ring=[];
  function readPreferences(){
    try {const p=JSON.parse(localStorage.getItem(storageKey)||"{}");
      return {enabled:!!p.enabled,types:p.types||{},threshold:([0.5,1,2].includes(Number(p.threshold))?Number(p.threshold):1),
        seen:Array.isArray(p.seen)?p.seen.slice(-100):[]};}
    catch(_){return {enabled:false,types:{},threshold:1,seen:[]};}
  }
  let preferences=readPreferences();
  seen=new Set(preferences.seen);
  function save(){
    try {localStorage.setItem(storageKey,JSON.stringify({enabled:active,types:preferences.types,
      threshold:preferences.threshold,seen:[...seen].slice(-100)}));}catch(_){}
  }
  function chosen(type){return preferences.types[type]!==false;}
  function note(text){id("alert-status").textContent=text;}
  function log(type,message,time=Date.now()){
    const item=document.createElement("div");item.className="line";
    const title=document.createElement("span");title.textContent=ALERT_TYPES[type]+": "+message;
    const dt=document.createElement("small");dt.textContent=new Date(time).toLocaleTimeString();
    item.append(title,dt);
    const view=id("alert-log");view.prepend(item);
    while(view.children.length>8)view.lastElementChild.remove();
  }
  function emit(type,key,message){
    if(!active||!chosen(type)||seen.has(key))return;
    seen.add(key);
    while(seen.size>100)seen.delete(seen.values().next().value);
    log(type,message);save();
    if("Notification" in window&&Notification.permission==="granted"){
      try {const n=new Notification("AI Trader — "+ALERT_TYPES[type],{
        body:message+" · Research/demo only. No real orders.",tag:"ai-trader-"+type+"-"+key.slice(-30)
      });setTimeout(()=>n.close(),9000);}catch(_){}
    }
  }
  const fingerprint=items=>items.join("|").trim();
  function splitTable(md,section){
    const pos=md.indexOf(section);if(pos===-1)return [];
    const body=md.slice(pos+section.length).split(/\n##\s/)[0];
    const rows=body.split(/\r?\n/).filter(s=>s.trim().startsWith("|"));
    return rows.slice(2).map(row=>row.split("|").slice(1,-1).map(s=>s.trim())).filter(r=>r.length>1);
  }
  function fetchText(branch,path){
    const url=root+encodeURIComponent(branch)+"/"+path+"?t="+Date.now();
    return fetch(url,{cache:"no-store",referrerPolicy:"no-referrer"}).then(r=>{
      if(!r.ok)throw new Error("HTTP "+r.status);return r.text();});
  }
  function recentReport(md){
    const match=md.match(/Updated\s+(\d{4}-\d\d-\d\d \d\d:\d\d)\s*UTC/);
    if(!match)return null;
    const ts=Date.parse(match[1].replace(" ","T")+":00Z");
    return Number.isFinite(ts)&&ts<=Date.now()+300000&&Date.now()-ts<CACHE_TTL?match[1]:null;
  }
  async function research(){
    const md=await fetchText("research-results","research/RADAR.md");
    const stamp=recentReport(md);
    if(!stamp)return; // Discard stale or malformed research report
    const rows=splitTable(md,"## 5-minute momentum and FOMO alerts").slice(0,6);
    if(!baseline){lastRadarStamp=stamp;return;}
    if(stamp===lastRadarStamp)return;
    lastRadarStamp=stamp;
    rows.forEach(row=>{
      const [name,signal,move]=row;
      const token=String(signal||"").replace(/\*|\s/g,"");
      const message=(name||"Market")+" · "+token+" · 15m "+(move||"?");
      if(token==="FOMO_RISK")emit("fomo","radar:"+stamp+":"+name+":fomo",message);
      if(token==="BULLISH_WATCH"||token==="BEARISH_WATCH")
        emit("momentum","radar:"+stamp+":"+name+":"+token,message);
    });
  }
  function parseCsv(text){
    const lines=text.trim().split(/\r?\n/);
    return lines.slice(1).filter(Boolean).map(r=>r.split(","));
  }
  async function paper(){
    const text=await fetchText("paper-results","ledger/trades.csv");
    const items=parseCsv(text);
    // First inspection establishes a baseline, not historical notifications.
    if(!baseline){items.forEach(row=>seen.add("trade:"+fingerprint(row)));return;}
    items.slice(-30).forEach(row=>{
      if(row.length<5)return;
      const time=Date.parse(row[0]);
      if(!Number.isFinite(time)||time>Date.now()+300000||Date.now()-time>7*86400000)return;
      const key="trade:"+fingerprint(row);
      emit("paper",key,(row[1]||"Unknown")+" · "+(row[2]||"Simulated event")+
        " at $"+(row[4]||"?")+" · "+row[0]);
    });
  }
  let pollBusy=false;
  async function poll(){
    if(!active||pollBusy)return;
    pollBusy=true;
    const outcomes=await Promise.allSettled([research(),paper()]);
    pollBusy=false;
    if(!baseline){baseline=true;save();note("Alerts on. Watching for NEW research signals and paper transactions.");}
    else if(outcomes.every(x=>x.status==="rejected"))note("Alerts on; report feeds unavailable, checking again later.");
    else note("Alerts on. Last check "+new Date().toLocaleTimeString()+". Browser must remain open.");
  }
  // Movement alerts compare public quotes to rolling 5-minute anchors.
  // This is price research only, not a validated strategy.
  function checkPrices(){
    if(!active||!chosen("price"))return;
    for(const name of ["binance","hyperliquid"]){
      const market=typeof markets==="undefined"?null:markets[name];
      if(!market||!Number.isFinite(market.price)||!market.updated||
          Date.now()-market.updated>45000)continue;
      const anchor=priceAnchors[name];
      if(!anchor){priceAnchors[name]={value:market.price,time:Date.now()};continue;}
      const elapsed=Date.now()-anchor.time;
      if(elapsed>=300000){priceAnchors[name]={value:market.price,time:Date.now()};continue;}
      const move=100*(market.price/anchor.value-1);
      const threshold=preferences.threshold;
      if(Math.abs(move)>=threshold){
        const bin=Math.floor(anchor.time/300000);
        emit("price","price:"+name+":"+bin+":"+(move>0?"up":"down"),
          name+" BTC "+(move>0?"rose ":"fell ")+Math.abs(move).toFixed(2)+"% since the observation window began");
        priceAnchors[name]={value:market.price,time:Date.now()};
      }
    }
  }
  function configure(){
    const checkboxes={fomo:id("alert-fomo"),momentum:id("alert-momentum"),
      paper:id("alert-paper"),price:id("alert-price")};
    Object.entries(checkboxes).forEach(([name,input])=>{
      input.checked=chosen(name);
      input.addEventListener("change",()=>{preferences.types[name]=input.checked;save();});
    });
    const threshold=id("alert-threshold");
    threshold.value=String(preferences.threshold);
    threshold.addEventListener("change",()=>{preferences.threshold=Number(threshold.value);save();});
    function updateButton(){
      id("alerts-toggle").textContent=active?"Turn alerts off":"Enable notifications";
      id("alert-mode").textContent=active?"ON (browser open)":"OFF";
    }
    id("alerts-toggle").addEventListener("click",async()=>{
      if(active){active=false;baseline=false;priceAnchors={binance:null,hyperliquid:null};save();updateButton();note("Alerts off.");return;}
      if(!("Notification" in window)){note("This browser does not support desktop notifications. In-page alerts only.");}
      else if(Notification.permission==="default"){
        try{await Notification.requestPermission();}catch(_){}
      }
      active=true;baseline=false;priceAnchors={binance:null,hyperliquid:null};
      save();updateButton();await poll();
      if("Notification" in window&&Notification.permission!=="granted")
        note("Alerts on, but browser pop-ups are blocked. New signals appear in the in-page alert log.");
    });
    updateButton();
    note("Alerts off. Press Enable to opt in. No automatic trades.");
  }
  configure(); // Always opt-in again per browser session, regardless of old settings.
  setInterval(poll,60000);
  setInterval(checkPrices,15000);
})();
