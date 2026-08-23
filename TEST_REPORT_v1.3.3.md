# SKYLINE AIRWAYS v1.3.3 — Test report

Tests exécutés avant création de l'archive GitHub :

- `python -m py_compile main.py logic.py models.py catalog.py` — OK
- `node --check static/game-v133.js` — OK
- `node --check static/setup.js` — OK
- `python tests/smoke_v132.py` — OK
- `python tests/smoke_v133.py` — OK
- `python tests/ops_intelligence_v131.py` — OK
- FastAPI `/health` + chargement des assets v1.3.3 — OK
- Audit des références statiques : 41 vérifiées, 0 manquante — OK

Le test v1.3.3 couvre notamment la hiérarchie des zones de hub, la mobilité contextuelle CDG/Limoges, le refus serveur d'une option localement impossible, le cycle de travaux et le fallback FR24 ciblé pour un appareil au sol.

Ces tests sont des tests de régression déterministes et n'appellent pas les services externes de production. Le comportement réel FR24/FAA/AviationWeather dépend de leur disponibilité et, pour FR24, du plan/token configuré sur Render.
