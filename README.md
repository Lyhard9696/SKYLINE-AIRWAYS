# SKYLINE AIRWAYS — v1.3.1 Relevant OPS

Build FastAPI/SQLAlchemy/MapLibre du projet SKYLINE AIRWAYS. Cette révision remplace la dépendance NOTAM payante de v1.3 par une veille opérationnelle gratuite et ciblée.

## v1.3.1

- NOTAM : **FAA NOTAM Search public**, sans compte et sans clé API.
- Le jeu n'affiche plus un mur de NOTAM mondial : il surveille uniquement les hubs possédés et les aéroports réellement utilisés comme départ, arrivée ou escale.
- Les restrictions d'espace aérien à fort impact sont priorisées seulement lorsqu'une route du joueur traverse la zone surveillée. Le texte et la sévérité proviennent des NOTAM live ; Skyline n'invente pas une fermeture.
- Météo aviation : METAR/TAF et SIGMET mondiaux via **AviationWeather.gov**, sans clé. Les SIGMET sont filtrés contre les corridors des routes du joueur.
- Météo générale : Open-Meteo avec MET Norway en secours.
- Globe : seuls les risques pertinents pour la compagnie sont ajoutés à la carte OPS.
- FR24 : snapshot mondial tuilé, en vol + au sol, avec distinction entre trafic suivi par FR24 et positions réellement livrées par le plan API.
- Le reste de v1.3 est conservé : hubs verrouillés par niveau/argent, alliances avec avantages communs, R&D/ères, opérations spécialisées, catalogue et fiches aéronef.

## Déploiement Render

```text
Build: pip install -r requirements.txt
Start: uvicorn main:app --host 0.0.0.0 --port $PORT
Health: /health
```

Variables principales :

```text
DATABASE_URL=<PostgreSQL Render>
SECRET_KEY=<secret>
FR24_API_TOKEN=<token FR24 production>
```

Aucune clé NOTAM, METAR, TAF ou SIGMET n'est nécessaire. Options de cache :

```text
OPS_NOTAM_CACHE_SECONDS=600
OPS_SIGMET_CACHE_SECONDS=180
OPS_WATCH_FIRS=
```

`OPS_WATCH_FIRS` est facultatif et permet d'ajouter d'autres FIR à la veille prioritaire, séparées par des virgules.

## Endpoints aviation

```text
/api/aviation/metar?icao=LFPG
/api/aviation/taf?icao=LFPG
/api/aviation/notams?icao=LFPG
/api/aviation/notam/status
/api/ops/intelligence
```

`/api/ops/intelligence` renvoie uniquement les alertes utiles au réseau du joueur : hubs, départs/arrivées, météo sévère et restrictions croisant ses propres rotations.

## Tests

```bash
python -m py_compile main.py models.py logic.py catalog.py
node --check static/game-v131.js
python tests/smoke_v13.py
```

## Base de données

`skyline.db` n'est volontairement pas livré : il peut contenir les comptes/progressions locaux. `data/catalog.sqlite` reste le catalogue aéronautique embarqué. Render utilise PostgreSQL.

## Limites des sources

FAA NOTAM Search est un service public de consultation et non une API développeur avec SLA. Skyline utilise donc un cache et un comportement de repli propre. AviationWeather.gov est la source publique pour METAR/TAF/SIGMET. Ces données sont destinées au gameplay et à l'immersion du simulateur, pas à la préparation d'un vol réel.
