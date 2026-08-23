# SKYLINE AIRWAYS — Flightradar24 API (v0.8)

## Secret

Le token doit rester **uniquement côté serveur**. Il ne doit jamais être placé dans `game.js`, HTML, CSS, une capture, un commit GitHub ou une valeur en clair dans `render.yaml`.

Un token déjà partagé dans une conversation doit être révoqué puis remplacé.

## Render — service existant

1. Dashboard Render → service `skyline-airways`.
2. `Environment` → `Add Environment Variable`.
3. Key : `FR24_API_TOKEN`.
4. Value : nouveau token régénéré.
5. `Save Changes`.
6. Redéployer le dernier commit.

`render.yaml` utilise `sync: false`, donc aucune valeur secrète n'est stockée dans le dépôt.

Le backend accepte aussi les alias `FLIGHTRADAR24_API_TOKEN`, `FLIGHTRADAR_TOKEN` et `FR24_TOKEN`, mais `FR24_API_TOKEN` reste le nom recommandé.

## Diagnostic intégré

Dans le jeu : `Plus → Centre OPS & diagnostics → Tester FR24 + météo`.

Le serveur essaie d'abord la réponse `full`; si le plan ou l'autorisation ne la permet pas, il tente la réponse `light`. Le frontend affiche le mode réellement utilisé.

Endpoints utiles après connexion :

- `/api/integrations/fr24/status`
- `/api/integrations/fr24/test?ident=LFPG`
- `/api/live-traffic?ident=LFPG`
- `/api/live-traffic/box?north=50&south=48&west=1&east=4`

Aucun de ces endpoints ne renvoie le token.

## Trafic au hub

La détection du trafic au sol n'utilise plus la règle incorrecte « altitude < 200 ft ». Elle combine :
- distance au point de référence de l'aéroport ;
- élévation de l'aéroport ;
- altitude de l'appareil ;
- vitesse sol / état `on_ground` quand disponible.

Cela permet notamment à CDG et aux aéroports situés plus haut que le niveau de la mer d'être traités correctement.

## Si aucun avion n'apparaît

Le Centre OPS donne le premier diagnostic. Vérifie dans cet ordre :
1. `configured: true` ;
2. test FR24 `OK` ;
3. nombre de positions > 0 ;
4. `ground_count` / `nearby_count` ;
5. que le bouton `✈ Trafic` du hub est actif.

En l'absence de trafic réel, la v0.8 n'invente pas de faux appareils pour remplir le tarmac.
