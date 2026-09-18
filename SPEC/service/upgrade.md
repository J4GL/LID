## LID-SERVICE-003 — Upgrade LID from GitHub and restart the system service

Implement: `upgrade.sh`, run from a LID checkout on a Linux host to fast-forward the checkout to
the latest commit on the tracked branch's `origin` remote and restart the already-installed
system-mode `lid.service`.
Uses: [Service installation](systemd.md)
Out of scope: installing the service for the first time; upgrading dependencies (already handled
by `run.sh` on service start)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_003_upgrades_checkout_and_restarts_system_service`
- Given: a LID checkout cloned from an `origin` with a new commit pushed ahead of the checkout,
  untracked `data/` and `downloads/` files holding local user data, an installed system-mode
  `lid.service` unit and a recording `systemctl` executable
- When: `upgrade.sh` is executed
- Then: the checkout's tracked files are fast-forwarded to the new `origin` commit
- Then: the untracked `data/` and `downloads/` files still exist with unchanged contents
- Then: it runs `systemctl daemon-reload`, `systemctl restart lid.service` and verifies the
  service is active

## LID-SERVICE-004 — Upgrade LID and restart the user service

Implement: `upgrade.sh`, auto-detecting a user-mode `lid.service` unit when no system-mode unit
is installed.
Uses: [Service installation](systemd.md)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_004_upgrades_checkout_and_restarts_user_service`
- Given: the same checkout setup as LID-SERVICE-003, but with only a user-mode `lid.service` unit
  installed
- When: `upgrade.sh` is executed
- Then: the checkout's tracked files are fast-forwarded to the new `origin` commit
- Then: it runs `systemctl --user daemon-reload`, `systemctl --user restart lid.service` and
  verifies the service is active through `systemctl --user`

## LID-SERVICE-005 — Upgrade aborts without touching data when the checkout has diverged

Implement: `upgrade.sh`, run from a LID checkout that has local commits not present on `origin`.
Uses: [Service installation](systemd.md)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_005_aborts_on_diverged_checkout`
- Given: a LID checkout with a local commit that is not on `origin`, while `origin` also has a
  new commit the checkout does not have, and a recording `systemctl` executable
- When: `upgrade.sh` is executed
- Then: it exits with a non-zero status and does not modify the checkout's tracked files
- Then: it does not invoke `systemctl restart` or `systemctl --user restart`
