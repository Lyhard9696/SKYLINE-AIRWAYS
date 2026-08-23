# SKYLINE AIRWAYS v1.3 — NOTAM temps réel

SKYLINE peut maintenant interroger un fournisseur NOTAM réel côté serveur.

## Fournisseur intégré

Aviation Edge NOTAM API — données NOTAM d'aéroports mondiaux par ICAO/IATA.

## Render

Ajouter :

```text
AVIATION_EDGE_API_KEY=<ta clé Aviation Edge>
```

Puis redéployer.

Le secret reste côté serveur et n'est jamais renvoyé au navigateur.

## Vérification

Après connexion :

```text
/api/aviation/notam/status
/api/aviation/notams?icao=LFPG
```

Le Centre OPS et les fiches aéroport du Globe utilisent ces endpoints. Si le fournisseur ou la clé n'est pas disponible, le jeu affiche un état propre et ne génère pas de faux NOTAM.
