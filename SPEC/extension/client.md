## EXT-CLI-001 — Le client récupère le token, rejoue sur 403 et envoie fichiers et magnets

Implement: `LidClient` dans `extension/lid.js` (avec `fetch` injecté),
utilisé par le service worker `extension/background.js` vers
`POST /api/torrents/files` et `POST /api/torrents/magnet`.
Out of scope: la demande de permission d'origine du tracker (geste dans la
popup de route, validation manuelle) ; le service worker lui-même
(EXT-SW-001).

Test: unit · `tests/extension-client.test.mjs` · `EXT-CLI-001 client bootstraps token retries once and posts`
- Given: un `fetch` mocké (`/api/bootstrap` rend un token, l'upload rend
  `201` avec `results[0].ok`)
- When: `uploadTorrent(bytes, "x.torrent", "direct")` est appelé
- Then: un `FormData` avec `mode` et le fichier `.torrent` est posté avec
  `X-P2P-Token`, et le résultat contient le nom et le mode
- Given: un `fetch` mocké rendant `403 session_expired` puis `201` après
  un second `/api/bootstrap`
- When: `sendMagnet("magnet:?...")` est appelé
- Then: le token est rechargé et la requête rejouée une seule fois avec succès
- Given: un `fetch` mocké rendant `409 duplicate_torrent`
- When: `uploadTorrent` est appelé
- Then: une `LidError` avec `code === "duplicate_torrent"` est levée
- Given: un `fetch` mocké rendant `409` avec `results[0]` en échec
  (`error_code: "invalid_torrent"`, sans code global)
- When: `uploadTorrent` est appelé
- Then: une `LidError` avec `code === "invalid_torrent"` est levée
  (erreur par fichier, pas générique)
- Given: des octets de plus de 10 Mio
- When: `uploadTorrent` est appelé
- Then: aucun `fetch` n'a lieu et une `LidError` avec `code === "file_too_large"` est levée

## EXT-CLI-002 — Les codes d'erreur LID sont traduits en messages FR et EN

Implement: `messageFor` dans `extension/messages.js`, utilisé par la popup
de route et les notifications de `extension/background.js`.

Test: unit · `tests/extension-client.test.mjs` · `EXT-CLI-002 error codes map to FR and EN messages`
- Given: les codes `duplicate_torrent`, `proxy_unavailable`,
  `proxy_not_configured`, `invalid_torrent`, `file_too_large`,
  `server_unreachable`, `blob_unavailable`, `blob_no_tab`,
  `origin_revoked` et un code inconnu
- When: `messageFor(code, "fr")` puis `messageFor(code, "en")` sont appelés
- Then: chaque code connu rend un message non vide distinct par langue, et
  le code inconnu rend le message générique sans lever

## EXT-CLI-003 — La demande d'accès au tracker rend faux quand elle échoue

Implement: `ensureOrigin` dans `extension/ui.js`, utilisé par la popup de
route `extension/route.js` et les options `extension/options.js` au clic.

Test: unit · `tests/extension-client.test.mjs` · `EXT-CLI-003 origin request failure reads as denied`
- Given: `permissions.contains` vrai, puis `request` faux, puis `request`
  qui lève
- When: `ensureOrigin` est appelé dans chaque cas
- Then: il rend `true` sans appeler `request` dans le premier cas, et
  `false` dans les deux autres sans jamais lever

## EXT-CLI-004 — Le client appelle fetch sans receveur détaché

Implement: constructeur de `LidClient` dans `extension/lid.js`, qui enveloppe
le `fetch` injecté au lieu de l'appeler en méthode.

Test: unit · `tests/extension-client.test.mjs` · `EXT-CLI-004 client calls fetch without detached receiver`
- Given: un `fetch` doublé qui rejette `Illegal invocation` quand son
  receveur n'est ni `undefined` ni `globalThis` (sémantique navigateur),
  et rend un token sinon
- When: `new LidClient(url, strictFetch).status()` est appelé
- Then: le statut est retourné sans `Illegal invocation`, ce qui échouerait
  si le client appelait le fetch en méthode (`this.fetch`)
