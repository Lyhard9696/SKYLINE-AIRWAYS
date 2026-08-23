# SKYLINE AIRWAYS v1.3.4 — FR24 hotfix

- Corrige le diagnostic `Flightradar24 · MONDE` de v1.3.3.
- Le endpoint FR24 `/live/flight-positions/count` exige au moins un filtre; v1.3.3 l’appelait sans filtre.
- Le dashboard mondial ne lance plus de requête count planétaire.
- Le globe reste viewport-adaptive: positions chargées uniquement après zoom, en vol comme au sol.
- Réduit les appels et protège la mémoire Render 512 Mo ainsi que les crédits FR24.
- Les appels count restent disponibles uniquement avec des bounds explicites côté backend.
