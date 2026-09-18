## STORAGE-MOVE-001 — An interrupted move recovers from the side holding a complete copy

A move copies files to the destination before removing them from the source, so an interruption
normally leaves a complete copy on one side and a partial copy on the other. Recovery keeps the
complete side, and the partial copy on the other side holds no unique data: it is discarded once
libtorrent has hash-checked the kept copy, so the move can run again instead of stalling on a
destination that looks occupied.

Implement: `CompletionMoves.prepare_restore` and the `torrent_checked_alert` branch of
`CompletionMoves.alert` in `app/moves.py`, reached from `Engine.restore` on start-up and from the
`retry-move` action handled in `app/engine.py`.
Out of scope: an interruption that leaves neither side complete, which stays a manual recovery
(`tests/test_moves.py::test_interrupted_move_recovery_never_downloads_missing_data[split]`);
deleting anything outside the interrupted move's own journal file list.

Test: unit · `tests/test_moves.py` · `test_storage_move_001_recovers_from_the_complete_side_and_discards_the_stale_copy`
- Given: a seeding multi-file torrent whose journal records an interrupted move, a complete copy of
  every journal file in the source folder, and a stale partial copy in the destination folder (one
  full file plus one truncated file)
- When: the engine is restarted and ticked
- Then: the torrent recovers from the source without downloading, the stale destination copy is
  discarded so the move can run again, and the move reaches phase `done` with every file complete
  in the destination, the torrent seeding and no torrent file left in the source folder

- Given: the same torrent, but with the complete copy in the destination folder and a stale
  leftover file in the source folder
- When: the engine is restarted and ticked
- Then: the torrent recovers from the destination without downloading, the stale source file is
  discarded, and the move reaches phase `done` with every file complete in the destination, the
  torrent seeding and no torrent file left in the source folder
