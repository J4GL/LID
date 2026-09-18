## SERVER-STATIC-001 — Les fichiers statiques sont revalidés à chaque chargement

Sans `Cache-Control`, le navigateur applique son cache heuristique : après un `upgrade.sh`, il
continue de servir l'ancien `app.js` et l'interface paraît inchangée. `no-cache` impose la
revalidation ; l'`ETag` évite quand même de retélécharger un fichier inchangé (304).

Implement: le montage `/static` dans `create_app` (`app/main.py`), servi par une sous-classe de
`StaticFiles` qui pose l'en-tête sur chaque réponse.
Out of scope: la mise en cache des réponses de l'API et de la page HTML elle-même.

Test: unit · `tests/test_api.py` · `test_server_static_001_static_files_must_be_revalidated`
- Given: l'application servie par `create_app`
- When: `GET /static/app.js` est demandé
- Then: la réponse a le statut 200, un en-tête `Cache-Control` valant `no-cache` et un `ETag`
- When: la même requête est renvoyée avec `If-None-Match` valant cet `ETag`
- Then: la réponse a le statut 304, sans corps
