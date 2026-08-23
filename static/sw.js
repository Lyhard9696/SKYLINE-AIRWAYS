const CACHE='skyline-v110-premium-functional-v1';
const CORE=['/static/icon-192.png','/static/icon-512.png'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).catch(()=>{}));});
self.addEventListener('activate',e=>e.waitUntil((async()=>{for(const k of await caches.keys())if(k!==CACHE)await caches.delete(k);await self.clients.claim();})()));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);
  const isCode=e.request.mode==='navigate'||u.pathname.endsWith('.js')||u.pathname.endsWith('.css')||u.pathname.endsWith('.html');
  if(isCode){e.respondWith(fetch(e.request,{cache:'no-store'}));return;}
  e.respondWith(fetch(e.request).then(r=>{if(r.ok&&u.origin===location.origin){const c=r.clone();caches.open(CACHE).then(x=>x.put(e.request,c)).catch(()=>{});}return r;}).catch(()=>caches.match(e.request)));
});
