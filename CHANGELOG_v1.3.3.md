# SKYLINE AIRWAYS — v1.3.3

## Premium Hub Zones + FR24 viewport + ground-aircraft details

Cette version consolide les retours après v1.3.1/v1.3.2 en gardant l'esthétique premium sombre des maquettes SKYLINE tout en réduisant la charge mémoire sur Render 512 Mo.

### Globe / Flightradar24

- Suppression du chargement de positions FR24 à l'échelle mondiale au démarrage.
- À très faible zoom, le globe reste immédiatement utilisable et n'affiche qu'un état agrégé/compteur mondial.
- Les positions détaillées sont chargées uniquement pour la zone visible, avec une limite adaptée au zoom et un seul appel en vol à la fois.
- Cache backend FR24 fortement borné afin d'éviter l'accumulation de snapshots en mémoire.
- Les avions au sol restent dans le flux de positions et sont cliquables.
- Un clic sur un avion déclenche une requête de détail ciblée : FR24 flight-summary si disponible, sinon petite recherche live autour de la position pour retrouver un mouvement au sol.
- La photo de l'appareil n'est recherchée qu'au clic, par immatriculation puis hex, afin de ne pas charger des milliers d'images.
- La fiche distingue compagnie peinte (`painted_as`) et opérateur (`operating_as`) et ne déduit jamais une compagnie à partir du seul type d'avion.

### Hubs : carte hiérarchique

La carte du hub n'affiche plus toutes les petites améliorations en même temps. Elle affiche d'abord de grandes zones :

- Terminal & passagers
- Mobilité & accès
- Airside / portes
- Technique & OPS
- Sûreté / résilience
- Cargo

États visuels :

- gris + cadenas : verrouillé / prérequis manquant ;
- jaune : déblocable immédiatement ;
- orange : travaux en cours avec progression ;
- vert : opérationnel ;
- bleu : sélection courante.

Cliquer une zone ouvre ses sous-améliorations (portiques, scanners, Duty Free, lounges, services premium, transports, sécurité, etc.). Les coûts, prérequis et chantiers sont validés côté serveur et persistent en base.

### Mobilité contextuelle

Les services proposés dépendent réellement de l'aéroport. Un grand hub parisien peut proposer TGV/RER et connexion urbaine ; un aéroport régional sans métro ne reçoit pas artificiellement une option métro. Les offres pertinentes peuvent inclure train, métro/RER, bus, navettes, taxis, VTC/Uber/Bolt, location de voiture et parkings. Les services impossibles localement sont également refusés par l'API d'achat.

### Marques, compagnies et aéronefs

- Logos constructeurs Airbus, Boeing et Embraer intégrés aux cartes aéronefs lorsque l'identité est connue.
- Logos compagnies/partenaires uniquement lorsque la correspondance est fiable.
- Les partenaires de hub utilisent les SVG fournis (SNCF, Uber/Bolt, Groupe ADP, hôtels, boutiques, etc.) lorsqu'ils sont pertinents pour le lieu et le service.
- Les photos d'aéronefs locales vérifiées sont prioritaires ; le catalogue peut compléter par une photo du type exact sans substituer un autre modèle.

### Accueil

Le bandeau « Bonjour » redevient un tableau de bord compagnie. Les visuels et marques de Duty Free, lounges, police aux frontières, transports et autres services sont réservés à la gestion du hub.

### Secours / Sécurité civile / opérations stratégiques

- Sélection d'un pays avant implantation.
- Carte nationale MapLibre interactive au lieu d'une image fixe de maquette.
- Achat et gestion des bases spécialisées directement sur la carte.
- Bases actives, disponibles et verrouillées différenciées visuellement.
- Flottes et contrats spécialisés restent des fonctions de gestion stratégique.

### OPS / météo / NOTAM

La logique v1.3.1 est conservée : NOTAM pertinents seulement pour les hubs, départs/arrivées et routes du joueur ; météo aviation via METAR/TAF/SIGMET ; pas de faux NOTAM météo.

### Tests de régression

- compilation Python ;
- syntaxe JavaScript ;
- smoke FastAPI ;
- régression OPS NOTAM/SIGMET ;
- contexte mobilité CDG/Limoges ;
- refus serveur d'une amélioration géographiquement impossible ;
- cycle chantier hub ;
- fallback ciblé de détail FR24 pour avion au sol ;
- audit des assets statiques.
