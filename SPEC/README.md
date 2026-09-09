# LID specifications

- [Service installation](service/systemd.md)
- [Server binding](server/bind.md)

Run the service installer specifications with:

```sh
.venv/bin/python -m pytest tests/test_service_installer.py -q
.venv/bin/python -m pytest tests/test_server_binding.py -q
```
