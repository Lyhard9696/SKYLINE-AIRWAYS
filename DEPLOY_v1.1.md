# Déploiement Render — v1.1

## Secret Flightradar24
Dans le service Web Render `skyline-airways` :

1. Ouvrir **Environment**.
2. Ajouter/modifier la variable :
   - **Key** : `FR24_API_TOKEN`
   - **Value** : la valeur du **Access Token** généré dans le portail Flightradar24.
3. Ne pas ajouter `Bearer ` devant la valeur : SKYLINE construit lui-même le header `Authorization: Bearer <token>`.
4. Enregistrer puis lancer/relaisser Render redéployer le service.

Le fichier `render.yaml` contient déjà `FR24_API_TOKEN` avec `sync: false`, donc aucune valeur secrète n'est enregistrée dans GitHub.

## Vérification
Après déploiement et connexion au jeu :
- `/api/integrations/fr24/status` doit retourner `configured: true`.
- `/api/integrations/fr24/test?ident=CDG` doit retourner `ok: true` si le plan FR24 autorise l'endpoint.
- Le Globe OPS affiche le trafic autour des hubs puis recharge une zone réelle lorsque l'utilisateur zoome.

Si le test renvoie 401/403, le problème vient du token ou des droits du plan FR24, pas du rendu du globe.
