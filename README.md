# SKYLINE AIRWAYS — v0.4 REALISM / IMMERSIVE WORLD

Version Web full-stack jouable, pensée pour Render + iPhone/PC.

## Ce qui change par rapport à v0.3

### Carrière et comptes
- Création de compte / connexion persistante.
- Base PostgreSQL sur Render.
- Nouveau joueur : 180 M€ et **aucun hub imposé**.
- Choix du premier hub parmi **85 937 aéroports, héliports et bases** du catalogue embarqué.
- Possibilité d’acheter ensuite d’autres hubs partout dans le monde.
- Chaque hub garde ses améliorations indépendamment.

### Hub satellite réellement navigable
- La page Hub occupe tout l’écran.
- Fond satellite géographique centré sur l’aéroport réellement acheté.
- Zoom, déplacement, inclinaison et rotation de caméra avec MapLibre.
- Pistes connues issues du catalogue aéroportuaire.
- Quand OpenStreetMap/Overpass est disponible : récupération des **taxiways, aprons et positions de porte** réelles autour du hub.
- Repli automatique sur les pistes OurAirports si Overpass est indisponible.
- Les avions et véhicules d’ambiance se déplacent sur le réseau de surface lorsque celui-ci est disponible.
- Trafic OpenSky autour du hub lorsque le service public répond, complété par du trafic IA/fictif.

### Développement du hub
Le hub possède **53 systèmes d’infrastructure**, représentant **597 niveaux cumulés** :
- portes au contact ;
- parkings avions éloignés ;
- postes gros-porteurs ;
- zone régionale ;
- aires de trafic ;
- taxiways ;
- dégivrage ;
- fuel farm ;
- pushback ;
- véhicules de piste ;
- terminal ;
- check-in ;
- bornes / self bag drop ;
- embarquement ;
- arrivées ;
- bagages ;
- toilettes ;
- Wi-Fi ;
- signalétique ;
- sûreté ;
- police aux frontières ;
- douanes ;
- pompiers ;
- centre médical ;
- centre de crise ;
- duty free ;
- galerie commerciale ;
- restauration ;
- hôtel ;
- parkings voitures ;
- transports terrestres ;
- lounges Business / First ;
- suites ;
- Fast Track ;
- maintenance ;
- pièces ;
- catering ;
- service à bord ;
- nettoyage ;
- centre équipages ;
- formation ;
- centre OPS ;
- cargo ;
- chaîne froide ;
- express ;
- fret lourd ;
- énergie ;
- eau ;
- systèmes IT ;
- et leurs niveaux successifs.

Chaque marqueur est cliquable directement sur la vue aérienne : coût, niveau, prérequis, construction/amélioration.

### Catalogue aéronefs
Le catalogue embarqué contient :
- **591 types ICAO** ;
- **197 variantes / motorisations** ;
- Airbus, Boeing, ATR, Embraer, Bombardier et de nombreux autres constructeurs ;
- jets, turbopropulseurs, hélicoptères, appareils historiques et autres aéronefs présents dans le catalogue.

Chaque appareil acheté est individuel :
- immatriculation ;
- base ;
- état ;
- achat ou leasing ;
- variante ;
- livrée ;
- rotation affectée ;
- position simulée.

### Livrées et identité
- couleurs principales / secondaires / accent ;
- plusieurs styles de livrée ;
- texte de logo ;
- import d’un logo personnel ;
- livrée personnalisable appareil par appareil.

Les vraies marques/livrées commerciales ne sont pas livrées comme assets officiels : leur utilisation commerciale nécessite les droits/licences correspondants. L’éditeur est conçu pour les ajouter plus tard sans changer le moteur.

### Globe 3D
- Globe satellite manipulable à 360° ;
- 2 200+ grands/moyens aéroports visibles sur le globe ;
- hubs possédés ;
- routes de la compagnie ;
- segments partenaires ;
- tes avions en temps simulé ;
- trafic fictif mondial animé pour garder le monde vivant ;
- rotation automatique facultative du globe.

### Météo
- Radar mondial RainViewer superposé au globe lorsque disponible ;
- météo locale Open-Meteo pour la position des avions ;
- nuages et effets d’orage dans la vue cockpit selon les conditions récupérées.

### Vue cockpit dynamique
La vue cockpit est une **vue d’observation**, pas un cockpit pilotable :
- paysage satellite qui défile selon la position réelle simulée du vol ;
- cap de la caméra aligné sur la route ;
- montée / croisière / descente ;
- altitude ;
- vitesse ;
- carburant ;
- météo ;
- couches nuageuses animées ;
- éclairs lorsque le moteur météo détecte des conditions orageuses.

### Routes et opérations
- même avion physique sur toute la rotation aller/retour ;
- turnaround ;
- pushback ;
- roulage départ ;
- vol ;
- roulage arrivée ;
- retour ;
- simulation accélérée ;
- autonomie ;
- compatibilité piste ;
- restrictions OPS ;
- exemple de liaison partenaire via Istanbul ;
- scénario géopolitique remplaçable par un futur fournisseur NOTAM/licencié.

## Installation sur Render

Le dépôt doit avoir ces éléments à la racine :

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
README.md
```

### Si ton Blueprint SKYLINE existe déjà
1. Remplace les fichiers de ton dépôt GitHub par ceux de cette version.
2. Fais un commit, par exemple :
   `SKYLINE v0.4 Realism Immersive World`
3. Render détecte automatiquement le commit.
4. Le Blueprint réutilise la base `skyline-db` existante si elle est déjà présente.
5. Attends `Deploy live`.
6. Ouvre l’URL habituelle `https://skyline-airways.onrender.com`.

### Nouveau Blueprint
`render.yaml` configure automatiquement :
- service Web Python ;
- PostgreSQL `skyline-db` ;
- `DATABASE_URL` ;
- secret de session ;
- cookie HTTPS ;
- health check `/health`.

## Test local

Python 3.11+ recommandé.

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 10000
```

Puis :

```text
http://localhost:10000
```

Sans `DATABASE_URL`, le jeu crée automatiquement une base SQLite locale `skyline.db`.

## Sources externes utilisées au runtime

Le jeu fonctionne même si certaines sources publiques sont temporairement indisponibles, mais les fonctions les plus riches utilisent :
- Esri World Imagery : fond satellite ;
- OpenStreetMap / Overpass : réseau airside quand disponible ;
- OurAirports : aéroports et pistes embarqués dans le catalogue ;
- OpenSky : trafic réel autour du hub quand disponible ;
- RainViewer : radar météo ;
- Open-Meteo : météo locale cockpit.

## Limite technique importante

Cette v0.4 est une version Web très interactive. Elle apporte un vrai satellite navigable, un globe 3D, des mouvements et une vue cockpit dynamique.

Pour atteindre ensuite un rendu équivalent à un simulateur AAA avec :
- modèles d’aéroports en 3D photoréalistes ;
- bâtiments réellement volumétriques ;
- cockpits Airbus/Boeing modélisés ;
- avions 3D fidèles ;
- nuages volumétriques ;
- éclairage physique ;
- véhicules 3D ;
- taxi exact sur toutes les voies avec animations complexes ;

le client final devra passer sur Unreal Engine 5 tout en conservant ce backend de comptes, flotte, économie, hubs et OPS.
