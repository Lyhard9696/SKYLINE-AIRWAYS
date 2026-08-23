# SKYLINE AIRWAYS v1.2 — Flightradar24

## Render
Dans `Environment` :

```text
FR24_API_TOKEN=<token API production>
FR24_API_BASE_URL=https://fr24api.flightradar24.com/api
FR24_WORLD_CACHE_SECONDS=120
FR24_WORLD_TILE_LIMIT=20000
FR24_WORLD_WORKERS=3
```

Ne pas écrire `Bearer` dans la valeur du token. SKYLINE construit lui-même l'en-tête :

```text
Authorization: Bearer <token>
Accept-Version: v1
```

Le token n'est jamais envoyé au frontend.

## Tests
Après connexion :

```text
/api/integrations/fr24/status
/api/integrations/fr24/test?ident=LFPG
/api/live-traffic/world
```

`/api/integrations/fr24/test` est volontairement un **diagnostic local** autour du hub. Un résultat comme `19 positions` ne représente donc pas le trafic mondial.

`/api/live-traffic/world` est l'endpoint utilisé pour la vue globale v1.2. Il découpe la planète en zones et déduplique les résultats.

## Coût API
Le mode mondial peut consommer beaucoup de crédits FR24. Le cache est partagé côté serveur. Pour économiser des crédits, augmenter par exemple :

```text
FR24_WORLD_CACHE_SECONDS=300
```

Le frontend ne déclenche pas un balayage mondial à chaque mouvement de carte : à fort zoom il interroge uniquement la bounding box visible.

## Sandbox
Le sandbox FR24 renvoie des données statiques prédéfinies et ne permet pas de valider un trafic mondial réel. Utiliser un token production sur Render pour la version live.
