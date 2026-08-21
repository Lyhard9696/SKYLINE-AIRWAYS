# SKYLINE AIRWAYS v0.3 — version web jouable full-stack

Cette version remplace la maquette v0.2 par un **prototype réellement jouable**.

## Ce qui fonctionne

- Création de compte, connexion et sauvegarde par utilisateur
- Base PostgreSQL sur Render via `render.yaml`
- Nouvelle partie : 90 M€, CDG niveau 1, **aucun avion**
- Achat ou leasing d'avions
- Catalogue ATR / Airbus / Boeing
- Flotte persistante
- Création et suppression de lignes depuis CDG
- Vérification de l'autonomie avant ouverture d'une ligne
- Scénarios de restrictions CDG→SVO et CDG→IKA
- Simulation accélérée des vols et revenus
- Carte mondiale OpenStreetMap interactive
- Avions qui se déplacent sur leurs lignes
- Clic avion → vue cockpit d'observation avec HUD dynamique
- Hub CDG en vue aérienne zoomable / déplaçable
- Achat **directement sur la vue aérienne** en cliquant les zones
- Plus de 30 éléments de hub : portes, parkings, sécurité, PAF, douanes, toilettes, duty free, restauration, lounges, bagages, catering, service à bord, maintenance, fuel, dégivrage, équipages, OPS, cargo, hôtel...
- Services à 8 ou 10 niveaux : ils ne passent plus au MAX après un seul achat
- Progression visuelle du hub selon son niveau
- Interface responsive iPhone / PC

## Important : ce que v0.3 n'est pas encore

Ce n'est pas encore le jeu AAA photoréaliste final. Le cockpit est une **vue d'observation simulée**, pas un cockpit 3D pilotable. La carte monde est une carte interactive 2D, pas encore le globe 3D Unreal Engine. Les NOTAM de cette version sont des scénarios de démonstration, pas encore un flux temps réel certifié.

Le moteur final visé reste : Unreal Engine 5 pour la 3D + backend de simulation persistant.

## Mettre à jour le projet Render existant

1. Sur GitHub, remplace le contenu du dépôt par les fichiers de ce dossier.
2. Commit sur `main`.
3. Le Blueprint Render détectera le nouveau `render.yaml`.
4. Va dans Render > Blueprint `skyline-airways` > **Manual sync** si la synchronisation ne part pas automatiquement.
5. Le Blueprint ajoutera une base PostgreSQL `skyline-db` et reliera automatiquement `DATABASE_URL` au service web.
6. Une fois le déploiement terminé, ouvre l'URL Render.
7. Tu arriveras sur l'écran **Connexion / Créer un compte**.

## Test local

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 10000
```

Puis ouvre `http://localhost:10000`.
