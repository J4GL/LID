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

if [[ "$AFTER" == "$BEFORE" ]]; then
  echo "LID is already up to date ($AFTER)."
else
  echo "LID updated from $BEFORE to $AFTER."
fi

run_systemctl daemon-reload
run_systemctl restart lid.service
run_systemctl is-active --quiet lid.service

echo "LID $MODE service restarted with the latest version."
if [[ "$MODE" == "user" ]]; then
  echo "Status: systemctl --user status lid.service"
  echo "Logs:   journalctl --user -u lid.service -f"
else
  echo "Status: systemctl status lid.service"
  echo "Logs:   journalctl -u lid.service -f"
fi
