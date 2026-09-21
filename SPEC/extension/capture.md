## EXT-CAP-000 — Le manifeste déclare une extension MV3 à permissions étroites

Implement: `extension/manifest.json`, chargé non empaqueté dans Chrome.

Test: unit · `tests/extension-capture.test.mjs` · `EXT-CAP-000 manifest declares narrow MV3 permissions`
- Given: le fichier `extension/manifest.json`
- When: il est parsé et inspecté
- Then: `manifest_version` vaut 3, `permissions` contient exactement
  `downloads`, `contextMenus`, `storage`, `notifications` et `scripting`
  (lecture des `blob:` dans le monde MAIN de la page), `host_permissions`
  ne couvre que le serveur LID configuré par défaut, et
  `optional_host_permissions` couvre `http`/`https` sans `host_permissions`
  large ni content scripts

## EXT-CAP-001 — Un téléchargement .torrent est reconnu et son URL récupérable extraite

Implement: `isTorrentDownload` et `fetchableHttpUrl` dans
`extension/classify.js`, appelés par le gestionnaire `downloads.onCreated`
dans `extension/background.js` avant `cancel()` + `erase()`.
Out of scope: le clic dans la popup de route et l'envoi réseau (EXT-CLI-001) ;
le chargement réel dans Chrome (validation manuelle).

Test: unit · `tests/extension-capture.test.mjs` · `EXT-CAP-001 recognizes torrent downloads and extractable urls`
- Given: un item `.torrent` en `http(s)`, un item au mime
  `application/x-bittorrent`, un item `.torrent` en `blob:` et un fichier
  ordinaire
- When: `isTorrentDownload` puis `fetchableHttpUrl` sont appliqués
- Then: les deux premiers sont reconnus avec l'URL `finalUrl` prioritaire,
  le `blob:` est reconnu mais sans URL récupérable, et le fichier ordinaire
  est ignoré

## EXT-CAP-002 — Un lien au menu contextuel est classé magnet, fichier ou ignoré

Implement: `classifyLink` et `trackerOrigin` dans `extension/classify.js`,
appelés par le gestionnaire `contextMenus.onClicked` dans
`extension/background.js`.
Out of scope: l'affichage du menu Chrome lui-même (validation manuelle).

Test: unit · `tests/extension-capture.test.mjs` · `EXT-CAP-002 classifies context menu links`
- Given: un lien `magnet:?xt=...`, un lien `https://.../x.torrent?pass=1`,
  un lien vers une page web et une chaîne vide
- When: `classifyLink` est appliqué, puis `trackerOrigin` sur le lien fichier
- Then: les kinds valent `magnet`, `file`, `null` et `null`, et l'origine
  du tracker vaut `https://` + hôte (+ port non défaut)

## EXT-CAP-003 — Le hook garde les octets après révocation de l'URL

Implement: `extension/blob-hook.js`, enregistré par `registerBlobHook` dans
`extension/background.js` à `document_start` en monde MAIN pour les sites
autorisés, puis lu par `readBlobAsBase64`.
Out of scope: injection réelle dans Chrome et contraintes CSP du navigateur ;
le script réel est exécuté dans un contexte JavaScript isolé.

Test: unit · `tests/extension-capture.test.mjs` · `EXT-CAP-003 blob hook retains bytes after object URL revocation`
- Given: le script réel du hook chargé dans un contexte isolé, un Blob aux
  octets connus et un `fetch` qui échoue à chaque appel
- When: une URL est créée via `URL.createObjectURL`, puis révoquée via
  `URL.revokeObjectURL`
- Then: l'URL native ne résout plus de Blob, mais le Blob conservé par le
  hook rend exactement les octets d'origine sans aucun appel à `fetch`
