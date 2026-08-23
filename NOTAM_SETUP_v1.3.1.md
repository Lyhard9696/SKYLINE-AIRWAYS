# SKYLINE AIRWAYS v1.3.1 — NOTAM & risques OPS

## Aucun abonnement requis

Les NOTAM sont interrogés côté serveur via le **FAA NOTAM Search public** :

```text
https://notams.aim.faa.gov/notamSearch/search
```

Aucune clé API n'est nécessaire et aucun secret NOTAM ne doit être ajouté dans GitHub ou Render.

## Logique de filtrage

SKYLINE ne télécharge pas des milliers d'avis pour les afficher au joueur. Le moteur surveille :

1. tous les hubs que le joueur possède ;
2. les aéroports de départ, arrivée et escale de ses rotations ;
3. les SIGMET AviationWeather.gov qui croisent les corridors de ses routes ;
4. une petite veille FIR prioritaire, affichée seulement si une route du joueur traverse réellement la région.

Les avis sont classés `CRITIQUE`, `IMPORTANT` ou `INFO`. Les fermetures d'aérodrome/piste et interdictions d'espace aérien montent en priorité. Les NOTAM d'aéroports sans rapport avec le réseau du joueur ne génèrent pas de notification.

## Météo

Une tempête n'est jamais transformée artificiellement en NOTAM. La météo sévère vient de METAR/TAF/SIGMET AviationWeather.gov. Si une fermeture officielle existe, le NOTAM FAA correspondant est affiché séparément.

## Endpoints

```text
/api/aviation/notam/status
/api/aviation/notams?icao=LFPG
/api/ops/intelligence
```

## Cache

```text
OPS_NOTAM_CACHE_SECONDS=600
OPS_SIGMET_CACHE_SECONDS=180
```

FAA NOTAM Search ne fournit pas de SLA d'API publique. En cas d'indisponibilité temporaire, l'interface affiche un état propre au lieu d'inventer des données.
