# CHANGELOG — SKYLINE AIRWAYS v1.3.1

## OPS intelligence ciblée

- Suppression de la dépendance `AVIATION_EDGE_API_KEY`.
- Intégration FAA NOTAM Search sans clé, avec cache serveur et déduplication.
- Surveillance limitée aux hubs et aux aéroports réellement utilisés par les rotations du joueur.
- Classification automatique des avis : espace aérien, piste, taxiway, navigation, infrastructure, opérations.
- Priorités `CRITIQUE / IMPORTANT / INFO`.
- Veille FIR à fort impact affichée seulement lorsqu'une route du joueur traverse la région ; aucune fermeture n'est inventée.
- METAR/TAF AviationWeather.gov conservés.
- Ajout des SIGMET mondiaux AviationWeather.gov et filtrage par corridor de route.
- Nouvel endpoint `/api/ops/intelligence`.
- Nouvel écran OPS avec KPIs, flux d'alertes pertinentes et marqueurs de risque sur le Globe.
- PWA/cache et assets frontend passés en v131.
