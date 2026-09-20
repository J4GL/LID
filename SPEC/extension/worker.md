## EXT-SW-001 — Le service worker intercepte, stocke l'attente et envoie vers LID

Implement: `extension/background.js` (service worker MV3), avec les API
`chrome` mockées et `fetch` injecté dans le test.
Out of scope: l'affichage réel de la popup et des notifications Chrome
(validation manuelle) ; la demande de permission d'origine, faite au clic
dans la popup de route.

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-001 worker intercepts stores pending and sends`
- Given: un téléchargement `.torrent` signalé par `downloads.onCreated`
- When: le gestionnaire tourne
- Then: `cancel()` puis `erase()` sont appelés pour cet id, l'attente est
  stockée en `storage.session` avec l'URL `finalUrl`, et une fenêtre popup
  de route est ouverte
- Given: un téléchargement `.torrent` en `blob:` et un fichier ordinaire
- When: le gestionnaire tourne
- Then: rien n'est annulé ; le `blob:` déclenche une notification expliquant
  le repli manuel
- Given: un clic menu sur un lien magnet
- When: le gestionnaire tourne
- Then: l'attente magnet est stockée et la popup de route est ouverte,
  sans appel réseau
- Given: une attente fichier et un message `lid-send` avec mode `proxy`
- When: le gestionnaire tourne avec un `fetch` mocké vers LID
- Then: les octets du tracker sont récupérés puis postés sur
  `/api/torrents/files` avec `mode=proxy`, l'attente est effacée et une
  notification de succès est créée
- Given: un message `lid-send` pour une attente inconnue
- When: le gestionnaire tourne
- Then: la réponse signale l'échec sans aucun `fetch`
