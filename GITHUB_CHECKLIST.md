# Checklist GitHub / Render

- [ ] Ajouter ce dossier au dépôt.
- [ ] Choisir `node-service` OU `python-service`.
- [ ] Ne jamais commiter `.env`.
- [ ] Render : `FR24_API_TOKEN` = token production depuis Access Tokens / Key Management.
- [ ] Vérifier `/health` -> `tokenConfigured: true`.
- [ ] Vérifier `/health` -> `sandboxLikely: false`.
- [ ] Tester `/api/fr24/live?scope=world`.
- [ ] Vérifier que `stats.airborne > 0`.
- [ ] Vérifier que `count` est bien supérieur au petit échantillon précédent.
- [ ] Vérifier un vol Air France : `paintedAs=AFR` => `liveryCode=AFR`.
- [ ] Ne jamais sélectionner une livrée depuis `aircraftType`.
- [ ] Brancher `frontend-integration/aviation-live-client.js`.
- [ ] Remplacer le vieux statut par `fr24StatusText(result)`.
- [ ] Appeler les photos uniquement au clic sur un avion.
- [ ] Brancher les fichiers `shared/game/*.json` dans les écrans Alliance / Prochaines ères.
