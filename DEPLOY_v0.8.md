# Déployer SKYLINE AIRWAYS v0.8 sur GitHub + Render

## 1. GitHub

Décompresse le ZIP puis envoie **le contenu** du dossier à la racine du dépôt existant. Remplace les fichiers quand GitHub le demande.

Commit conseillé :

`SKYLINE v0.8 Realism Restore`

Ne supprime pas la base PostgreSQL `skyline-db` sur Render.

## 2. Flightradar24 — service Render existant

`render.yaml` déclare `FR24_API_TOKEN` avec `sync: false`, mais sur un service déjà créé tu dois renseigner le secret dans le Dashboard Render.

1. Render Dashboard
2. Ouvre le service **skyline-airways**
3. **Environment**
4. **Add Environment Variable**
5. Key : `FR24_API_TOKEN`
6. Value : colle un **nouveau token régénéré**
7. **Save Changes**
8. **Deploy latest commit** (ou Manual Deploy)

Le token précédemment partagé dans une conversation doit être révoqué et ne doit pas être réutilisé.

## 3. Vérifier après déploiement

Connecte-toi au jeu puis :

**☰ Plus → Centre OPS & diagnostics → Tester FR24 + météo**

Résultat attendu pour FR24 :
- `OK · full` ou `OK · light` ;
- nombre de positions reçues ;
- nombre d'appareils détectés au sol près du hub.

Si l'API refuse la requête, l'écran affiche une raison sanitizée (401/403/429, clé absente, etc.) sans afficher le secret.

Tu peux également tester après connexion :
- `/api/integrations/fr24/status`
- `/api/integrations/fr24/test?ident=LFPG`
- `/api/live-traffic?ident=LFPG`

## 4. Si l'ancienne interface reste sur iPhone

La v0.8 change le cache PWA. Après le premier nouveau déploiement :
- recharge complètement la page ;
- si une ancienne installation PWA persiste, ferme-la puis relance-la ;
- en dernier recours, supprime l'ancienne web-app de l'écran d'accueil puis ajoute-la de nouveau.

## 5. Santé serveur

`/health` doit indiquer `version: 0.8.0`.
