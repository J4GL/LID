## DASH-COMPACT-001 — Le toggle bascule et mémorise la vue compacte

Implement: `installCompactToggle` dans `app/static/compact.js`, branché par
`app/static/app.js` sur le bouton `#compact-toggle` de `.list-heading` et sur
`#torrent-list`, avec `localStorage` comme stockage.

Test: unit · `tests/compact.test.mjs` · "DASH-COMPACT-001 toggles and remembers the compact view"
- Given: un stockage vide
- When: `installCompactToggle({ button, list, storage })` est appelé
- Then: le bouton est `aria-pressed="false"` et la liste n'a pas la classe `compact`
- When: l'utilisateur clique sur le bouton
- Then: la liste a la classe `compact`, le bouton est `aria-pressed="true"` et
  le stockage contient `p2p-compact` = `"1"`
- When: l'utilisateur clique de nouveau
- Then: la classe `compact` est retirée, le bouton est `aria-pressed="false"` et
  `p2p-compact` vaut `"0"`
- Given: un stockage contenant `p2p-compact` = `"1"`
- When: `installCompactToggle` est appelé
- Then: la liste a la classe `compact` et le bouton est `aria-pressed="true"`
- Given: un stockage dont `getItem` et `setItem` lèvent une exception
- When: `installCompactToggle` est appelé puis le bouton est cliqué
- Then: l'installation ne lève pas, la liste démarre sans `compact`, puis le clic
  ajoute `compact` et met le bouton à `aria-pressed="true"`

## DASH-COMPACT-002 — Le libellé du toggle existe en anglais et en français

Implement: clé `list.compact` dans `app/static/i18n.js`, appliquée au bouton
`#compact-toggle` de `app/static/index.html` via `data-i18n-title` et
`data-i18n-aria`.

Test: unit · `tests/i18n.test.mjs` · "DASH-COMPACT-002 compact toggle label is translated"
- Given: la langue `en`
- When: `t("list.compact")` est appelé
- Then: il renvoie `Compact view`
- Given: la langue `fr`
- When: `t("list.compact")` est appelé
- Then: il renvoie `Vue compacte`

## DASH-COMPACT-003 — En vue compacte, un torrent tient sur une ligne avec une barre deux fois moins large

Implement: bouton `#compact-toggle` dans `app/static/index.html`, élément
`.torrent-activity` rempli par `render()` dans `app/static/app.js` avec
`formatAgo(last_upload_at)`, règles `#torrent-list.compact` dans
`app/static/style.css`, servis par `create_app` (`app/main.py`) sur `/`.
Uses: [DASH-COMPACT-001](#dash-compact-001--le-toggle-bascule-et-mémorise-la-vue-compacte),
[Seeding last-upload](../seeding/last-upload.md)
Out of scope: le mobile (≤ 800 px), où la vue compacte peut passer sur deux lignes.

Test: e2e · `tests/test_dashboard_compact.py` · `test_dash_compact_003_one_line_rows_with_half_width_bar`
- Given: l'application servie par uvicorn avec un manager factice exposant deux
  torrents — `long` (nom de 200 caractères, téléchargement, progress 0.42,
  `last_upload_at` `null`) et `seed` (seeding, progress 1, ratio 1.23,
  `last_upload_at` = maintenant − 6 h) — ouverte dans obscura (viewport 1280 px,
  langue `en`, stockage vide)
- When: la page est chargée
- Then: `#compact-toggle` est `aria-pressed="false"`, chaque ligne fait plus de
  56 px de haut et sa barre `progress` mesure `Wn` px de large
- When: l'utilisateur clique sur `#compact-toggle`
- Then: `#torrent-list` a la classe `compact` et le bouton est
  `aria-pressed="true"` ; pour chaque ligne, nom, ratio, pourcentage, barre, ↓, ↑, dernière activité
  et actions sont visibles, se chevauchent verticalement (`max(top) < min(bottom)`),
  apparaissent dans cet ordre de gauche à droite, et la ligne fait au plus 56 px ;
  badge, taille, pairs, volumes, état et chemin sont masqués et
  `#table-labels` aussi ; chaque barre mesure `Wn / 2` px à 1 px près et chaque nom est plus large
  qu'en vue normale ; le nom de `long` est tronqué : `text-overflow`
  calculé vaut `ellipsis` et la largeur naturelle du texte (clone `max-content`)
  dépasse la largeur affichée ; la dernière activité affiche `6h ago` pour `seed` et `Never shared` pour `long`
- When: l'utilisateur clique de nouveau sur `#compact-toggle`
- Then: `#torrent-list` n'a plus la classe `compact`, le bouton est
  `aria-pressed="false"` et chaque barre mesure `Wn` px à 1 px près
