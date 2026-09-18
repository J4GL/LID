## STORAGE-RESUME-001 — A completed torrent whose files are missing is never resumed

Attaching a torrent hands libtorrent a save path and resumes it. While every path carried an
infohash it was derived, deterministic and unique, so a wrong one was barely reachable. A shared
final folder makes it reachable: a migration cut short, a stale recorded layout or a changed root
all end at a save path holding nothing, where libtorrent rechecks to zero and starts downloading
the library again. A torrent that was complete therefore has to find its files before it is allowed
to run.

Implement: the payload check in `Engine.attach` in `app/engine.py`, using
`CompletionMoves.complete_files` in `app/moves.py` against the file list of the torrent being
attached. Reached from `Engine.restore` on start-up, from `Engine.add`, and from the `retry-move`
action.
Out of scope: a torrent that has never completed, which legitimately starts from nothing; a
partially complete torrent, whose missing pieces are what it is downloading.

Test: unit · `tests/test_moves.py` · `test_storage_resume_001_a_completed_torrent_with_missing_files_is_not_resumed`
- Given: a torrent that reached phase `done` in the final folder, with its recorded path rewritten
  in the index to a folder holding none of its files
- When: the engine is restarted and ticked
- Then: the torrent is paused with a download rate of zero, its record carries an error naming the
  missing payload, and the folder it points at is still empty
- When: the files are put back at the recorded path and the engine is restarted
- Then: the torrent seeds again with no error
