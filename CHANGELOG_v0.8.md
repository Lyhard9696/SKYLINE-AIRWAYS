# SKYLINE AIRWAYS v0.8 — REALISM RESTORE

Cette version corrige une vraie régression introduite dans la v0.7.1 et remet le projet sur la direction visuelle et fonctionnelle validée.

## Correction critique

La v0.7.1 avait perdu une partie importante de `static/game.js`. Plusieurs fonctions appelées par l'interface n'existaient donc plus (`renderOwnedHubs`, `loadMarket`, météo, rendu flotte/routes, synchronisation globe, etc.). Résultat : erreurs JavaScript, boutons sans effet, catalogue incomplet, trafic/météo cassés.

La v0.8 repart du moteur complet de la v0.7 et conserve les améliorations serveur FR24 de la v0.7.1.

## Interface & navigation

- fonctions principales restaurées et navigation rebranchée ;
- toutes les vues statiques du menu pointent vers une vue réellement présente ;
- écrans premium ajoutés : Niveau & quêtes, Alliances, Boutique, Secours & opérations spéciales ;
- diagnostic FR24 + météo directement dans Centre OPS ;
- références visuelles premium intégrées pour hubs, finance, globe, cockpit, siège, boutique, alliances et opérations spécialisées ;
- construction des bases spéciales via un sélecteur de hub dans l'interface, sans `prompt()` navigateur.

## Flotte & catalogue photo

- catalogue général à nouveau visible par défaut ;
- filtres rapides : long-courrier, court/moyen-courrier, hélicoptères, bombardiers d'eau, transport stratégique, défense ;
- fiches photo pour A350, H145, CL-415, A400M, Rafale et cartes premium génériques ;
- appareils spécialisés visibles avant leur déblocage mais achat verrouillé par niveau ;
- ajout/normalisation des rôles H145, AW139, CL-415, NH90, A400M, C-130J, Rafale et MQ-9 (gestion stratégique uniquement).

## Secours, sécurité civile & activités stratégiques

- bases spécialisées persistantes en base de données ;
- paliers : SAR 61, sécurité civile 66, service public 71, gouvernement 76, défense stratégique 81 ;
- contrats automatiques : feux d'été Portugal, secours H24, SAR maritime, service public, pont aérien et disponibilité territoriale ;
- contrôle du niveau, de la base et du nombre d'appareils compatibles avant acceptation ;
- aucun pilotage/combat tactique : le module reste un système de gestion.

## Flightradar24

- hub et globe utilisent le backend FR24 lorsque la clé est disponible ;
- alias acceptés : `FR24_API_TOKEN`, `FLIGHTRADAR24_API_TOKEN`, `FLIGHTRADAR_TOKEN`, `FR24_TOKEN` ;
- essai automatique endpoint `full`, puis `light` si le plan API ne donne pas accès au full ;
- détection sol autour du hub basée sur distance, altitude terrain/aéroport et vitesse ;
- endpoint de test sécurisé `/api/integrations/fr24/test?ident=LFPG` ;
- aucun token n'est envoyé au navigateur ou inclus dans GitHub.

## Météo

- logique météo frontend restaurée ;
- radar RainViewer récupéré via `/api/weather/radar` côté serveur afin de réduire les problèmes CORS ;
- conditions cockpit via Open-Meteo conservées ;
- les erreurs de fournisseur sont visibles dans Centre OPS au lieu de casser silencieusement la vue.

## Cache / PWA

Le cache service worker passe à `skyline-v080-realism-restore-v1` afin d'éviter que l'iPhone conserve le JavaScript cassé de la v0.7.1.

## Hotfix v0.8.1

- badge visible de source trafic sur le hub (FR24/OpenSky + compte sol/proche) ;
- badge radar météo visible et bouton météo capable de retenter le chargement ;
- cache PWA v0.8.1 pour forcer Safari/iPhone à abandonner le JavaScript v0.7.1 cassé.
