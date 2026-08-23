# SKYLINE AIRWAYS — v0.8 REALISM RESTORE

> **Important v0.8** — cette build corrige la régression JavaScript de la v0.7.1, restaure les vues et interactions perdues, rétablit météo + trafic, ajoute le catalogue photo et les activités Secours / Sécurité civile / Opérations stratégiques. Voir `CHANGELOG_v0.8.md` et `DEPLOY_v0.8.md`.


Mise à jour jouable de SKYLINE AIRWAYS pour Render, iPhone/iPad et PC. Cette version conserve le moteur full-stack de la v0.5.1 Stability et refond l’expérience autour d’une interface plus réaliste, plus claire et moins « science-fiction ».

## Installation depuis GitHub

Décompresse le ZIP puis envoie **le contenu du dossier** à la racine du dépôt GitHub existant. Les fichiers doivent rester organisés ainsi :

```text
main.py
models.py
logic.py
catalog.py
requirements.txt
render.yaml
README.md
data/
static/
templates/
```

Tu peux laisser Render redéployer automatiquement après le commit.

Commit conseillé :

```text
SKYLINE v0.8 Realism Restore
```

La base PostgreSQL existante reste compatible. Les nouvelles tables v0.6 sont créées automatiquement au démarrage.

## Nouveautés principales

### Nouvelle direction visuelle

- interface aviation premium contemporaine ;
- palette claire blanc cassé / bleu aviation / or discret ;
- cartes et images satellite restent au centre du jeu ;
- moins d’éléments « futuristes » et davantage d’ergonomie de vraie application de gestion aérienne ;
- nouvelle page **Accueil** avec progression, KPI, hub principal, quêtes, équipages et vols en cours ;
- navigation mobile simplifiée à six onglets ;
- menu « Plus » pour les écrans secondaires.

### Niveau joueur et progression

Le niveau joueur est calculé à partir de :

- rotations réellement terminées ;
- quêtes quotidiennes récupérées ;
- hubs ;
- avions ;
- routes ;
- personnel ;
- améliorations des hubs ;
- réputation gagnée.

Les grandes phases affichées dans le jeu sont : Fondateur, Compagnie internationale, Groupe aérien puis Opérateur mondial.

### Quêtes quotidiennes

Trois objectifs journaliers dynamiques :

- rotations terminées ;
- passagers transportés ;
- satisfaction du hub principal.

Une quête terminée peut être récupérée depuis l’accueil et donne de l’argent + de l’XP.

### Satisfaction propre à chaque hub

Chaque hub possède désormais :

- une note de satisfaction globale ;
- ponctualité ;
- embarquement ;
- sécurité ;
- bagages ;
- confort ;
- accès.

La note dépend notamment des améliorations du hub, infrastructures acquises, personnel disponible et congestion opérationnelle.

### CDG, Nice, Limoges et profils locaux

La v0.6 ajoute une couche de profil réaliste pour différencier les hubs. Exemples :

- **CDG / LFPG** : grand hub intercontinental, RER B, TGV, RoissyBus, taxi/VTC ;
- **Nice / LFMN** : hub premium méditerranéen, tram L2/L3, tourisme, business et saisonnalité ;
- **Limoges / LFBL** : aéroport régional, bus/navette, route, taxi et développement progressif.

Le moteur possède aussi des profils pour plusieurs grands hubs mondiaux et un comportement générique selon la catégorie réelle de l’aéroport.

### Hub aérien amélioré

- les fenêtres « Explore ton aéroport » et « Globe 360 » ne bloquent plus l’écran au chargement ;
- les inspecteurs sont fermés par défaut et ne s’ouvrent qu’après un clic utile ;
- les terminaux OpenStreetMap sont maintenant récupérés lorsque disponibles ;
- terminaux, pistes, taxiways, gates et parkings restent visibles sur le fond satellite ;
- gates/parkings/pistes non acquis restent gris/verrouillés ;
- les anciennes grosses pastilles d’amélioration ne sont plus l’affichage principal ;
- les marqueurs de services sont masqués par défaut et peuvent être activés avec le bouton Services.

### Équipages : recrutement manuel, affectation automatique

Le joueur recrute ses pilotes et PNC mais ne crée pas les plannings à la main.

OPS calcule automatiquement :

