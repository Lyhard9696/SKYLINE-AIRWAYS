# Aviation Patch — FR24 monde + METAR/TAF + compagnies + alliances/ères

Ce dossier est un **patch autonome prêt à versionner dans GitHub**. Il ne contient aucune clé secrète.

Il fournit :
- FR24 `live/flight-positions/full` côté serveur ;
- mode **monde entier** par tuiles + déduplication `fr24_id` ;
- aucune restriction aux avions au sol ;
- compteurs `positions / en vol / sol estimé / inconnu` ;
- mode `bounds` pour n'interroger que la vue du globe ;
- cache serveur pour éviter une requête FR24 par joueur ;
- livery : `painted_as` > `operating_as` > callsign > neutre ;
- METAR/TAF via AviationWeather.gov côté serveur ;
- photos avion paresseuses via Planespotters (optionnel) ;
- seed de grandes compagnies mondiales + résolution FR24 dynamique ;
- configurations "Prochaines ères" ;
- niveaux/bonus d'alliance ;
- moteur central de modificateurs économiques.

## Quel dossier utiliser ?

Deux variantes backend sont incluses :

- `node-service/` : Node 20 + Express — recommandé si ton projet est JS/TS/React/Vite/Next côté frontend.
- `python-service/` : Python 3.11 + Flask — si ton backend actuel est Python.

**N'en déploie qu'une seule.**

Le dossier `frontend-integration/` contient un client JS utilisable avec les deux backends.

---

## Render — variables

Dans **Render > Environment** :

```text
FR24_API_TOKEN=<ton token production>
FR24_WORLD_STRATEGY=tiles
FR24_CACHE_SECONDS=15
CORS_ORIGIN=https://ton-domaine.example
```

Ne mets jamais le token dans le frontend.

### Important : token production
Le service utilise par défaut :

```text
https://fr24api.flightradar24.com/api
```

et **pas le sandbox**.

Si ton token est un token sandbox, FR24 renverra des données statiques/prédéfinies. Il faut un token API production pour voir le trafic réel.

---

# Pourquoi tu voyais "19 positions / 11 sol"

Le patch ne filtre pas les avions au sol ni les avions en vol.

Un petit nombre de positions vient généralement de :
1. `bounds` trop petit ;
2. `limit` trop faible ;
3. token sandbox ;
4. filtre accidentel (`airports`, `categories`, `altitude_ranges`, etc.) ;
5. appel limité à un aéroport ou une zone.

Le endpoint du patch :

```text
GET /api/fr24/live?scope=world
```

agrège des tuiles mondiales et déduplique les avions.

Exemple de réponse :

```json
{
  "ok": true,
  "scope": "world",
  "provider": "flightradar24",
  "mode": "full",
  "count": 16842,
  "stats": {
    "airborne": 15122,
    "groundEstimated": 1504,
    "unknown": 216
  },
  "data": []
}
```

**Le compteur sol est une estimation d'affichage. Il ne sert jamais à filtrer les données.**

---

# Mode conseillé pour le globe

## Vue monde
```text
/api/fr24/live?scope=world
```

## Quand le joueur zoome
```text
/api/fr24/live?bounds=N,S,W,E
```

Cela permet :
- d'afficher l'ensemble mondial quand le globe est éloigné ;
- de passer à des données ciblées quand on zoome ;
- d'éviter de télécharger des dizaines de milliers d'objets toutes les quelques secondes.

---

# Attention aux crédits FR24

Le mode `tiles` vise la couverture mondiale et peut coûter beaucoup de crédits.

Le cache est donc partagé côté serveur :
- requêtes identiques réutilisées pendant `FR24_CACHE_SECONDS` ;
- plusieurs joueurs ne provoquent pas chacun un nouveau balayage mondial.

Pour réduire la consommation :
```text
FR24_WORLD_STRATEGY=single
```

`single` fait un seul appel monde avec `limit=20000`. C'est moins cher, mais si le résultat atteint exactement 20 000, il peut être plafonné. Le mode `tiles` est le mode prévu pour rechercher une couverture plus complète.

---

# Frontend

Copie/import le module :

```text
frontend-integration/aviation-live-client.js
```

Puis :

```js
import { AviationLiveClient } from "./aviation-live-client.js";

const aviation = new AviationLiveClient({
  apiBase: ""
});

const result = await aviation.getWorldFlights();

console.log(result.count);
console.log(result.stats.airborne);
console.log(result.stats.groundEstimated);
```

Le statut à afficher peut être :

```text
Flightradar24 OK · full · 16842 positions · 15122 en vol · 1504 sol estimé
```

Ne plus afficher seulement :

```text
19 positions / 11 sol
```

sans donner le nombre d'avions en vol.

---

# METAR / TAF

```text
GET /api/aviation/metar?icao=LFPG
GET /api/aviation/taf?icao=LFPG
```

Open-Meteo peut rester pour la météo générale mais n'est plus utilisé comme source METAR/TAF.

---

# Photos

```text
GET /api/aircraft/photo?reg=F-GZND&hex=...
```

À appeler uniquement quand le joueur sélectionne un avion.

Si aucune photo n'existe, le frontend doit afficher un modèle/silhouette neutre — jamais la photo d'une autre compagnie.

---

# Livrées

Ordre strict :

```text
painted_as
operating_as
préfixe callsign connu
UNKNOWN
```

Donc :
- `painted_as=AFR` => Air France ;
- un `A350` sans compagnie fiable n'est **jamais** transformé en Air China simplement parce que c'est un A350.

---

# Prochaines ères

Données :
```text
shared/game/eras.json
```

Endpoint :
```text
GET /api/game/eras
```

Les bonus sont exprimés sous forme de modificateurs économiques et doivent être branchés dans les coûts réels du jeu.

---

# Alliances

Données :
```text
shared/game/alliance-levels.json
shared/game/alliance-goals.json
```

Endpoint :
```text
GET /api/game/alliance-levels
GET /api/game/alliance-goals
```

Calcul générique :
```text
POST /api/game/effective-cost
```

Exemple :

```json
{
  "base": 1000000,
  "modifiers": [
    {"category":"route_creation","mode":"percentage","value":-10}
  ]
}
```

---

# Tests rapides après déploiement

```text
GET /health
GET /api/fr24/live?scope=world
GET /api/fr24/live?bounds=51.5,48.5,0.5,5.5
GET /api/aviation/metar?icao=LFPG
GET /api/aviation/taf?icao=LFPG
GET /api/fr24/airline/AFR
GET /api/game/eras
GET /api/game/alliance-levels
```

Dans `/api/fr24/live?scope=world`, vérifie :
- `count` est nettement supérieur à 19 avec un token production valide ;
- `stats.airborne` existe ;
- `stats.groundEstimated` n'est qu'une sous-partie ;
- des avions avec `altitudeFt > 0` sont présents ;
- `liveryCode` suit `painted_as`.

---

# Déploiement Render — Node

Root directory :
```text
aviation_patch_github/node-service
```

Build command :
```text
npm install
```

Start command :
```text
npm start
```

# Déploiement Render — Python

Root directory :
```text
aviation_patch_github/python-service
```

Build command :
```text
pip install -r requirements.txt
```

Start command :
```text
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60
```

---

# Limite importante

Sans les fichiers de ton dépôt actuel, ce ZIP ne peut pas remplacer automatiquement les composants de ton interface déjà existante. Il fournit cependant le backend/API et la logique de jeu sous forme autonome et intégrable sans exposer le token.
