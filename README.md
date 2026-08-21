# SKYLINE AIRWAYS — v0.2 Render / iPhone

Cette version est faite pour être hébergée sur **Render** et utilisée directement sur iPhone, iPad, Mac ou PC.

Elle utilise uniquement **Python standard** côté serveur : aucune bibliothèque Python à installer.

## Déployer sur Render

### 1. GitHub
Crée un dépôt GitHub et dépose **tout le contenu de ce dossier à la racine**.

Tu dois notamment voir :
- `app.py`
- `render.yaml`
- `templates/`
- `static/`

### 2. Render — méthode la plus simple
1. Dans Render : **New → Blueprint**
2. Connecte ton dépôt GitHub
3. Sélectionne le dépôt SKYLINE
4. Render détecte `render.yaml`
5. Clique sur le déploiement

Le fichier `render.yaml` configure automatiquement :
- Runtime : Python
- Build : `python --version`
- Start : `python app.py`
- Health check : `/health`

Render donnera ensuite une URL du type :

`https://skyline-airways.onrender.com`

## Sur iPhone

1. Ouvre l'URL Render dans **Safari**
2. Appuie sur **Partager**
3. Choisis **Sur l’écran d’accueil**
4. Garde le nom `SKYLINE`

Le prototype possède :
- un manifest PWA ;
- une icône SKYLINE ;
- un mode standalone ;
- une interface responsive iPhone ;
- une sauvegarde locale de la progression dans Safari.

## Fonctionnalités déjà interactives

- Hub CDG évolutif
- rendu niveau 1 / 4 / 8 / 12
- zones grisées → progression visuelle
- achat des portes
- parkings
- sûreté
- police aux frontières
- pompiers / ARFF
- toilettes
- duty free
- restauration
- lounges Business / First
- bagages
- catering
- maintenance
- centre équipages
- Operations Control Center
- carte réseau
- scénarios OPS / NOTAM
- déroutement vers un alternate
- Paris → Istanbul → Téhéran en deux appareils/opérateurs
- flotte
- pool de pilotes / fatigue
- écran « Rendu » avec la direction cible iPhone + Web

## Test local

Dans ce dossier :

```bash
python app.py
```

Puis ouvre :

`http://localhost:10000`

## Important

Les restrictions, NOTAM et données opérationnelles du prototype sont illustratives.
La version finale pourra brancher des données réelles autorisées.

## Pour le vrai jeu photoréaliste

Cette version est une PWA/prototype de gameplay.

Architecture cible :
- **Unreal Engine 5** : globe 3D, CDG, avions, cockpit, météo, sol
- **Python/backend** : simulation, OPS, économie, équipages, maintenance, données
- **Base persistante** : sauvegardes et monde long terme
