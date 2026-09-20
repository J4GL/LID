## DEL-001 — Supprimer un torrent en staging efface son dossier et ses fichiers

Implement: `Engine.action(key, "remove_with_files")` dans `app/engine.py`,
`Manager.action` dans `app/manager.py` (purge `known` comme `remove`), et
`DELETE /api/torrents/{key}?delete_files=true` dans `app/main.py`, appelé par
la barre de confirmation inline de `app/static/app.js`.

Test: unit · `tests/test_remove_files.py` · `test_del_001_remove_with_files_deletes_staging_folder`
- Given: un moteur avec un record `nested` dont le dossier
  `downloads/<mode>/<key>` contient des fichiers, et un manager dont `known`
  référence ce torrent
- When: `DELETE /api/torrents/{key}?delete_files=true` est appelé
- Then: le record est retiré de l'index, `.source`/`.resume` sont supprimés,
  le dossier du torrent a disparu du disque, `known` ne contient plus l'id, et
  la réponse contient `"removed"` et `"files_deleted": true`
- When: `DELETE /api/torrents/{key}` (sans flag) est appelé sur un torrent équivalent
- Then: le torrent est retiré mais ses fichiers restent sur le disque (comportement inchangé)

## DEL-002 — En dossier final plat, seuls les fichiers du torrent sont effacés

Implement: `Engine.action(key, "remove_with_files")` dans `app/engine.py` via
`CompletionMoves.discard_stale(path, files, prune_root=False)` et
`CompletionMoves.entries_of` dans `app/moves.py`.

Test: unit · `tests/test_remove_files.py` · `test_del_002_flat_deletes_only_own_entries`
- Given: un record `flat` dont l'entrée (`dossier/` de 2 fichiers + son
  `<entrée>.parts`) partage le dossier final avec l'entrée d'un autre torrent
- When: `Engine.action(key, "remove_with_files")` est appelé
- Then: l'entrée du torrent et son `.parts` ont disparu, l'entrée voisine est
  intacte, la racine finale existe toujours, et `.source`/`.resume` sont supprimés
- Given: un record `flat` dont le dossier final contient un symlink à la place d'un fichier listé
- When: `Engine.action(key, "remove_with_files")` est appelé
- Then: le symlink n'est pas suivi ni supprimé (aucune écriture à travers)

## DEL-003 — La suppression avec fichiers est gardée comme le retrait simple

Implement: `Engine.action(key, "remove_with_files")` dans `app/engine.py`.

Test: unit · `tests/test_remove_files.py` · `test_del_003_remove_with_files_guards_and_edge_cases`
- Given: un record en phase `moving` (puis `verifying`)
- When: `Engine.action(key, "remove_with_files")` est appelé
- Then: `StorageUnavailable` est levée et le torrent reste dans l'index
- Given: un magnet sans métadonnées (aucun fichier sur disque)
- When: `Engine.action(key, "remove_with_files")` est appelé
- Then: le torrent est retiré comme un `remove` simple, sans erreur
- Given: un record `nested` dont le chemin enregistré n'est pas sous la racine validée
- When: `Engine.action(key, "remove_with_files")` est appelé
- Then: aucune suppression sur disque n'a lieu et le torrent reste dans l'index
- Given: un record dont un fichier est ineffaçable (`OSError` à la suppression)
- When: `Engine.action(key, "remove_with_files")` est appelé
- Then: le torrent est retiré et le résultat contient `file_errors` non vide nommant le chemin en faute
