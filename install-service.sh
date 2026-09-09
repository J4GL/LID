#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SYSTEMCTL="${LID_SYSTEMCTL:-systemctl}"
SERVICE_USER="${LID_SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
PLATFORM="${LID_PLATFORM:-$(uname -s)}"
MODE="system"

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

if [[ "$MODE" == "user" ]]; then
  UNIT_DIR="${LID_SYSTEMD_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
  USER_DIRECTIVE=""
else
  UNIT_DIR="${LID_SYSTEMD_DIR:-/etc/systemd/system}"
  USER_DIRECTIVE="User=$SERVICE_USER"
fi
UNIT_PATH="$UNIT_DIR/lid.service"

if [[ "$PLATFORM" != "Linux" ]]; then
  echo "ERROR: the LID service installer supports Linux with systemd." >&2
  exit 1
fi

if ! command -v "$SYSTEMCTL" >/dev/null 2>&1; then
  echo "ERROR: systemctl is required to install the LID service." >&2
  exit 1
fi

if [[ "$MODE" == "system" && "$UNIT_DIR" == "/etc/systemd/system" && "$EUID" -ne 0 ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: run this installer as root." >&2
    exit 1
  fi
  export LID_SERVICE_USER="$SERVICE_USER"
  exec sudo --preserve-env=LID_SERVICE_USER "$0" "$@"
fi

if [[ "$MODE" == "system" && "$UNIT_DIR" == "/etc/systemd/system" ]] && ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "ERROR: service user '$SERVICE_USER' does not exist." >&2
  exit 1
fi

mkdir -p "$UNIT_DIR"
TEMP_UNIT="$UNIT_PATH.tmp.$$"
trap 'rm -f "$TEMP_UNIT"' EXIT

cat >"$TEMP_UNIT" <<EOF
[Unit]
Description=LID - Linux ISO Downloader
Wants=network-online.target
After=network-online.target local-fs.target

[Service]
Type=simple
$USER_DIRECTIVE
WorkingDirectory="$PROJECT_DIR"
ExecStart="$PROJECT_DIR/run.sh"
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "$TEMP_UNIT"
mv "$TEMP_UNIT" "$UNIT_PATH"
trap - EXIT

run_systemctl() {
  if [[ "$MODE" == "user" ]]; then
    "$SYSTEMCTL" --user "$@"
  else
    "$SYSTEMCTL" "$@"
  fi
}

run_systemctl daemon-reload
run_systemctl enable --now lid.service
run_systemctl is-active --quiet lid.service
run_systemctl is-enabled --quiet lid.service

echo "LID $MODE service installed and running as $SERVICE_USER."
if [[ "$MODE" == "user" ]]; then
  echo "Status: systemctl --user status lid.service"
  echo "Logs:   journalctl --user -u lid.service -f"
else
  echo "Status: systemctl status lid.service"
  echo "Logs:   journalctl -u lid.service -f"
fi
