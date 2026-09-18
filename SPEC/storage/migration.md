## STORAGE-MIGRATE-001 — The migration shows its whole plan and changes nothing until told to

A library already on disk under `<final>/<mode>/<infohash>/` has to be relocated once, offline.
Because the step is irreversible and touches every completed torrent at once, the command reports
first and acts only when asked: it prints each relocation, each adoption, each suffix, each empty
shell it would remove and each obstacle it found, and writes nothing. It refuses to run at all
while the service holds the data folder, or while any record is mid-move, since recovery reads both
sides of a move in flight.

Implement: `main` and `plan` in `app/migrate.py`, run as `python -m app.migrate`, taking the
`app.lock` flock of `app/launch.py`.
Uses: [Completed torrents land directly in the final folder](flat-final.md)
Out of scope: records still in the staging folder or attached to a previous root, which keep the
nested layout.

Test: unit · `tests/test_migrate.py` · `test_storage_migrate_001_the_dry_run_reports_everything_and_writes_nothing`
- Given: two indexes, `direct` and `proxy`, sharing one final folder, holding a nested completed
  record whose entry is free and whose hash folder also holds Finder metadata, one whose entry
  already exists with identical content, one whose entry exists with different content and whose
  hash folder also holds a file of the user's, one still in the staging folder; plus the identity
  marker in the final folder
- When: `python -m app.migrate` is run
- Then: it exits zero, its report names the relocation and its destination, the adoption, the
  suffix `(2)`, the shells it would remove, the Finder metadata it would clear from one and the
  user's file that keeps another; it does not name the staging record; and on disk every file, both
  indexes and the identity marker are unchanged
- When: the data folder's `app.lock` is held by another process and the command is run again
- Then: it exits non-zero, says the service is running, and still changes nothing
- When: the lock is released, a record is marked mid-move with a journal, and the command is run
- Then: it exits non-zero, names that torrent, and still changes nothing

## STORAGE-MIGRATE-002 — Applying the migration relocates by rename, verifies, and can be re-run

The relocation is a rename inside one root: no byte is copied, and the modification times that
fast-resume compares are preserved, so the torrents seed again without a full recheck. Each record
is journalled before its files move and verified after, and the index is rewritten once that record
is verified, so an interruption leaves one torrent to finish rather than a library to rebuild.
Running the command again finishes what was started and then has nothing left to do.

Implement: `apply` in `app/migrate.py`, run as `python -m app.migrate --apply`, journalling through
`<state>/flat-migration.json` and rewriting each index with `write_json` from `app/storage.py`.

Test: unit · `tests/test_migrate.py` · `test_storage_migrate_002_apply_relocates_verifies_and_resumes`
- Given: the indexes and folders of STORAGE-MIGRATE-001
- When: `python -m app.migrate --apply` is run
- Then: it exits zero; each relocated torrent's files are readable at `<final>/<entry>` with their
  original bytes and modification times; the adopted torrent points at the copy already there, which
  is untouched, and its nested duplicate is kept — deleting a copy nothing has hash-checked is the
  user's call, not an offline batch's; the suffixed torrent is at `<final>/<entry> (2)` with the
  pre-existing entry unchanged; each migrated record reads `layout` `flat` with `path` equal to the
  final folder; the staging record is untouched; the emptied hash folders and their now-empty mode
  folder are gone, while a hash folder still holding something other than Finder metadata is
  reported and kept, and so is its mode folder; the identity marker is still there;
  `index.before-flat.json` holds each index as it was; and `flat-migration.json` is empty
- When: the command is run again with `--apply`
- Then: it exits zero, reports nothing left to migrate, and changes nothing
- Given: the same starting state, with the index write made to raise after the first record's files
  were renamed
- When: `python -m app.migrate --apply` is run, fails, and is then run again
- Then: the second run resolves that record from the side actually holding its files, and every
  torrent ends with `layout` `flat` and its files at `<final>/<entry>`
