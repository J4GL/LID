## SEED-LASTUP-001 — Un torrent terminé affiche son dernier envoi en relatif

Implement: `Engine.snapshot` dans `app/engine.py` (lignes exposées via `Manager.state` dans `app/manager.py` vers `GET /api/torrents` et la SSE `/api/events` dans `app/main.py`), rendu par `render()` dans `app/static/app.js` via le helper `app/static/timeago.js` et les clés `torrent.last_upload*` dans `app/static/i18n.js`. L'âge s'affiche entre parenthèses à droite de l'état, dans `.progress-label` : `Seeding ( Last upload: 7m ago )`.
Uses: [Server binding](../server/bind.md)

Test: unit · `tests/test_seeding.py` · `test_seed_lastup_001_snapshot_exposes_last_upload_and_finished_anchors`
- Given: un record moteur avec `last_upload_at`, `finished_at` et `added_at` connus, sans session libtorrent active
- When: `Engine.snapshot()` est appelé
- Then: la ligne expose `last_upload_at` et `finished_at` inchangés, et un record ancien sans ces clés est normalisé à `None` sans lever d'erreur

Test: unit · `tests/timeago.test.mjs` · `seeding timeago SEED-LASTUP-001 formats relative age in French and English`
- Given: un timestamp `last_upload_at` vieux de 6 heures puis de 2 jours, langue EN puis FR
- When: `formatAgo(ts, now, lang)` est appelé
- Then: il retourne `6h ago` puis `2 days ago` en EN, `il y a 6 h` puis `il y a 2 j` en FR, et `Never shared` / `Jamais partagé` quand le timestamp est `null`
