# LID specifications

- [Service installation](service/systemd.md)
- [Service upgrade](service/upgrade.md)
- [Server binding](server/bind.md)
- [Static asset caching](server/static-cache.md)
- [Content-Security-Policy](server/csp.md)
- [Flat final folder](storage/flat-final.md)
- [Interrupted move recovery](storage/interrupted-move.md)
- [Resume guard](storage/resume-guard.md)
- [Flat layout migration](storage/migration.md)
- [Seeding last-upload](seeding/last-upload.md)
- [Seeding auto-remove](seeding/auto-remove.md)
- [Disk usage](storage/disk-usage.md)
- [Delete with files](storage/delete-with-files.md)
- [Compact view](dashboard/compact.md)
- [Extension capture](extension/capture.md)
- [Extension client](extension/client.md)
- [Extension worker](extension/worker.md)

Run the service installer specifications with:

```sh
.venv/bin/python -m pytest tests/test_service_installer.py -q
.venv/bin/python -m pytest tests/test_upgrade.py -q
.venv/bin/python -m pytest tests/test_server_binding.py -q
.venv/bin/python -m pytest tests/test_api.py -q
.venv/bin/python -m pytest tests/test_moves.py -q
.venv/bin/python -m pytest tests/test_migrate.py -q
.venv/bin/python -m pytest tests/test_seeding.py -q
.venv/bin/python -m pytest tests/test_disk_usage.py -q
.venv/bin/python -m pytest tests/test_remove_files.py -q
.venv/bin/python -m pytest tests/test_dashboard_compact.py -q
node --test tests/timeago.test.mjs
node --test tests/compact.test.mjs tests/i18n.test.mjs
node --test tests/extension-capture.test.mjs tests/extension-client.test.mjs tests/extension-worker.test.mjs
```

For the extension blob regression tests (proxy uploads only):

```sh
node --test --test-name-pattern='EXT-CAP-|EXT-SW-(00[2346789]|010)|EXT-CLI-00[234]' tests/extension-capture.test.mjs tests/extension-client.test.mjs tests/extension-worker.test.mjs
```

The dashboard e2e tests drive the real application with the
`obscura` headless browser (0.2.3 or later): it must be on
`PATH` (or set `OBSCURA=/path/to/obscura`); the tests fail when it is missing.
