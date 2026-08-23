# TEST REPORT — SKYLINE AIRWAYS v1.3.6

Exécuté avant packaging :

- `python -m py_compile main.py models.py logic.py catalog.py` — OK
- `node --check static/game-v136.js` — OK
- `tests/ops_intelligence_v131.py` — OK
- `tests/smoke_v133.py` — OK
- `tests/smoke_v136.py` — OK
- `/health` — HTTP 200, version 1.3.6
- runtime JS/CSS v1.3.6 — HTTP 200
- couverture illustrations aéronefs — 591/591
- identité compagnie sans token FR24 — seed + catalogue local (~2 000 compagnies)
- FR24 mock — trafic sol + trafic en vol conservés simultanément
- Hub hiérarchique/contextuel — OK
- trafic mondial fictif — désactivé par l’override final v1.3.6

Les appels FR24 réels dépendent toujours du token, du plan et des crédits du compte de production.
