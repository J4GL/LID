## DISK-001 — L'état expose l'usage disque des racines de stockage

Implement: `Manager.state()` dans `app/manager.py` (via `shutil.disk_usage` sur les
racines `downloads` / `completed` de `FolderSettings.payload()`), exposé par
`GET /api/torrents` et `GET /api/events` dans `app/main.py`, affiché par
`renderStorage()` dans `app/static/app.js` (voir DISK-003 et DISK-004).

Test: unit · `tests/test_disk_usage.py` · `test_disk_001_state_exposes_storage_disk_usage`
- Given: un manager avec `storage.downloads` et `storage.completed` existants
- When: `Manager.state()` est appelé
- Then: `state["disks"]` contient une entrée par racine avec `label`
  (`downloads` ou `completed`), `path`, `total`, `used`, `free` en octets, et
  `total == used + free` avec `total > 0`

## DISK-002 — Les disques sont dédupliqués par device et absents en setup

Implement: `Manager.state()` dans `app/manager.py` et le payload `setup_only`
de `GET /api/torrents` dans `app/main.py`.

Test: unit · `tests/test_disk_usage.py` · `test_disk_002_disks_deduped_and_setup_empty`
- Given: un manager dont `completed` est `None`
- When: `Manager.state()` est appelé
- Then: `state["disks"]` ne contient que l'entrée `downloads`
- Given: un manager dont `downloads` et `completed` sont sur le même device
- When: `Manager.state()` est appelé
- Then: `state["disks"]` ne contient qu'une seule entrée
- Given: une racine de stockage inexistante ou illisible (`OSError`)
- When: `Manager.state()` est appelé
- Then: la racine en faute est omise sans lever, les autres entrées restent
- Given: l'application en `setup_only` (pas de manager)
- When: `GET /api/torrents` est appelé
- Then: la réponse contient `"disks": []`

## DISK-003 — Le disque temporaire s'affiche dans le pied de page

Implement: `renderStorage()` dans `app/static/app.js`, appelé par `render()` à
chaque état reçu de `GET /api/torrents` / `GET /api/events`, remplit
`#temporary-disk` de `.footer` dans `app/static/index.html` (à la place du slogan
« Two routes. One space. ») avec l'entrée `downloads` de `state.disks`.
Out of scope: le mobile (≤ 800 px), où le pied de page peut passer sur plusieurs lignes.

Test: e2e · `tests/test_dashboard_storage.py` · `test_disk_003_temporary_disk_in_footer`
- Given: l'application servie avec `disks` = `downloads` 256 GiB utilisés sur
  512 GiB et `completed` 768 GiB sur 1 TiB, ouverte dans obscura (1280 px, `en`)
- When: la page est chargée
- Then: `#temporary-disk` est visible dans `.footer`, entre `#live-label` et
  `#storage-button` de gauche à droite ; il affiche `Downloads` et
  `256.0 GiB / 512.0 GiB` ; sa barre est `ok` et son remplissage mesure 50 %
  de la barre à 1 px près ; aucun `[data-i18n="footer.tagline"]` ni
  `#disk-widget` n'existe
- Given: `disks` = `downloads` 471 GiB utilisés sur 512 GiB (92 %), sans `completed`
- When: la page est chargée
- Then: `#temporary-disk` affiche `471.0 GiB / 512.0 GiB` et sa barre est `full`
- Given: `disks` = `[]`
- When: la page est chargée
- Then: `#temporary-disk` est masqué

## DISK-004 — Le disque de destination s'affiche en camembert après « Global ratio »

Implement: `renderStorage()` dans `app/static/app.js`, appelé par `render()`,
remplit la carte `#destination-disk` placée après la carte « Global ratio » dans
`.metrics` de `app/static/index.html`, avec l'entrée `completed` de
`state.disks`, ou à défaut l'entrée `downloads` (pas de déplacement, ou même
disque dédupliqué par DISK-002).
Uses: [DISK-002](#disk-002--les-disques-sont-dédupliqués-par-device-et-absents-en-setup)
Out of scope: le mobile (≤ 800 px), où la carte passe sur sa propre ligne.

Test: e2e · `tests/test_dashboard_storage.py` · `test_disk_004_destination_disk_pie_card`
- Given: l'application servie avec `disks` = `downloads` 256 GiB sur 512 GiB et
  `completed` 768 GiB utilisés sur 1 TiB, ouverte dans obscura (1280 px, `en`)
- When: la page est chargée
- Then: `#destination-disk` est le 5ᵉ `.metric`, juste après la carte
  « Global ratio », sur la même ligne (même `top`) à sa droite ; il affiche
  `Destination disk`, `75 %` et `768.0 GiB / 1.0 TiB` ; son camembert
  `.disk-pie` est visible et mesure au moins 40 × 40 px, porte la classe `ok`,
  sa part utilisée `.disk-pie-used` a `stroke-dasharray` = `75.0 100` et son
  `aria-label` vaut `Destination disk: 75 % used`
- Given: `disks` = `downloads` 435 GiB utilisés sur 512 GiB (85 %), sans `completed`
- When: la page est chargée
- Then: `#destination-disk` affiche `85 %` et `435.0 GiB / 512.0 GiB`, le
  camembert porte la classe `warn` et `stroke-dasharray` vaut `85.0 100`
- Given: `disks` = `[]`
- When: la page est chargée
- Then: `#destination-disk` est masqué et la carte « Global ratio » s'arrête au
  bord droit de `.metrics` à 1 px près

## DISK-005 — Les libellés de stockage existent en anglais et en français

Implement: clés `metrics.destination` et `metrics.destination_used` dans
`app/static/i18n.js`, lues par `renderStorage()` dans `app/static/app.js`.

Test: unit · `tests/i18n.test.mjs` · "DISK-005 storage labels are translated"
- Given: la langue `en`
- When: `t("metrics.destination")` puis `t("metrics.destination_used", { value: "75 %" })` sont appelés
- Then: ils renvoient `Destination disk` puis `Destination disk: 75 % used`
- Given: la langue `fr`
- When: les mêmes appels sont faits
- Then: ils renvoient `Disque de destination` puis `Disque de destination : 75 % utilisé`
