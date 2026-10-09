## ADD-ROUTE-001 — Ajouter sans route choisie explique quoi faire au lieu de rester grisé

Implement: `createRoutePicker` dans `app/static/add-route.js`, branché par
`app/static/app.js` sur `.mode-picker` / `.mode-choice` de la boîte « New
transfer » ; `#magnet-submit` et `#pick-files` restent cliquables hors ajout en
cours et appellent `require()` avant tout envoi ou ouverture du sélecteur de
fichiers ; `onMissing` y affiche `error.route_required` dans `#add-error`.

Test: unit · `tests/add-route.test.mjs` · "ADD-ROUTE-001 asks for a route instead of staying disabled"
- Given: un picker `direct` / `proxy` venant d'être ouvert (`reset()`), aucune route choisie
- When: `require()` est appelé (clic sur « Add link » ou « Choose .torrent files »)
- Then: il renvoie `null`, `onMissing` est appelé une fois, le picker porte la
  classe `needs-route` et le focus est sur le bouton `direct`
- When: l'utilisateur clique sur `proxy`
- Then: `mode` vaut `"proxy"`, `proxy` est `aria-pressed="true"` et `direct`
  `"false"`, la classe `needs-route` est retirée et `onSelect` reçoit `"proxy"`
- When: `require()` est appelé
- Then: il renvoie `"proxy"` sans rappeler `onMissing`
- When: `reset()` est appelé (réouverture de la boîte)
- Then: `mode` vaut `null`, les deux choix sont `aria-pressed="false"` et
  `needs-route` est absent

## ADD-ROUTE-002 — Le message « route requise » existe en anglais et en français

Implement: clé `error.route_required` dans `app/static/i18n.js`, lue par
`localizedError("route_required")` depuis `app/static/app.js`.

Test: unit · `tests/i18n.test.mjs` · "ADD-ROUTE-002 route required message is translated"
- Given: la langue `en`
- When: `localizedError("route_required")` est appelé
- Then: il renvoie `Choose a route first: Direct or Proxy.`
- Given: la langue `fr`
- When: `localizedError("route_required")` est appelé
- Then: il renvoie `Choisissez d’abord une route : Direct ou Proxy.`
