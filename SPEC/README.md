# LID specifications

- [Service installation](service/systemd.md)
- [Service upgrade](service/upgrade.md)
- [Server binding](server/bind.md)
- [Static asset caching](server/static-cache.md)
- [Flat final folder](storage/flat-final.md)
- [Interrupted move recovery](storage/interrupted-move.md)
- [Resume guard](storage/resume-guard.md)
- [Flat layout migration](storage/migration.md)
- [Seeding last-upload](seeding/last-upload.md)
- [Seeding auto-remove](seeding/auto-remove.md)
- [Disk usage](storage/disk-usage.md)
- [Delete with files](storage/delete-with-files.md)

Run the service installer specifications with:

```sh
.venv/bin/python -m pytest tests/test_service_installer.py -q
.venv/bin/python -m pytest tests/test_upgrade.py -q
.venv/bin/python -m pytest tests/test_server_binding.py -q
.venv/bin/python -m pytest tests/test_moves.py -q
.venv/bin/python -m pytest tests/test_migrate.py -q
.venv/bin/python -m pytest tests/test_seeding.py -q
.venv/bin/python -m pytest tests/test_disk_usage.py -q
.venv/bin/python -m pytest tests/test_remove_files.py -q
node --test tests/timeago.test.mjs
```
