# SKYLINE AIRWAYS v1.3 — FR24 mondial

## Variables Render

```text
FR24_API_TOKEN=<token production>
FR24_API_BASE_URL=https://fr24api.flightradar24.com/api
FR24_WORLD_CACHE_SECONDS=180
FR24_WORLD_TILE_LIMIT=20000
FR24_WORLD_WORKERS=3
FR24_WORLD_DETAIL=light
FR24_COUNT_CACHE_SECONDS=30
```

Le token ne doit jamais être placé dans le JavaScript, dans un `VITE_*`, dans GitHub ou dans une capture d'écran.

## Pourquoi l'ancien écran disait « 13 positions / 6 sol » ?

L'ancien bouton de diagnostic exécutait volontairement une requête locale autour d'un seul aéroport avec un petit `limit`. Ce nombre n'était pas le trafic mondial.

v1.3 sépare maintenant :

- **FR24 suivis** : résultat du endpoint mondial `/live/flight-positions/count` ;
- **affichés** : positions que le compte API a réellement autorisé SKYLINE à télécharger ;
- **en vol / sol** : classification de ces positions chargées ;
- **couverture** : affichés / suivis lorsque le compteur mondial est disponible.

## Limites d'abonnement

Le code demande jusqu'à 20 000 positions par zone et balaye le monde par tuiles, mais un abonnement FR24 peut imposer une limite de réponse et les appels consomment des crédits. Le jeu n'invente donc jamais les positions manquantes.

Pour une vraie couverture exhaustive, il faut que l'abonnement FR24 autorise suffisamment de résultats et de crédits. Le Globe indique explicitement lorsqu'une limitation de plan est détectée.

## Coût / stabilité Render

Le snapshot mondial est partagé entre les joueurs et mis en cache. L'affichage se déplace visuellement entre les snapshots par interpolation locale, ce qui donne un mouvement fluide sans appeler FR24 toutes les 3 secondes pour chaque joueur.

À fort zoom, SKYLINE interroge uniquement la bounding box visible afin d'obtenir une vue plus détaillée.

## Endpoints de diagnostic

Après connexion :

```text
/api/integrations/fr24/status
/api/integrations/fr24/world-summary
/api/live-traffic/world
```

Le vieux endpoint `/api/integrations/fr24/test?ident=CDG` existe encore uniquement comme test **local** et renvoie maintenant `scope: diagnostic_local`.
