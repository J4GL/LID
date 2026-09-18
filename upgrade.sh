#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$PROJECT_DIR"

GIT="${LID_GIT:-git}"
SYSTEMCTL="${LID_SYSTEMCTL:-systemctl}"
PLATFORM="${LID_PLATFORM:-$(uname -s)}"
SYSTEM_UNIT_DIR="${LID_SYSTEMD_SYSTEM_DIR:-/etc/systemd/system}"
USER_UNIT_DIR="${LID_SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
MODE=""

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [--user]" >&2
  exit 2
fi
if [[ ${1:-} == "--user" ]]; then
  MODE="user"
elif [[ $# -eq 1 ]]; then
  echo "Usage: $0 [--user]" >&2
  exit 2
fi

if [[ "$PLATFORM" != "Linux" ]]; then
  echo "ERROR: the LID upgrade script supports Linux with systemd." >&2
  exit 1
fi

if ! command -v "$SYSTEMCTL" >/dev/null 2>&1; then
  echo "ERROR: systemctl is required to restart the LID service." >&2
  exit 1
fi

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  echo "ERROR: $PROJECT_DIR is not a git checkout." >&2
  exit 1
fi

if [[ -z "$MODE" ]]; then
  if [[ -f "$SYSTEM_UNIT_DIR/lid.service" ]]; then
    MODE="system"
  elif [[ -f "$USER_UNIT_DIR/lid.service" ]]; then
    MODE="user"
  else
    echo "ERROR: no LID systemd unit found. Run install-service.sh first." >&2
    exit 1
  fi
fi

run_systemctl() {
  if [[ "$MODE" == "user" ]]; then
    "$SYSTEMCTL" --user "$@"
  elif [[ "$SYSTEM_UNIT_DIR" == "/etc/systemd/system" && "$EUID" -ne 0 ]]; then
    sudo "$SYSTEMCTL" "$@"
  else
    "$SYSTEMCTL" "$@"
  fi
}

BRANCH="$("$GIT" rev-parse --abbrev-ref HEAD)"
BEFORE="$("$GIT" rev-parse HEAD)"

"$GIT" fetch origin "$BRANCH"

if ! "$GIT" merge --ff-only "origin/$BRANCH"; then
  echo "ERROR: local checkout has diverged from origin/$BRANCH; resolve manually before upgrading. No data was touched." >&2
  exit 1
fi

AFTER="$("$GIT" rev-parse HEAD)"

service_running() {
  run_systemctl is-active --quiet lid.service
}

# A restart interrupts whatever the engine is doing, a move in flight included,
# so nothing new from GitHub means nothing to restart.
if [[ "$AFTER" == "$BEFORE" ]]; then
  echo "LID is already up to date ($AFTER); the service was left alone."
  if ! service_running; then
    echo "lid.service was not running: starting it." >&2
    run_systemctl start lid.service
  fi
  exit 0
fi

echo "LID updated from $BEFORE to $AFTER."

# Stopping the engine flushes to disk, so the restart below is silent for a
# while. An upgrade cut short there must still leave the dashboard running:
# start unconditionally, since a stop already in flight can outlive the check.
restore_service() {
  echo "Interrupted: making sure lid.service is running." >&2
  run_systemctl start lid.service || true
  exit 130
}
trap restore_service INT TERM HUP

echo "Restarting lid.service (stopping the engine can take a minute)…"
run_systemctl daemon-reload
if ! run_systemctl restart lid.service; then
  echo "WARNING: restart failed; starting lid.service instead." >&2
  run_systemctl start lid.service || true
fi
if ! service_running; then
  run_systemctl start lid.service || true
  if ! service_running; then
    echo "ERROR: lid.service is not running after the upgrade." >&2
    if [[ "$MODE" == "user" ]]; then
      echo "Check: systemctl --user status lid.service" >&2
    else
      echo "Check: systemctl status lid.service" >&2
    fi
    exit 1
  fi
fi
trap - INT TERM HUP

echo "LID $MODE service restarted with the latest version."
if [[ "$MODE" == "user" ]]; then
  echo "Status: systemctl --user status lid.service"
  echo "Logs:   journalctl --user -u lid.service -f"
else
  echo "Status: systemctl status lid.service"
  echo "Logs:   journalctl -u lid.service -f"
fi