- qualification appareil ;
- pilotes disponibles au hub ;
- pilotes requis sur le vol ;
- équipage renforcé sur long-courrier ;
- effectif recommandé pour permettre la rotation et le repos ;
- couverture du pool équipage ;
- risque fatigue ;
- personnel contractuel temporaire si l’effectif réellement requis manque.

Exemple : un court/moyen-courrier utilise normalement 2 pilotes en service, mais un pool de 4 pilotes par appareil est recommandé pour que l’exploitation reste confortable. Un très long-courrier peut utiliser 4 pilotes sur le même vol et nécessiter un pool plus important pour les rotations suivantes.

### Banques réelles par pays

L’espace Finance propose désormais des banques différentes selon le pays du hub principal, sans intégrer leurs logos dans le dépôt.

Exemples :

- France : BNP Paribas, Crédit Agricole, Société Générale, Caisse d’Épargne, HSBC Continental Europe ;
- Royaume-Uni : HSBC UK, Barclays, Lloyds Bank ;
- États-Unis : JPMorgan Chase, Bank of America, Citi ;
- Japon : MUFG, SMBC ;
- Émirats : Emirates NBD, First Abu Dhabi Bank ;
- Espagne : Santander, BBVA, CaixaBank ;
- Mexique : BBVA México, Banorte, HSBC México.

Chaque banque possède un taux de base, un plafond, un niveau joueur minimal et un positionnement différent.

### Hôtels géolocalisés

L’espace Hôtels distingue :

1. **partenariats hôteliers** proposés selon le marché du hub ;
2. **hôtels appartenant au groupe**, beaucoup plus tardifs.

Les partenariats demandent un niveau joueur et une satisfaction minimum. Construire son propre hôtel demande le niveau joueur 20 et une satisfaction de hub d’au moins 70 %.

### Création de rotation sur iPhone

Le formulaire de création de ligne est désormais replié sur mobile. Il ne prend plus tout l’écran en permanence : le bouton « Créer une nouvelle rotation » l’ouvre uniquement quand le joueur en a besoin.

## Simulation des vols

`SIM_SPEED = 3.0` : environ 33 % du temps réel.

Un vol de 8 h réelles dure donc environ 2 h 40 dans le jeu. Les phases sol restent simulées : nettoyage, catering, ravitaillement, embarquement, pushback, taxi, vol, taxi arrivée et débarquement.

## Globe, trafic et météo

- MapLibre en projection globe ;
- fond satellite Esri ;
- radar météo RainViewer lorsque disponible ;
- Open-Meteo pour les conditions cockpit ;
- couche jour/nuit ;
- routes SKYLINE ;
- avions SKYLINE ;
- trafic FR24 si `FR24_API_TOKEN` officiel est configuré ;
- sinon OpenSky lorsqu’il répond.

## Données embarquées

- 85k+ aéroports/héliports/bases ;
- 591 types d’aéronefs ;
- données pistes ;
- catalogue avion et variantes selon les données disponibles.

## Render / stabilité

Le `render.yaml` conserve :

- un seul Web Service ;
- PostgreSQL `skyline-db` ;
- `MALLOC_ARENA_MAX=2` ;
- caches mémoire bornés ;
- limites de trafic et géométrie OSM adaptées aux 512 Mo du plan gratuit.

## Vérifications effectuées avant packaging

- compilation Python ;
- syntaxe JavaScript validée avec Node ;
- création de compte ;
- achat de CDG ;
- lecture du nouvel état v0.6 ;
- calcul niveau joueur ;
- calcul satisfaction hub ;
- quêtes quotidiennes ;
- catalogue bancaire France ;
- prêt BNP Paribas + remboursement ;
- offres hôtelières géolocalisées ;
- chargement de la page jeu avec `premium.css`.

## Important

Cette version reste un prototype personnel Web. Les noms de marques réelles utilisés comme données de jeu ne signifient aucun partenariat ou affiliation officielle. Une diffusion commerciale nécessitera une revue juridique/licences des marques, livrées et contenus tiers.

## v0.7.1 — FR24 READY

See `FR24_SETUP.md` for secure Flightradar24 configuration and diagnostics. See `REALISM_3D_ROADMAP.md` for the Unreal Engine / Pixel Streaming path to photorealistic cockpits, volumetric clouds and fully 3D airports.
