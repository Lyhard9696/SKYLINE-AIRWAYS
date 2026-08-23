# SKYLINE AIRWAYS v1.3.2 — Memory Safe Globe & Hub Works

## Globe / Flightradar24
- Suppression du chargement planétaire de positions FR24 au démarrage : la vue monde n'importe plus de snapshot géant en RAM.
- À faible zoom, le Globe affiche uniquement le nombre mondial d'aéronefs suivis par FR24 et les couches stratégiques.
- À partir du zoom régional, les positions sont chargées uniquement dans la bounding box visible (1000 à 2200 positions max par rafraîchissement).
- Cache trafic ramené à 8 entrées pour protéger les instances Render 512 Mo.
- L'ancien helper de snapshot mondial est neutralisé : même un appel accidentel ne déclenche plus les 12 tuiles mondiales.
- Les avions au sol restent dans les réponses et sont cliquables.
- Au clic, Skyline appelle `flight-summary/full` uniquement pour le `fr24_id` sélectionné, puis cherche une photo exacte par immatriculation/hex via Planespotters. Aucun enrichissement photo n'est lancé pour les milliers de marqueurs.
- Le diagnostic distingue désormais le compteur mondial FR24 et les positions chargées dans la zone visible.

## Hubs
- Nouvelle progression visuelle et fonctionnelle des améliorations :
  - gris + cadenas = verrouillé ;
  - jaune = déblocable ;
  - orange = travaux en cours ;
  - vert = opérationnel.
- Les achats d'améliorations ne sont plus instantanés : création d'un chantier persistant `hub_constructions_v132`, paiement côté serveur, timer puis activation automatique.
- Ajout de la Gare ferroviaire / RER, du Métro / transport urbain et d'Uber / Bolt & VTC.
- Les accès terrestres participent réellement à la satisfaction et à la demande du hub.
- Libellés spécifiques CDG : Terminal 2E, Gare TGV / RER, CDGVAL / Métro, zone VTC, Police aux frontières, Duty Free Terminal 2E.
- Les marqueurs de la carte du hub utilisent les mêmes couleurs d'état.

## Accueil
- Retrait du visuel de services de hub derrière « Bonjour ». L'accueil utilise désormais un fond aviation sobre et premium ; les visuels/services restent dans la gestion du hub.

## Secours / Sécurité civile / opérations stratégiques
- Suppression de l'image statique comme écran principal.
- Sélection d'un pays, carte interactive nationale et sites aéroportuaires cliquables.
- Achat des bases directement sur la carte ; les bases spécialisées sont indépendantes des hubs commerciaux.
- Points verts = base active, jaunes = site constructible, gris = branche verrouillée.
- Le coût combine le coût de la branche et un coût d'implantation local.
- Contrats, flotte compatible et missions automatiques restent connectés au moteur existant.

## Compatibilité / déploiement
- FastAPI 1.3.2.
- Cache PWA `skyline-v132-memory-safe-hubs-v1`.
- Paramètres Render FR24 sûrs : limite 2200, worker 1.
