/* AI Trader read-only mobile notification worker.
   Does not use PushManager, periodic background sync, any exchange keys or orders.
   Active page asks this worker to display new research alerts when supported. */
"use strict";
self.addEventListener("install", () => { self.skipWaiting(); });
self.addEventListener("activate", event => { event.waitUntil(self.clients.claim()); });
self.addEventListener("message", event => {
  const payload=event.data;
  if(!payload || payload.type!=="SHOW_RESEARCH_ALERT" || typeof payload.title!=="string" ||
      typeof payload.body!=="string" || typeof payload.tag!=="string")return;
  const title=payload.title.slice(0,120);
  const body=payload.body.slice(0,250);
  const tag=payload.tag.slice(0,110);
  event.waitUntil(self.registration.showNotification(title,{
    body,tag,renotify:false,data:{url:self.registration.scope}
  }));
});
self.addEventListener("notificationclick", event=>{
  event.notification.close();
  event.waitUntil(self.clients.matchAll({type:"window",includeUncontrolled:true}).then(async clients=>{
    const existing=clients.find(c=>c.url.startsWith(self.registration.scope));
    if(existing){await existing.focus();return;}
    if(self.clients.openWindow)await self.clients.openWindow(self.registration.scope);
  }));
});
