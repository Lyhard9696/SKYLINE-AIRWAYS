# SKYLINE AIRWAYS v1.3 — Premium Operations

Cette version repart du projet v1.1/v1.2 existant et corrige les points signalés après le premier déploiement v1.2.

## Globe OPS / Flightradar24

- Le diagnostic principal n'utilise plus le petit test local autour de CDG : il interroge désormais le **compteur mondial FR24** puis le snapshot mondial réellement chargé.
- Le Globe utilise 12 zones mondiales, déduplique les `fr24_id` et conserve les appareils en vol **et** au sol.
- Les compteurs séparent désormais : `suivis par FR24`, `chargés par le plan API`, `en vol`, `sol`, `couverture`.
- Une limite imposée par l'abonnement FR24 est affichée comme telle au lieu de laisser croire que 13 ou 20 positions correspondent au monde entier.
- À faible zoom : snapshot mondial partagé et mis en cache. À fort zoom : bounding box de la vue courante.
- Les positions sont interpolées visuellement entre deux snapshots pour éviter un globe figé, sans multiplier les appels facturés.
- Rendu des milliers de positions par source/layers GeoJSON MapLibre plutôt que par milliers de marqueurs DOM.
- `painted_as` reste prioritaire sur `operating_as`; aucune compagnie n'est déduite depuis le type d'avion.

## Météo aviation

- Open-Meteo reste la source météo générale principale.
- Retry automatique puis repli sur MET Norway si Open-Meteo est temporairement indisponible.
- METAR et TAF passent par AviationWeather.gov côté serveur, séparément de la météo générale.
- Le diagnostic affiche la source réellement utilisée au lieu de rester bloqué sur `Open-Meteo ÉCHEC`.

## NOTAM réels

- Intégration serveur de **Aviation Edge NOTAM API**.
- Endpoint `GET /api/aviation/notams?icao=LFPG`.
- Les NOTAM sont affichables depuis le Centre OPS et depuis la fiche d'un aéroport sur le Globe.
- Aucun faux NOTAM n'est généré.
- Secret requis sur Render : `AVIATION_EDGE_API_KEY`.

## Catalogue & fiches aéronefs

- Chargement paresseux de photos de **type exact** via Wikimedia Commons lorsque le catalogue local n'a pas de photo.
- Cache serveur des recherches de photos.
- Aucun visuel de compagnie n'est substitué à un type seulement parce que l'appareil est un A350/B737/etc.
- La fiche avion peut maintenant être fermée par le bouton `×`, clic sur l'arrière-plan ou touche Échap.
- Les images ne sont chargées que lorsqu'une carte approche du viewport.

## Hubs

- L'écran Hubs mondiaux conserve le rendu premium de référence : hubs possédés à gauche, hub sélectionné détaillé à droite, hubs futurs verrouillés.
- Achat d'un hub contrôlé côté serveur par **niveau joueur + trésorerie**.
- Les améliorations sont contrôlées côté serveur par **niveau du hub + prérequis + trésorerie**.
- Une amélioration non accessible reste grisée avec cadenas et raison du verrouillage.
- Les services passagers/partenaires (salons, duty free, Police aux frontières, sécurité, parkings, toilettes, bagages, hôtels, restaurants, luxe, Uber/Bolt, rail/SNCF...) disposent de cartes premium et produisent de vrais effets économiques/satisfaction.

## Alliances

- Refonte visuelle premium de l'écran Alliances.
- Niveaux d'alliance 1 à 10.
- Objectifs collectifs, réseau mondial, contributions, économies, membres, rôles fondateur/officier et chat.
- Nouvelles améliorations communes persistantes, achetées avec la trésorerie de l'alliance :
  - contrats carburant groupés ;
  - académie équipages ;
  - pool maintenance ;
  - centrale achats flotte ;
  - bureau réseau & codeshare ;
  - réseau de salons.
- Les bonus sont ajoutés au moteur économique central et bénéficient à **tous les membres** de l'alliance.
- Le réseau de salons agit aussi sur la réputation effective utilisée par le moteur de demande.

## Niveau, quêtes & Prochaines ères

- Nouvelle présentation haut de gamme du niveau joueur et des quêtes.
- `Prochaines ères` devient une vraie roadmap de cinq ères :
  1. Optimisation moderne
  2. Transition énergétique
  3. Aviation ultra-efficiente
  4. Nouvelles propulsions régionales
  5. Réseau intelligent
- Déblocage par niveau joueur + progression R&D.
- Les bonus d'ère sont réellement intégrés aux coûts/demande.

## Secours & opérations spéciales

- Refonte complète de l'écran selon la direction artistique fournie.
- Branches : secours, incendie/Sécurité civile, gendarmerie, gouvernemental, défense.
- Bases spécialisées, flotte dédiée, disponibilité et contrats.
- Les branches verrouillées restent visibles mais non utilisables jusqu'au niveau requis.

## PWA / cache

- Cache PWA incrémenté en v1.3.
- JS/CSS/HTML sont servis en `no-store` afin d'éviter qu'un ancien `game.js` reste actif après un déploiement Render.

## Tests de packaging

Voir `tests/smoke_v13.py`. Le packaging valide également :
- compilation Python ;
- syntaxe JavaScript via Node ;
- démarrage FastAPI avec SQLite temporaire ;
- inscription + achat du premier hub ;
- chargement `/game` avec assets v1.3 ;
- endpoints R&D, alliances, hubs, NOTAM/FR24 status ;
- création d'alliance, contribution et achat d'une amélioration commune.
