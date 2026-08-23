# SKYLINE AIRWAYS v0.6 — Aviation Premium

# SKYLINE AIRWAYS — v0.5 REALISM OPERATIONS

Version Web full-stack jouable, pensée pour Render, iPhone/iPad et PC. Cette version garde la carrière v0.4 et ajoute une couche de gestion beaucoup plus profonde : personnel, pricing, finance, banque, marketing, partenariats, hôtels, service à bord, opérations au sol, hub réellement achetable et trafic réel optionnel.

## Mise à jour depuis v0.4

La v0.5 est conçue pour être déposée directement par-dessus la v0.4 dans le même dépôt GitHub. Les nouvelles tables PostgreSQL sont créées automatiquement au démarrage. Les comptes, hubs, avions et routes existants sont conservés.

## Temps de simulation

`SIM_SPEED = 3.0`.

Le temps simulé avance trois fois plus vite que le temps réel : un vol de 8 heures réelles de block-time dure environ 2 h 40 dans le jeu, soit ~33 % de sa durée réelle. Les phases sol sont elles aussi simulées : nettoyage, catering, ravitaillement, embarquement, pushback, roulage, vol, roulage arrivée et débarquement.

## Personnel

Nouvel espace **Gestion → Personnel** :
- commandants / copilotes ;
- PNC ;
- mécaniciens ;
- agents de piste ;
- RH ;
- directeur marketing ;
- directeur des opérations ;
- directeur financier.

Les pilotes ont des qualifications par famille d'appareil. Si l'effectif n'est pas suffisant, OPS peut utiliser du personnel contractuel, mais cela augmente fortement le coût du vol.

## Prix des billets et demande

Chaque ligne possède maintenant :
- prix Economy ;
- Premium ;
- Business ;
- First ;
- frais bagages ;
- taux de surbooking.

Le remplissage estimé varie avec le prix, la réputation, le niveau de service, les campagnes marketing et les partenariats. Le détail de rentabilité est recalculé avant validation.

## Finance / banque

Nouvel espace **Gestion → Finance / Banque** :
- trésorerie ;
- masse salariale ;
- dette ;
- historique des transactions ;
- résultats par vol ;
- emprunts bancaires ;
- taux d'intérêt ;
- remboursement partiel.

Chaque rotation terminée produit une fiche de vol avec passagers, recettes, coûts et bénéfice/perte.

## Marketing, partenariats et hôtels

Le joueur peut :
- recruter un directeur marketing ;
- lancer des campagnes publicitaires ;
- signer des partenariats ;
- développer des accords hôteliers ;
- construire ses propres hôtels dans ses hubs ;
- agrandir progressivement ces hôtels.

## Service à bord et appareil

Chaque avion peut recevoir des améliorations indépendantes :
- Wi-Fi ;
- repas ;
- divertissement ;
- confort cabine ;
- formation du service cabine ;
- standard de nettoyage.

Ces niveaux ont un coût mais influencent l'attractivité et la rentabilité des vols.

## Studio de livrée

Le rendu avion a été remplacé par un aperçu SVG spécifique au type d'aéronef au lieu d'un simple pictogramme. Sont personnalisables :
- fuselage ;
- couleur secondaire ;
- accent ;
- dérive ;
- moteurs ;
- ventre ;
- nez ;
- motif ;
- taille et position du logo.

Ce studio reste un éditeur 2D Web. Des modèles 3D photoréalistes et les livrées officielles des compagnies nécessitent des assets 3D et les droits/licences correspondants.

## Cockpit dynamique

La vue cockpit est une caméra d'observation, pas un simulateur pilotable :
- cadre cockpit fixe ;
- paysage satellite qui avance avec l'avion ;
- cap suivi automatiquement ;
- altitude / vitesse / carburant / phase de vol ;
- ciel jour, crépuscule ou nuit en fonction de la position ;
- étoiles et éclairage nocturne ;
- couverture nuageuse issue de la météo locale ;
- pluie et effets d'orage lorsqu'ils sont cohérents avec la météo.

Le vrai cockpit 3D de chaque A320/A350/777/etc., les nuages volumétriques et le relief photoréaliste sont une étape Unreal Engine ultérieure. Cette version stabilise la logique Web d'observation dynamique.

## Hub interactif

La vue aérienne garde le fond satellite et les données OpenStreetMap lorsqu'elles sont disponibles. La v0.5 ajoute :
- portes réelles cliquables ;
- positions de parking cliquables ;
- pistes visibles ;
- infrastructure non acquise affichée comme verrouillée / grisée ;
- achat directement depuis la vue aérienne ;
- services de hub avec cadenas/prérequis ;
- niveaux multiples ;
- véhicules de service associés à la phase réelle de l'avion ;
- déplacements sur le réseau de taxiway lorsqu'un réseau OSM exploitable existe.

Les phases de service au sol sont liées au vol : nettoyage, catering, fuel, passagers et pushback ne sont plus seulement des éléments décoratifs.

## Trafic aérien réel

La v0.5 n'imite pas ou ne scrape pas le site Flightradar24.

- Si la variable Render `FR24_API_TOKEN` est configurée avec un abonnement API Flightradar24 autorisé, le serveur utilise l'API officielle Live Flight Positions.
- Sans token FR24, le jeu essaie OpenSky dans la zone visible.
- Le globe n'ajoute plus les anciens faux avions décoratifs lorsqu'un trafic réel peut être interrogé.

Le fond satellite est indépendant du fournisseur de trafic aérien.

## Météo et globe

- globe MapLibre 3D ;
- rotation 360° ;
- représentation approximative jour/nuit sur le globe ;
- radar RainViewer lorsque disponible ;
- météo locale Open-Meteo dans le cockpit ;
- routes et avions SKYLINE en temps simulé.

## Données / réalisme

Le catalogue embarqué conserve les données v0.4 :
- 85k+ aéroports/héliports/bases ;
- 591 types d'aéronefs ;
- variantes et motorisations selon les données disponibles.

Les vraies livrées, marques et modèles 3D officiels ne sont pas distribués avec ce prototype sans licence.

## Déploiement Render

Le dépôt doit garder à sa racine :

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

Le Blueprint Render existant peut être conservé. Le `render.yaml` utilise la même base `skyline-db`.

### Option Flightradar24 officielle

Dans Render → service `skyline-airways` → Environment, ajouter si tu possèdes un abonnement API autorisé :

```text
FR24_API_TOKEN=ton_token_api
```

Cette variable est facultative. Sans elle, le reste du jeu fonctionne et le trafic tente OpenSky.

## Vérifications effectuées avant packaging

- compilation Python ;
- validation syntaxique JavaScript avec Node ;
- création de compte ;
- achat d'un hub ;
- leasing d'un avion ;
- personnalisation de livrée ;
- amélioration Wi-Fi ;
- recrutement ;
- création de route ;
- tarification ;
- campagne marketing ;
- emprunt ;
- partenariat ;
- construction d'hôtel ;
- lecture finance / état / hub.

