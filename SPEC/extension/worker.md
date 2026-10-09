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
- Given: un téléchargement `.torrent` en `blob:`, un en `data:` et un
  fichier ordinaire
- When: le gestionnaire tourne
- Then: le `blob:` est intercepté comme un fichier (attente `blob` +
  popup) ; le `data:` déclenche une notification expliquant le repli
  manuel sans annulation ; le fichier ordinaire est ignoré
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

## EXT-SW-002 — Un .torrent reconnu tardivement est intercepté sans doublon

Implement: gestionnaire `downloads.onChanged` dans
`extension/background.js`, qui relit l'item via `downloads.search` et
partage l'interception avec `onCreated`.
Out of scope: l'affichage réel de la popup (validation manuelle).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-002 worker intercepts late torrent filenames once`
- Given: un téléchargement créé sans nom (`onCreated` l'ignore), dont
  le delta `filename.current` porte `x.torrent` alors que `search`
  ne le reflète pas encore
- When: `onChanged` tourne
- Then: `cancel()` + `erase()` sont appelés, l'attente est stockée avec le nom
  de l'événement et l'URL récupérable, et la popup de route est ouverte
- Given: le même téléchargement signalé à nouveau (création puis nom)
- When: les deux gestionnaires tournent
- Then: une seule popup est ouverte et l'attente n'est stockée qu'une fois
- Given: un fichier ordinaire au nom déterminé, ou un changement de seul
  état (cas distincts)
- When: `onChanged` tourne
- Then: aucune annulation ni popup ni notification n'est ajoutée
- Given: un téléchargement au nom générique dont seul `mime.current`
  devient `application/x-bittorrent`
- When: `onChanged` tourne
- Then: une seule annulation, un effacement et une popup sont demandés pour
  ce téléchargement, et l'attente contient l'URL HTTP récupérable

## EXT-SW-003 — Un .torrent en blob: est lu dans la page puis envoyé

Implement: interception `blob:` et `handleSend` dans
`extension/background.js`, via `tabs.query` et `scripting.executeScript`
en monde MAIN (octets rendus en base64, JSON oblige).
Out of scope: la demande de permission d'origine (geste dans la popup) ;
le chargement réel dans Chrome (validation manuelle).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-003 worker reads page blobs and sends them`
- Given: un téléchargement `blob:https://site/x` au mime `x-bittorrent`
  et sans nom
- When: `onCreated` tourne
- Then: `cancel()` + `erase()` sont tentés aussitôt (best effort, les
  octets vivent dans la page), l'attente `blob` est stockée avec l'origine
  du site et l'id du téléchargement, et la popup de route est ouverte
- Given: le delta `onChanged` apportant le vrai nom dans `filename.current`
- When: le gestionnaire tourne
- Then: le nom de l'attente est rafraîchi et aucune seconde popup n'est ouverte
- Given: cette attente et un message `lid-send` avec mode `proxy`, un
  onglet du site rendant les octets en base64, et un `fetch` mocké vers LID
- When: le gestionnaire tourne
- Then: `erase()` est rappelé après lecture des octets sans nouvelle
  annulation si le téléchargement est terminé, le fichier est posté sur
  `/api/torrents/files` avec `mode=proxy`, l'attente est effacée
  et une notification de succès est créée (mentionnant le fichier local
  à supprimer si le téléchargement était déjà terminé)
- Given: la même attente sans onglet du site (page fermée)
- When: `lid-send` tourne
- Then: la réponse porte `code === "blob_no_tab"`, aucun nouvel
  appel `cancel`/`erase` n'a lieu et l'attente est conservée pour un
  nouvel essai

## EXT-SW-004 — Les octets blob sont lus par anticipation quand possible

Implement: `cacheBlobEarly` dans `extension/background.js`, appelé à
l'interception `blob:` quand l'origine est déjà autorisée ; `sendBlob`
réutilise le cache et n'annule que les téléchargements en cours.
Out of scope: la demande de permission d'origine (geste dans la popup) ;
le chargement réel dans Chrome (validation manuelle).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-004 worker prefetches blob bytes when permitted`
- Given: un téléchargement `blob:` sur une origine déjà autorisée, avec
  un onglet servant les octets
- When: `onCreated` tourne puis `lid-send` tourne (page fermée entre-temps)
- Then: une seule injection a eu lieu (à l'interception), l'envoi réussit
  depuis le cache sans nouvel onglet, et le cache est vidé après succès
- Given: un téléchargement `blob:` sur une origine non autorisée
- When: `onCreated` tourne
- Then: aucune injection n'a lieu (pas de permission à ce stade) et la
  popup s'ouvre normalement
- Given: un envoi `blob` dont le téléchargement est déjà terminé
- When: `lid-send` tourne avec succès
- Then: `cancel()` n'est pas rappelé (téléchargement terminé) mais
  `erase()` oui, et la notification mentionne le fichier local

## EXT-SW-005 — Un envoi blob sans permission d'origine le signale

Implement: `readBlobBytes` dans `extension/background.js` revérifie
`permissions.contains` et écarte les onglets sans URL visible ; code
`origin_revoked` dans `extension/messages.js`.
Out of scope: le ré-octroi lui-même (interrupteur dans
`chrome://extensions`, ou demande dans la popup de route).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-005 worker reports revoked origin on blob send`
- Given: une attente `blob` dont l'origine n'est plus autorisée
- When: `lid-send` tourne
- Then: la réponse porte `code === "origin_revoked"`, aucun nouvel
  appel `cancel`/`erase` n'a lieu et l'attente est conservée
- Given: l'origine autorisée mais seuls des onglets sans URL visible
- When: `lid-send` tourne
- Then: la réponse porte `code === "blob_no_tab"`

## EXT-SW-006 — Les blobs sont conservés via un hook précoce insensible au CSP

Implement: `extension/blob-hook.js` (monde MAIN, `document_start`,
enregistré par `registerBlobHook` dans `extension/background.js` sur
message `lid-register-hook` envoyé par `extension/route.js` après octroi
d'origine) ; `readBlobAsBase64` lit le stash d'abord (`Blob.arrayBuffer`,
hors CSP et insensible à la révocation), `fetch` en repli. Le message
`blob_unavailable` conseille de relancer le téléchargement sur la page.
Out of scope: le premier blob d'une origine nouvellement accordée dans la
popup, créé avant l'enregistrement du hook (perdu ; nouvel essai sur la page).
Les origines déjà autorisées sont couvertes par EXT-SW-011.

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-006 worker stashes page blobs past CSP and revoke`
- Given: une origine autorisée sans script enregistré, avec un onglet ouvert
- When: `lid-register-hook` tourne
- Then: `registerContentScripts` est appelé une fois avec `lid-blob-hook`
  (monde MAIN, `document_start`, `blob-hook.js`) puis `lid-magnet-hook`
  (monde ISOLATED, `document_start`, `magnet-hook.js`, EXT-CAP-005), aux mêmes
  motifs, et l'onglet ouvert reçoit `blob-hook.js` (MAIN) puis
  `magnet-hook.js` (ISOLATED) par `executeScript` avec `files`
- Given: un hook enregistré pour une origine, puis `lid-register-hook`
  pour une seconde origine
- When: le message tourne
- Then: `updateContentScripts` fusionne les deux motifs pour les deux
  scripts, sans second appel à `registerContentScripts`
- Given: la fonction injectée capturée et un stash contenant le Blob
- When: elle tourne avec l'URL du blob (`fetch` saboté)
- Then: elle résout le base64 exact des octets, sans appeler `fetch`
- Given: la fonction injectée sans entrée stash
- When: elle tourne avec un `fetch` servant le blob
- Then: elle résout le base64 via le repli `fetch`

## EXT-SW-007 — Le fichier blob est recherché dans les onglets de son origine

Implement: `blobOrigin` et `readBlobBytes` dans `extension/background.js`,
appelés par `downloads.onCreated` et par `lid-send` depuis `extension/route.js`.
Out of scope: Chrome réel et le téléchargement BitTorrent ; les API Chrome
et LID sont doublées dans ce test unitaire.

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-007 worker finds blob bytes across tabs for proxy upload`
- Given: deux onglets de l'origine du blob, un onglet étranger et un onglet
  sans URL ; le référent est absent, réduit à l'origine, périmé ou étranger
  (cas distincts) ; le premier onglet du site échoue ou rend un résultat
  absent, vide ou mal encodé, et le second rend les octets attendus
- When: `onCreated` intercepte le torrent sans permission, puis la permission
  est accordée et `lid-send` reçoit `mode=proxy`
- Then: l'attente porte l'origine du blob, une seule popup est demandée,
  seuls les deux onglets du site sont interrogés dans cet ordre en monde
  MAIN avec l'URL exacte du blob, et les octets et le nom exacts sont envoyés
  une fois à `/api/torrents/files` avec `mode=proxy` ; l'attente est supprimée
  et une seule notification de succès est créée
- Given: les mêmes onglets mais un référent correspondant exactement au
  second onglet, qui contient les octets
- When: l'interception puis l'envoi proxy ont lieu
- Then: seul le second onglet est lu et l'envoi réussit une fois avec les
  mêmes octets, nom et mode ; l'attente est supprimée
- Given: une permission retirée, aucun onglet accessible, ou deux onglets
  du site sans octets lisibles (cas distincts)
- When: `lid-send` reçoit `mode=proxy`
- Then: il rend respectivement `origin_revoked`, `blob_no_tab` ou
  `blob_unavailable`, conserve l'attente, ne fait aucun appel réseau ni
  nouvelle annulation ; dans le dernier cas, les deux onglets ont été essayés

## EXT-SW-008 — Un envoi proxy partage la lecture anticipée et garde les octets en cas d'échec

Implement: `cacheBlobEarly` et `sendBlob` dans `extension/background.js`,
appelés par `downloads.onCreated` puis `lid-send` depuis la popup de route.
Out of scope: persistance des octets après arrêt du service worker ; Chrome
et LID réels (API doublées).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-008 worker shares blob reads and retains bytes for proxy retry`
- Given: une origine autorisée, une ouverture de popup suspendue et une
  lecture des octets suspendue
- When: `onCreated` intercepte le torrent
- Then: une seule popup est demandée et la lecture commence avant que son
  ouverture se termine, sans appel réseau
- When: la popup finit de s'ouvrir et `lid-send` reçoit `mode=proxy`
- Then: la même lecture reste l'unique injection, l'envoi attend les octets
  et aucun appel réseau n'a encore lieu
- When: les octets arrivent et LID répond `proxy_unavailable`
- Then: un seul upload a été tenté avec les octets, le nom et le mode proxy
  attendus, la réponse porte `proxy_unavailable`, l'attente est conservée
  et aucune notification de succès n'est créée
- When: la page est fermée et un nouvel envoi proxy reçoit un succès de LID
- Then: aucun onglet n'est relu, les mêmes octets sont envoyés, l'attente
  est supprimée et une seule notification de succès est créée
- When: l'ancienne attente est réintroduite et envoyée à nouveau sans onglet
- Then: la réponse porte `blob_no_tab`, sans nouvel upload (cache libéré)
- Given: l'origine n'est pas autorisée lors de l'interception, puis elle est
  autorisée et l'envoi proxy lit les octets mais échoue avec `proxy_unavailable`
- When: la page est fermée et l'envoi proxy est réessayé avec succès
- Then: les octets de la lecture au moment de l'envoi sont réutilisés sans
  nouvelle injection, les deux uploads portent les mêmes octets, nom et
  mode proxy, l'attente est supprimée et une seule notification de succès
  est créée
- Given: une lecture anticipée qui échoue faute d'octets lisibles
- When: les octets deviennent disponibles et `lid-send` reçoit `mode=proxy`
- Then: une nouvelle lecture réussit, un seul upload contient les octets,
  le nom et le mode proxy attendus, et l'attente est supprimée

## EXT-SW-009 — Une annulation devenue impossible ne pollue pas la console

Implement: annulation best effort dans `extension/background.js`, appelée lors
de l'interception d'un téléchargement `.torrent` et avant l'envoi d'un blob.
Out of scope: modifier le résultat de l'ajout ou masquer les erreurs LID.

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-009 worker consumes late download cancellation errors`
- Given: un double de l'API d'annulation signale une erreur via
  `runtime.lastError` dans son callback
- When: `downloads.onCreated` intercepte le torrent et tente son annulation
- Then: le callback lit `runtime.lastError`, aucun avertissement non consommé
  n'est produit, l'historique du téléchargement est effacé et la popup de
  choix est ouverte normalement
- Given: la recherche précédant un envoi blob rend un téléchargement
  `interrupted`
- When: `lid-send` reçoit `mode=proxy`
- Then: l'extension ne tente pas de l'annuler, efface son entrée, envoie le
  torrent une fois en proxy et signale le succès

## EXT-SW-010 — Un nom reçu après annulation ne déclenche aucune suggestion

Implement: observation des noms via `downloads.onChanged` dans
`extension/background.js`, sans abonnement à `onDeterminingFilename`.
Out of scope: console de Chrome réel ; le double reproduit le rappel
automatique de `suggest` par Chromium et son refus après annulation.

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-010 worker observes late filenames without suggesting after cancellation`
- Given: un torrent blob reconnu par son MIME, sans nom à sa création,
  et un téléchargement Chrome dont l'annulation réussit sans erreur
- When: `onCreated` est reçu, avant tout choix de mode
- Then: une seule annulation et un effacement sont demandés, une seule
  popup est ouverte, l'attente est stockée et aucun envoi réseau n'a lieu
- When: Chrome détermine le nom après cette annulation puis signale
  `filename.current` et `state.current=interrupted` via `onChanged`
- Then: aucun gestionnaire de détermination du nom n'est enregistré,
  aucune suggestion ni erreur `Download must be in progress` n'est produite,
  le nom de l'attente est actualisé, sans seconde popup, annulation ou
  effacement ni appel réseau
- When: `lid-send` reçoit `mode=proxy`
- Then: l'envoi réussit une seule fois avec les octets capturés et le nom
  actualisé, l'attente est supprimée et une notification de succès est créée

## EXT-SW-011 — Le hook blob couvre toutes les origines déjà autorisées dès le démarrage

Implement: `syncBlobHook` dans `extension/background.js`, appelé par
`runtime.onInstalled` (installation, mise à jour, rechargement),
`runtime.onStartup` et `permissions.onAdded` (octroi depuis la popup de route
ou `chrome://extensions`).
Uses: [EXT-SW-006](#ext-sw-006--les-blobs-sont-conservés-via-un-hook-précoce-insensible-au-csp)
Out of scope: une origine jamais accordée (aucun hook possible avant l'octroi).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-011 worker hooks every granted origin at startup`
- Given: `permissions.getAll` rend le serveur LID (permission d'hôte du
  manifeste), `https://site.example/*` et `https://other.example/*`, aucun
  script enregistré, et un onglet ouvert sur `https://site.example/t`
- When: `runtime.onInstalled` tourne avec `reason: "update"`
- Then: `registerContentScripts` est appelé une fois avec `lid-blob-hook`
  (monde MAIN, `document_start`, `blob-hook.js`) et `lid-magnet-hook` (monde
  ISOLATED, `magnet-hook.js`), chacun avec exactement `https://site.example/*`
  et `https://other.example/*`, sans le serveur LID, et l'onglet ouvert reçoit
  `blob-hook.js` puis `magnet-hook.js` par `executeScript` avec `files`
- When: `runtime.onStartup` tourne ensuite
- Then: aucun second `registerContentScripts` ; les motifs enregistrés restent
  exactement les deux origines, sans doublon
- When: `permissions.onAdded` signale `https://new.example/*`
- Then: `updateContentScripts` enregistre les deux origines plus
  `https://new.example/*`, pour les deux scripts
- Given: `permissions.getAll` ne rend que le serveur LID
- When: `runtime.onStartup` tourne
- Then: aucun enregistrement, mise à jour ni injection n'a lieu
- Given: une version précédente a laissé `lid-blob-hook` seul, enregistré
  pour `https://site.example/*`, et `permissions.getAll` rend
  `https://site.example/*` et `https://other.example/*`
- When: `runtime.onInstalled` tourne avec `reason: "update"`
- Then: `updateContentScripts` met `lid-blob-hook` sur les deux origines et
  `registerContentScripts` crée `lid-magnet-hook` sur ces deux mêmes origines

## EXT-SW-012 — La popup de route s'ouvre sous l'élément cliqué, sinon au centre de la fenêtre

Implement: `openRoutePicker` / `pickerBounds` dans `extension/background.js`,
appelés par `interceptDownload` (onglet actif de la fenêtre au premier plan),
`handleMenuClick` (onglet transmis par `contextMenus.onClicked`) et le message
`lid-magnet` (onglet émetteur, EXT-SW-013).
Uses: [EXT-CAP-004](capture.md#ext-cap-004--le-hook-mémorise-lancrage-du-dernier-clic)
Out of scope: le rendu réel de la fenêtre par Chrome (validation manuelle).

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-012 worker places the route picker under the clicked element`

Chaque cas part d'une fenêtre au premier plan `{left:100, top:50, width:1200,
height:800}` dont l'onglet actif est 7, et d'un téléchargement `.torrent`
http intercepté ; la popup mesure 380×300.
- Given: un ancrage `{left:400, right:480, bottom:220}` daté de maintenant,
  zoom 1
- When: la popup de route s'ouvre
- Then: `executeScript` vise l'onglet 7 en monde MAIN et `windows.create`
  reçoit `left:250, top:224`
- Given: le même ancrage, zoom 1.25
- When: la popup de route s'ouvre
- Then: `windows.create` reçoit `left:360, top:279`
- Given: un ancrage `{left:1240, right:1290, bottom:780}`, zoom 1
- When: la popup de route s'ouvre
- Then: `windows.create` reçoit `left:920, top:550` (bornée dans la fenêtre)
- Given: un ancrage daté de 11 s
- When: la popup de route s'ouvre
- Then: `windows.create` reçoit `left:510, top:300` (centre de la fenêtre)
- Given: `executeScript` rejette (site non autorisé)
- When: la popup de route s'ouvre
- Then: `windows.create` reçoit `left:510, top:300`
- Given: un clic menu sur un lien magnet depuis l'onglet 42, ancrage
  `{left:400, right:480, bottom:220}` récent, zoom 1
- When: la popup de route s'ouvre
- Then: `executeScript` vise l'onglet 42 et `windows.create` reçoit
  `left:250, top:224`
- Given: `windows.getLastFocused` rejette
- When: la popup de route s'ouvre
- Then: `windows.create` est appelé sans `left` ni `top`, sans injection

## EXT-SW-013 — Un magnet cliqué dans la page ouvre la popup de route

Implement: le message `lid-magnet` dans `handleMessage` de
`extension/background.js`, envoyé par `extension/magnet-hook.js`
(EXT-CAP-005) ; même attente `magnet` que `handleMenuClick`, popup placée par
`pickerBounds` sur l'onglet émetteur (EXT-SW-012).
Uses: [EXT-CAP-005](capture.md#ext-cap-005--un-clic-sur-un-lien-magnet-est-confié-au-worker-au-lieu-du-système),
[EXT-SW-012](#ext-sw-012--la-popup-de-route-souvre-sous-lélément-cliqué-sinon-au-centre-de-la-fenêtre)

Test: unit · `tests/extension-worker.test.mjs` · `EXT-SW-013 worker opens the route picker for a clicked magnet`
- Given: une fenêtre au premier plan `{left:100, top:50, width:1200,
  height:800}`, un ancrage `{left:400, right:480, bottom:220}` récent, zoom 1
- When: `lid-magnet` arrive avec
  `magnet:?xt=urn:btih:abc&dn=Ubuntu+24.04` depuis l'onglet 42
- Then: la réponse vaut `{ok:true}` ; la session contient une seule attente
  `{kind:"magnet", magnet:<le lien>, name:"Ubuntu 24.04"}` ; `executeScript`
  vise l'onglet 42 et `windows.create` ouvre `route.html?id=<cette attente>`
  en `left:250, top:224`
- When: `lid-send` arrive pour cette attente avec le mode `direct`
- Then: `POST /api/torrents/magnet` reçoit `{mode:"direct", magnet:<le lien>}`
  et l'attente est retirée de la session
- Given: un `lid-magnet` dont le lien vaut `https://site.example/x`, puis un
  `lid-magnet` valide sans onglet émetteur
- When: chacun arrive
- Then: chacun répond `{ok:false, code:"unexpected_response"}`, sans attente
  en session ni fenêtre ouverte
