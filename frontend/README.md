# Argos Frontend

Frontend statique minimal pour Argos (thème noir / rouge).

- Fichiers créés:
  - `index.html`
  - `css/style.css`
  - `js/app.js`

Fonctionnalités ajoutées:

- Thème sombre noir/rouge, layout: sidebar gauche, panneau droit de configuration.
- Options dynamiques par module (Nmap, FFUF) dans le panneau de configuration.
- Upload de wordlist (sélection locale, nom affiché — l'upload réel est à gérer côté backend).
- Liste de workflows prédéfinis (cliquables) qui affichent les étapes.
- Bouton `Run` principal et duplication dans le panneau de config.
- Appels API simulés à `POST /api/run` avec fallback simulé si le backend est absent.

Pour tester localement, ouvrir `index.html` dans le navigateur. Pour intégrer au serveur WebUI, copier le dossier `frontend` dans le dossier statique du serveur (`Argos/WebUI/static`) et ajuster les routes côté `server.py` pour servir l'`index.html`.

Notes pour l'intégration backend:

- Endpoint attendu: `POST /api/run` (payload JSON: { module, target, options, wordlist }).
- Uploads de fichiers peuvent être implémentés plus tard via un endpoint dédié (`/api/upload`).

