## LID-SERVICE-001 — Install and start LID as a system service

Implement: `install-service.sh`, run from a LID checkout on a Linux host to install and start `lid.service` with systemd.

Test: unit · `tests/test_service_installer.py` · `test_lid_service_001_installs_and_enables_systemd_unit`
- Given: a LID checkout, a writable systemd unit directory, a selected service user and a recording `systemctl` executable
- When: `install-service.sh` is executed
- Then: it writes `lid.service` with the checkout as `WorkingDirectory`, `run.sh` as `ExecStart`, the selected user, restart-on-failure behavior and the multi-user startup target
- Then: it runs `systemctl daemon-reload`, `systemctl enable --now lid.service`, and verifies that the service is active and enabled

## LID-SERVICE-002 — Install LID in the user systemd manager

Implement: `install-service.sh --user`, run from a LID checkout when the service account has systemd lingering enabled.

Test: unit · `tests/test_service_installer.py` · `test_lid_service_002_installs_user_systemd_unit`
- Given: a LID checkout, an isolated home directory, a selected service user and a recording `systemctl` executable
- When: `install-service.sh --user` is executed
- Then: it writes `~/.config/systemd/user/lid.service` for the checkout without a system-level `User` directive and enables it through `default.target`
- Then: it reloads, starts, verifies and enables the service through `systemctl --user`
