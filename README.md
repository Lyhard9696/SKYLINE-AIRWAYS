# SKYLINE AIRWAYS — v1.2 Live World

Version basée directement sur le projet SKYLINE AIRWAYS v1.1 fourni par le propriétaire du projet.

## Principales évolutions v1.2

### Globe FR24 mondial
- Le diagnostic FR24 local reste un petit test autour du hub, mais il est maintenant explicitement marqué comme tel.
- Le Globe utilise `/api/live-traffic/world` à faible zoom.
- Le backend découpe le monde en 12 zones FR24, fusionne les résultats et déduplique par `fr24_id`.
- Aucun filtre ne supprime les avions au sol ou les avions en vol : tous les enregistrements live récupérés sont conservés.
- Les compteurs distinguent `positions`, `en vol` et `sol`.
- À fort zoom, le Globe repasse sur `/api/live-traffic/box` avec une limite jusqu'à 20 000 positions.
- Le rendu mondial utilise une source GeoJSON MapLibre et des couches GPU au lieu de créer des milliers de marqueurs DOM.
- Le snapshot mondial est partagé en mémoire entre les joueurs et compressé via GZip.

Variables Render :

```text
FR24_API_TOKEN=<token production>
FR24_API_BASE_URL=https://fr24api.flightradar24.com/api
FR24_WORLD_CACHE_SECONDS=120
FR24_WORLD_TILE_LIMIT=20000
FR24_WORLD_WORKERS=3
```

`FR24_API_TOKEN` reste exclusivement côté serveur.

> Important : une couverture mondiale FR24 consomme beaucoup plus de crédits qu'une petite bounding box. Augmenter `FR24_WORLD_CACHE_SECONDS` réduit fortement la consommation si nécessaire.

### Identification compagnie / livrée
Pour le trafic réel, SKYLINE ne choisit plus une compagnie à partir du type d'avion.

Ordre :
1. `painted_as` — livrée réellement portée ;
2. `operating_as` — opérateur ;
3. aucune supposition si les données sont absentes.

La fiche d'un vol réel affiche séparément **Livrée** et **Opéré par**. Les grandes compagnies sont résolues depuis un cache interne et les autres peuvent être résolues via l'endpoint statique FR24.

### Photos du trafic réel
- Recherche uniquement au clic sur un avion.
- Recherche par immatriculation puis hex via le proxy backend Planespotters.
- Cache positif 24 h / négatif 6 h.
- Si aucune photo exacte n'est trouvée, pas de photo d'une autre compagnie.
- Deux fallbacks locaux sont explicitement liés à la bonne combinaison type/livrée : A350 Air France (`AFR`) et A350 Air China (`CCA`).
- L'A350 générique du catalogue n'utilise plus une photo de compagnie comme s'il s'agissait d'une photo neutre.

### METAR / TAF
Nouveaux endpoints serveur :

```text
GET /api/aviation/metar?icao=LFPG
GET /api/aviation/taf?icao=LFPG
```

Source : AviationWeather.gov. Open-Meteo reste utilisé pour les conditions météo générales/cockpit.

### NOTAM
Aucun faux NOTAM n'est généré. Tant qu'aucun fournisseur opérationnel n'est branché :

```text
NOTAM : données temps réel temporairement indisponibles.
```

Endpoint : `/api/aviation/notam/status`.

### Prochaines ères
Les ères sont désormais une vraie progression calculée depuis le niveau de carrière et les niveaux R&D :
1. Optimisation moderne
2. Transition énergétique
3. Aviation ultra-efficiente
4. Nouvelles propulsions régionales
5. Réseau intelligent

Les bonus des ères sont appliqués au moteur économique : carburant, maintenance, achat avion, création de ligne, formation et demande selon l'ère.

### Alliances
Les alliances de joueurs gardent les données v1.1 existantes et ajoutent :
- niveaux 1 à 10 ;
- bonus carburant, formation, maintenance, achat/leasing et ouverture de lignes ;
- bonus de demande/correspondance ;
- XP gagné grâce aux vols et contributions ;
- objectifs collectifs hebdomadaires ;
- économies réellement suivies ;
- contribution par membre ;
- passagers 30 jours et lignes par membre ;
- réseau mondial de hubs/lignes avec filtres ;
- connexions entre hubs membres ;
- activité des économies ;
- chat existant conservé.

Les alliances aériennes SkyTeam, Star Alliance et oneworld possèdent également des bonus économiques réels.

### Frais de création de ligne
L'ouverture d'une nouvelle route possède maintenant un coût calculé à partir de la distance et de l'appareil. Les réductions d'alliance/ère sont appliquées réellement et le gain d'alliance est journalisé.

## Installation GitHub / Render

Décompresser le ZIP puis placer son **contenu** à la racine du dépôt GitHub :

```text
main.py
models.py
logic.py
catalog.py
requirements.txt
render.yaml
data/
static/
templates/
```

Render peut ensuite redéployer automatiquement.

La base locale `skyline.db` du projet transmis n'est volontairement **pas incluse** dans le ZIP GitHub : elle peut contenir des comptes/progressions locales et Render utilise PostgreSQL. Les nouvelles tables v1.2 sont créées automatiquement par SQLAlchemy au démarrage.

## Tests effectués avant packaging
- compilation Python de `main.py`, `models.py`, `logic.py`, `catalog.py` ;
- validation syntaxique de `static/game-v120.js` avec Node ;
- démarrage de FastAPI avec une base SQLite temporaire ;
- création de compte et achat d'un hub ;
- chargement état / R&D / alliances ;
- création d'une alliance joueur ;
- bonus de création de route effectivement appliqué et journalisé ;
- test unitaire local de normalisation FR24 : avion en vol + avion au sol conservés ;
- agrégateur mondial FR24 testé avec déduplication simulée.

## Données et droits
Le projet contient des visuels et marques fournis avec le prototype. Avant une diffusion commerciale, vérifier les droits de marque, de logo, de livrée et de photographie. Les photos live obtenues depuis un fournisseur tiers doivent conserver l'attribution requise par ce fournisseur.
