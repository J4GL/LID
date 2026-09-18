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

## LID-SERVICE-006 — An interrupted upgrade never leaves the service stopped

Stopping `lid.service` takes as long as the engine needs to flush, so `upgrade.sh` is silent for
a while during the restart. Interrupting it there must not leave the dashboard down.

Implement: `upgrade.sh`, restarting the service under a signal handler that starts it back.
Uses: [Service installation](systemd.md)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_006_interrupted_upgrade_leaves_the_service_running`
- Given: a LID checkout with an installed user-mode `lid.service` unit and a recording `systemctl`
  whose `restart` is slow
- When: `upgrade.sh` is interrupted with `SIGINT` while the restart is running
- Then: it exits non-zero after asking `systemctl` to start `lid.service` again

## LID-SERVICE-007 — An upgrade that leaves the service inactive fails loudly

Implement: `upgrade.sh`, verifying the service is active after the restart.
Uses: [Service installation](systemd.md)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_007_reports_a_service_that_stays_inactive`
- Given: a LID checkout with an installed user-mode `lid.service` unit and a recording `systemctl`
  that reports the service as inactive
- When: `upgrade.sh` is executed
- Then: it retries the start, exits non-zero and names `lid.service` on standard error instead of
  stopping silently

## LID-SERVICE-008 — An upgrade with nothing new never restarts the service

Restarting interrupts whatever the engine is doing, including a move in flight, so a checkout that
already matches `origin` is left alone. The service is only started when it is not running.

Implement: `upgrade.sh`, comparing the checkout's commit before and after the fast-forward.
Uses: [Service installation](systemd.md)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_008_up_to_date_checkout_is_not_restarted`
- Given: a checkout already at `origin`'s commit, an installed user-mode `lid.service` unit and a
  recording `systemctl` reporting the service as active
- When: `upgrade.sh` is executed
- Then: it exits zero reporting the checkout is up to date, and asks `systemctl` only whether the
  service is active, without a `daemon-reload` or a `restart`

- Given: the same checkout, with a recording `systemctl` reporting the service as inactive
- When: `upgrade.sh` is executed
- Then: it exits zero after starting `lid.service`, without a `restart`

## LID-SERVICE-005 — Upgrade aborts without touching data when the checkout has diverged

Implement: `upgrade.sh`, run from a LID checkout that has local commits not present on `origin`.
Uses: [Service installation](systemd.md)

Test: unit · `tests/test_upgrade.py` · `test_lid_service_005_aborts_on_diverged_checkout`
- Given: a LID checkout with a local commit that is not on `origin`, while `origin` also has a
  new commit the checkout does not have, and a recording `systemctl` executable
- When: `upgrade.sh` is executed
- Then: it exits with a non-zero status and does not modify the checkout's tracked files
- Then: it does not invoke `systemctl restart` or `systemctl --user restart`
