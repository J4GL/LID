## DASH-HEADER-001 — « Add a torrent » est centré dans le header, sans titre « Dashboard / Transfers »

Implement: `app/static/index.html` — le bloc `.page-heading` (« DASHBOARD »,
« Transfers. ») est retiré et `#add-button` est placé dans `.header`, entre la
marque et les boutons langue / proxy ; le titre `h1` reste pour les lecteurs
d'écran en `.sr-only` ; mise en page dans `app/static/style.css`, clic branché
par `openAdd` dans `app/static/app.js`, servis par `create_app` (`app/main.py`) sur `/`.
Out of scope: le mobile (≤ 800 px), où le bouton reste dans le header sans
garantie de centrage exact.

Test: e2e · `tests/test_dashboard_header.py` · `test_dash_header_001_add_button_centered_in_header`
- Given: l'application servie par uvicorn avec un manager factice, ouverte dans
  obscura (viewport 1280 px, langue `en`)
- When: la page est chargée
- Then: aucun élément `.page-heading` ni
  `[data-i18n="dashboard"]` n'existe ; le `h1` vaut
  `Transfers` et mesure au plus 1 × 1 px ; `#add-button` est dans `.header`,
  visible, son centre horizontal est celui de `.header` à 1 px près et son
  centre vertical celui de `.brand` à 1 px près ; il ne chevauche ni
  `.header-label` (à sa gauche) ni `#language-toggle` (à sa droite)
- When: l'utilisateur clique sur `#add-button`
- Then: `#add-dialog` est ouvert
