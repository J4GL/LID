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

## EXT-CAP-004 — Le hook mémorise l'ancrage du dernier clic

Implement: `extension/blob-hook.js` (monde MAIN, `document_start`, enregistré
par `hookMatches` dans `extension/background.js`) ; lu par `pickerBounds` pour
placer la popup de route (EXT-SW-012).
Out of scope: la conversion d'unités propre à Chrome (zoom de page), faite par
le worker.

Test: unit · `tests/extension-capture.test.mjs` · `EXT-CAP-004 blob hook records the last click anchor`
- Given: le script réel du hook chargé dans un contexte isolé exposant
  `addEventListener`, un `<a>` de rect `{left:40, right:120, bottom:60}`
- When: un `pointerdown` (capture) arrive sur ce lien avec `screenX:540,
  screenY:320, clientX:50, clientY:30`
- Then: un écouteur `pointerdown` et un `contextmenu` sont enregistrés en
  capture, et `__lidLastClick` vaut `{left:530, right:610, bottom:350}` avec
  `at` égal à l'horloge de la page
- Given: le même hook, un `<span>` dans un `<button>` de rect
  `{left:10, right:90, bottom:44}`
- When: un `contextmenu` arrive sur le `<span>` avec `screenX:300,
  screenY:200, clientX:20, clientY:20`
- Then: `__lidLastClick` vaut `{left:290, right:370, bottom:224}` (rect du
  bouton, pas du `<span>`)
- Given: un ancrage déjà mémorisé
- When: un `pointerdown` clavier arrive (`screenX:0, clientX:0`)
- Then: `__lidLastClick` reste inchangé

## EXT-CAP-005 — Un clic sur un lien magnet est confié au worker au lieu du système

Implement: `extension/magnet-hook.js` (monde ISOLATED, `document_start`),
enregistré par `hookMatches` dans `extension/background.js` avec le hook blob
et sur les mêmes sites ; il envoie `lid-magnet` au worker (EXT-SW-013).
Out of scope: les magnets ouverts par script (`location = "magnet:…"`,
`window.open`) et les sites non autorisés, qui restent au gestionnaire du
système ; le menu contextuel (EXT-CAP-002) couvre ces cas.

Test: unit · `tests/extension-capture.test.mjs` · `EXT-CAP-005 magnet hook hands magnet clicks to the worker`
- Given: le script réel chargé dans un contexte isolé exposant
  `addEventListener` et `chrome.runtime.sendMessage`, et un
  `<a href="magnet:?xt=urn:btih:abc&dn=Ubuntu">` contenant un `<span>`
- When: un `click` de confiance (`isTrusted`, `button:0`) arrive sur le `<span>`
- Then: un seul écouteur `click` est enregistré, en capture ;
  `preventDefault` est appelé et `sendMessage` reçoit exactement
  `{type:"lid-magnet", magnet:"magnet:?xt=urn:btih:abc&dn=Ubuntu"}`
- Given: le même lien
- When: un `click` non fiable (`isTrusted:false`, clic simulé par la page)
  arrive, puis un `click` déjà `defaultPrevented`, puis un `click` de bouton
  milieu, puis un `click` sur un lien `https://…`
- Then: ni `preventDefault` ni `sendMessage` pour aucun d'eux
- Given: le script exécuté une seconde fois dans le même contexte
  (réinjection dans un onglet ouvert)
- When: un `click` de confiance arrive sur le lien magnet
- Then: toujours un seul écouteur et un seul `sendMessage`
- Given: `chrome.runtime.sendMessage` lève (extension rechargée, contexte
  invalidé)
- When: un `click` de confiance arrive sur le lien magnet
- Then: aucune exception ne remonte et `preventDefault` n'est pas appelé
  (le système ouvre le magnet comme sans extension)
