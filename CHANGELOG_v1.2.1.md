# SKYLINE AIRWAYS v1.2.1 — Premium Hubs

## Hubs mondiaux
- Refonte de la page **Hubs mondiaux** selon la référence visuelle fournie.
- Cartes premium des hubs possédés avec photo satellite, niveau, satisfaction, badge principal et sélection lumineuse.
- Nouvelle zone **Hubs disponibles** avec HND, MEX, DXB, JFK et autres grands hubs mondiaux selon disponibilité.
- Les hubs non accessibles sont réellement grisés/verrouillés : le backend vérifie le niveau joueur et la trésorerie avant acquisition.
- Le panneau du hub sélectionné affiche niveau, passagers/jour, prestige, satisfaction, bonus économiques actifs et coûts fixes estimés.

## Gestion du hub
- Le bouton **Gérer le hub** ouvre désormais un tableau premium directement dans la page Réseau de hubs.
- Onglets : Services passagers, Infrastructures, Partenaires et Analytiques.
- Cartes dédiées pour salons, Duty Free, Police aux frontières, sécurité, parkings, toilettes, bagages, hôtels, restaurants, boutiques luxe, transports sol et intermodalité.
- Utilisation des assets déjà présents : Air France, Relay, Groupe ADP, Novotel, ibis, Sheraton, Ladurée, Rolex, Uber, Bolt et SNCF.
- Les améliorations sont verrouillées côté serveur tant que le niveau du hub, les prérequis ou la trésorerie sont insuffisants.
- Une amélioration déjà acquise reste active visuellement même si le prochain niveau est temporairement inaccessible.

## Économie
- Les améliorations commerciales/passagers du hub produisent maintenant de vrais bonus économiques sur les vols au départ du hub :
  - revenus annexes ;
  - bonus de demande.
- Ces bonus passent par le moteur économique existant et ne sont pas de simples valeurs décoratives.

## Interface
- Fermeture des fiches/modales renforcée : bouton ×, clic sur le fond et touche Échap.
- Cache PWA incrémenté pour forcer le chargement de la nouvelle interface.

## Compatibilité
- Aucune nouvelle table SQL requise.
- Base PostgreSQL/SQLite existante compatible.
