## LID-SERVER-001 — Expose the dashboard on the local network by default

Implement: the default `Server` configuration in `app/config.py`, the FastAPI middleware created by `app.main.create_app`, and the server-address field in the settings UI.

Test: e2e · `tests/test_server_binding.py` · `test_lid_server_001_defaults_to_lan_and_accepts_same_origin_requests`
- Given: LID running with its default configuration and a browser using `192.168.1.29:8000` as the host and origin
- When: the browser requests bootstrap, settings and readiness through the application routes
- Then: the requests are accepted, settings report `0.0.0.0` as the listen address, and readiness allows the matching LAN origin
