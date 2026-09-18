## STORAGE-FLAT-001 — Completed torrents land directly in the final folder

The final folder is browsed by people, not by the engine, so it holds no `direct`/`proxy`
separation and no infohash folder: a completed torrent's own top-level entry sits at the root of
the final folder. A multi-file torrent contributes its folder, a single-file torrent a bare file.
The staging folder keeps `<mode>/<infohash>/`, where the infohash still keeps two downloads of the
same name apart.

Implement: `CompletionMoves.target_for` and `CompletionMoves.begin` in `app/moves.py`, using the
`flat` branch of `destination_for` in `app/policy.py`. Reached from `CompletionMoves.tick`, called
by `Engine.tick` in `app/engine.py`.
Uses: [Path layout is recorded, never re-derived](#storage-flat-006--the-path-layout-is-read-from-the-index-never-re-derived)
Out of scope: the staging folder, which keeps its nested layout.

Test: unit · `tests/test_moves.py` · `test_storage_flat_001_completed_torrents_land_in_the_final_folder`
- Given: a seeding multi-file torrent whose files are `album/a.bin` and `album/nested/b.bin`, a
  final folder configured and empty apart from its identity marker
- When: the engine is ticked until the move reaches phase `done`
- Then: every file is readable at `<final>/album/…` with its original bytes, the final folder holds
  no `direct`, `proxy` or infohash entry, the record's `path` is the final folder itself, its
  `layout` is `flat`, and the torrent is seeding

- Given: a seeding single-file torrent whose only file is `payload.bin`
- When: the engine is ticked until the move reaches phase `done`
- Then: `<final>/payload.bin` is a file holding the original bytes, the final folder still holds
  its identity marker, and the torrent is seeding

## STORAGE-FLAT-002 — An identical copy already in the final folder is adopted, not duplicated

Two torrents can claim the same top-level entry in a flat folder. When the entry already there
holds the same files — same relative paths, same sizes, nothing extra — the data is the same data,
so the move is replaced by an adoption: nothing is copied, libtorrent hash-checks the entry in
place, and the staging copy is discarded once it passes. This also lets a torrent removed by the
inactivity sweep be re-added and seed at once from the files it left behind.

Implement: the occupied-destination branch of `CompletionMoves.begin` in `app/moves.py`, which
writes a journal with `target_claimed` false and re-attaches the torrent through `Engine.restore`,
so the existing recovery path in `CompletionMoves.prepare_restore` adopts the destination.
Uses: [Interrupted move recovery](interrupted-move.md)

Test: unit · `tests/test_moves.py` · `test_storage_flat_002_an_identical_entry_is_adopted_instead_of_duplicated`
- Given: a seeding multi-file torrent in the staging folder, and a copy of every one of its files
  already present at its top-level entry in the final folder
- When: the engine is ticked until the move reaches phase `done`
- Then: the final folder's copy is untouched byte for byte, no second entry was created, the
  staging copy no longer holds any file of the torrent, the record's `path` is the final folder
  with `layout` `flat`, and the torrent is seeding

## STORAGE-FLAT-003 — A different entry of the same name is kept, and the torrent is suffixed

When the existing entry holds different content, nothing may be overwritten: the torrent takes the
first free `Nom (2)`, `Nom (3)`… name instead. For a single-file torrent the suffix goes before the
extension. The chosen name is recorded in the index and re-applied to libtorrent on every restart,
so it survives the fast-resume sanitising that deliberately drops renames coming from resume data.

Implement: the suffix branch of `CompletionMoves.begin` in `app/moves.py`, recorded as
`storage["folder"]` and re-applied by `apply_folder` in `app/policy.py`, called from `Engine.attach`
in `app/engine.py`.

Test: unit · `tests/test_moves.py` · `test_storage_flat_003_a_different_entry_of_the_same_name_is_suffixed`
- Given: a seeding multi-file torrent named `album` in the staging folder, and a folder `album` in
  the final folder holding one file of the same name but different bytes
- When: the engine is ticked until the move reaches phase `done`
- Then: the pre-existing `<final>/album` is byte for byte unchanged, every file of the torrent is
  readable under `<final>/album (2)/`, the record's `folder` is `album (2)`, and the torrent is
  seeding
- When: the engine is closed and restarted
- Then: libtorrent's save path is the final folder, the torrent is seeding without downloading, and
  its files are still read from `<final>/album (2)/`

## STORAGE-FLAT-004 — A discarded copy never reaches beyond what the move itself wrote

In the nested layout the infohash folder made a recorded path the property of one torrent, so
discarding a stale copy could not touch anyone else. A flat final folder is shared, and two
torrents can list the same relative path at the same size, so a stale copy is only deleted when
the move actually created it: the journal records `target_claimed`, and the final folder itself is
never removed.

Implement: `CompletionMoves.discard_stale` and the `target_claimed` key written by
`CompletionMoves.begin` in `app/moves.py`, read by the `torrent_checked_alert` branch of
`CompletionMoves.alert`.
Uses: [Interrupted move recovery](interrupted-move.md)

Test: unit · `tests/test_moves.py` · `test_storage_flat_004_a_discarded_copy_never_reaches_another_torrent`
- Given: a file belonging to another torrent already at `<final>/album/a.bin`, and a seeding
  torrent whose journal records an interrupted move into that same flat folder with
  `target_claimed` false and a complete copy still in the staging folder
- When: the engine is restarted and ticked until the move settles
- Then: the other torrent's file is unchanged byte for byte, the final folder still exists, and the
  recovering torrent is seeding without having downloaded any payload

## STORAGE-FLAT-005 — The final folder is never walked, and a symlinked entry blocks the move

The nested layout could afford a recursive symlink scan of one torrent's folder; the final folder
holds the whole library, so walking it is not an option. The check becomes exact instead of
recursive: the torrent's own top-level entries are inspected without following links, which is also
the only protection left, since libtorrent's own existence pre-check follows a symlink and would
write straight through it.

Implement: the `flat` branch of `destination_for` in `app/policy.py` and the entry check in
`CompletionMoves.begin` in `app/moves.py`.

Test: unit · `tests/test_moves.py` · `test_storage_flat_005_the_final_folder_is_never_walked_and_symlinks_block_the_move`
- Given: a seeding multi-file torrent named `album`, a symlink `<final>/album` pointing outside the
  final folder, and `Path.rglob` patched to raise if it is ever called
- When: the engine is ticked
- Then: the move does not start, the record's phase is `failed` with an error naming the entry, the
  symlink is still a symlink, its target folder is still empty, and `Path.rglob` was never called
- When: the symlink is removed and the move is retried
- Then: the move reaches phase `done`, `Path.rglob` was still never called, and the torrent is
  seeding

## STORAGE-FLAT-006 — The path layout is read from the index, never re-derived

Which shape a torrent's files have on disk is a fact about that torrent, not about today's
settings: the final folder can be changed at any time, and records keep pointing at the root they
were moved to. The shape is therefore stored per record, and an index written before this key
existed reads back as nested so an upgrade relocates nothing.

Implement: the `layout` key of `CompletionMoves.new_record`, its backfill in
`CompletionMoves.__init__` (records and any in-flight journal), and the `layout` argument threaded
through `CompletionMoves.valid_path` in `app/moves.py`.

Test: unit · `tests/test_moves.py` · `test_storage_flat_006_the_layout_is_read_from_the_index`
- Given: an index whose records carry a `storage` dict with no `layout`, one of them holding an
  in-flight journal with no `source_layout` or `target_layout`
- When: the engine is started
- Then: it starts without raising, every record reads back as `layout` `nested`, the journal's two
  sides read back as `nested` with `target_claimed` false, `index.before-flat.json` holds the index
  as it was, and no file moved on disk

- Given: a torrent moved to a flat final folder, and the final folder then changed to another one
  in the storage settings
- When: the engine is restarted
- Then: the record still reads `layout` `flat` on its original root, libtorrent's save path is that
  original root, and the torrent is seeding
