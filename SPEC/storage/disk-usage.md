## DISK-001 — L'état expose l'usage disque des racines de stockage

Implement: `Manager.state()` dans `app/manager.py` (via `shutil.disk_usage` sur les
racines `downloads` / `completed` de `FolderSettings.payload()`), exposé par
`GET /api/torrents` et `GET /api/events` dans `app/main.py`, affiché par la
pastille disque de `.list-heading` dans `app/static/app.js`.

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
