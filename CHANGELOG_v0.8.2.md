# SKYLINE AIRWAYS v0.8.2 — Runtime Hotfix

- Corrige `managementTab is not defined` sur Safari/iOS en initialisant l'état de gestion avant tout callback.
- Protège les rafraîchissements contre un mélange de versions de `renderOwnedHubs`.
- Charge désormais `/static/game-v082.js` pour contourner définitivement les anciens caches PWA.
- Le service worker ne met plus en cache HTML/JS/CSS et supprime les anciens caches SKYLINE à l'activation.
- Ajoute `window.SKYLINE_BUILD = 0.8.2-runtime-hotfix` pour diagnostic navigateur.
