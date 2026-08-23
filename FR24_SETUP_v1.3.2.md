# SKYLINE AIRWAYS v1.3.2 — FR24 sans OOM Render

Le token FR24 reste uniquement côté serveur :

```text
FR24_API_TOKEN=...
FR24_API_BASE_URL=https://fr24api.flightradar24.com/api
FR24_WORLD_CACHE_SECONDS=45
FR24_WORLD_TILE_LIMIT=2200
FR24_WORLD_WORKERS=1
FR24_COUNT_CACHE_SECONDS=30
```

## Fonctionnement du Globe

La v1.3.2 ne télécharge plus toutes les positions du monde au lancement. À faible zoom, `/api/integrations/fr24/world-summary` récupère seulement le compteur global FR24. Après zoom régional, le navigateur appelle `/api/live-traffic/box` avec la bounding box visible.

Le plafond serveur de 2200 protège la RAM de l'instance Render 512 Mo. Le frontend demande 1000, 1600 ou 2200 positions selon le zoom. Les avions au sol et en vol sont conservés.

## Détail d'un avion

Le marqueur de carte contient une position légère. Quand le joueur clique dessus, `/api/live-aircraft/detail?fr24_id=...` récupère la fiche `flight-summary/full` du vol sélectionné uniquement. La photo est ensuite demandée par immatriculation/hex via `/api/live-aircraft/photo`.

Cette séparation évite de charger des milliers de fiches et photos en mémoire.
