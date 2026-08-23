# SKYLINE AIRWAYS v1.3.6

- Corrige l’erreur de syntaxe de la Boutique v1.3.5 qui empêchait la navigation (Globe, Hub, etc.).
- Catalogue : 591/591 types ont maintenant une illustration locale légère sur fond blanc ; aucune recherche distante n’est nécessaire pour afficher les cartes.
- FR24 : trafic visible dès la vue monde avec symboles avion progressifs au zoom ; aucun trafic mondial fictif n’est généré.
- Hub : uniquement les vrais aéronefs FR24/OpenSky, aucun camion/bus décoratif animé.
- Fiches live : photo exacte par immatriculation/hex quand disponible, sinon illustration du type ; plus de fallback vers une photo d’aéroport.
- Compagnies : résolution locale via le catalogue embarqué (~2 000 compagnies) avant appel FR24, plus badges premium locaux pour 80+ grandes compagnies mondiales.
- Réduction des caches serveur et maintien du chargement viewport/tuiles pour Render 512 Mo.
- Cache PWA et fichiers frontend bumpés à 1.3.6.
