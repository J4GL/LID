# LID specifications

- [Service installation](service/systemd.md)
- [Service upgrade](service/upgrade.md)
- [Server binding](server/bind.md)
- [Interrupted move recovery](storage/interrupted-move.md)
- [Seeding last-upload](seeding/last-upload.md)
- [Seeding auto-remove](seeding/auto-remove.md)

Run the service installer specifications with:

```sh
.venv/bin/python -m pytest tests/test_service_installer.py -q
.venv/bin/python -m pytest tests/test_upgrade.py -q
.venv/bin/python -m pytest tests/test_server_binding.py -q
.venv/bin/python -m pytest tests/test_moves.py -q
.venv/bin/python -m pytest tests/test_seeding.py -q
node --test tests/timeago.test.mjs
```
