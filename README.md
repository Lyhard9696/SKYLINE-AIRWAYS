# SKYLINE AIRWAYS — v1.3 Premium Operations

Build basée sur le véritable projet SKYLINE AIRWAYS transmis dans la conversation : FastAPI, SQLAlchemy, MapLibre, catalogue embarqué et interface v1.1 premium.

## Ce que v1.3 apporte

- Globe OPS FR24 mondial : compteur mondial, snapshot tuilé, avions en vol + sol, interpolation visuelle, diagnostic des limites d'abonnement.
- Météo générale robuste : Open-Meteo puis MET Norway en secours.
- METAR / TAF : AviationWeather.gov côté serveur.
- NOTAM réels : Aviation Edge, clé serveur optionnelle mais nécessaire pour activer les données.
- Catalogue : photos paresseuses du type exact via catalogue local puis Wikimedia Commons.
- Fiche avion fermable de façon fiable.
- Hubs premium : achat et améliorations verrouillés par niveau/prérequis/argent, effets réellement appliqués.
- Alliances premium : niveaux, objectifs, membres, réseau, économies, rôles et améliorations communes profitant à tous les membres.
- Niveau & quêtes refondus + cinq Prochaines ères avec effets économiques réels.
- Secours / Sécurité civile / opérations stratégiques refondus et interactifs.
- PWA : invalidation du vieux cache JS/CSS après déploiement.

Voir `CHANGELOG_v1.3.md` pour le détail.

## Déploiement Render

Le dépôt est prévu pour un Web Service Python :

```text
Build: pip install -r requirements.txt
Start: uvicorn main:app --host 0.0.0.0 --port $PORT
Health: /health
```

Variables obligatoires/automatiques :

```text
DATABASE_URL=<PostgreSQL Render>
SECRET_KEY=<secret>
FR24_API_TOKEN=<token FR24 production>
```

Pour les NOTAM réels :

```text
AVIATION_EDGE_API_KEY=<clé Aviation Edge>
```

Le fichier `render.yaml` contient les placeholders `sync: false` pour les secrets.

## FR24

Ne juge plus le Globe avec l'ancien « 13 positions / 6 sol » : ce chiffre venait d'un test local. Utilise :

```text
/api/integrations/fr24/world-summary
```

Il indique combien de positions FR24 suit mondialement et combien ton abonnement a réellement livré au snapshot SKYLINE. Voir `FR24_SETUP_v1.3.md`.

## NOTAM

Voir `NOTAM_SETUP_v1.3.md`.

## Tests

```bash
python -m py_compile main.py models.py logic.py catalog.py
node --check static/game-v130.js
python tests/smoke_v13.py
```

## Base de données

`skyline.db` n'est volontairement pas livré : il peut contenir les comptes/progressions locaux. `data/catalog.sqlite` est le catalogue aéronautique embarqué. Render utilise PostgreSQL et SQLAlchemy crée les nouvelles tables v1.3 automatiquement.

## Droits

Le prototype contient des marques, logos, livrées et photographies de référence. Toute diffusion commerciale nécessite une revue des licences/droits. Les contenus tiers chargés dynamiquement doivent conserver l'attribution requise par leur fournisseur.
