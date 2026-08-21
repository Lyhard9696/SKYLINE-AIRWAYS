
const CACHE="skyline-v02";
const ASSETS=["/","/static/app.css","/static/app.js","/static/icon-192.png","/static/assets/hub_level_1.png"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener("fetch",e=>e.respondWith(fetch(e.request).catch(()=>caches.match(e.request))));
