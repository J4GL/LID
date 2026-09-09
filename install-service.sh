#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
UNIT_DIR="${LID_SYSTEMD_DIR:-/etc/systemd/system}"
SYSTEMCTL="${LID_SYSTEMCTL:-systemctl}"
SERVICE_USER="${LID_SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
UNIT_PATH="$UNIT_DIR/lid.service"
PLATFORM="${LID_PLATFORM:-$(uname -s)}"

if [[ "$PLATFORM" != "Linux" ]]; then
  echo "ERROR: the LID service installer supports Linux with systemd." >&2
  exit 1
fi

if ! command -v "$SYSTEMCTL" >/dev/null 2>&1; then
  echo "ERROR: systemctl is required to install the LID service." >&2
  exit 1
fi

if [[ "$UNIT_DIR" == "/etc/systemd/system" && "$EUID" -ne 0 ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: run this installer as root." >&2
    exit 1
  fi
  export LID_SERVICE_USER="$SERVICE_USER"
  exec sudo --preserve-env=LID_SERVICE_USER "$0" "$@"
fi

if [[ "$UNIT_DIR" == "/etc/systemd/system" ]] && ! id "$SERVICE_USER" >/dev/null 2>&1; then
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
User=$SERVICE_USER
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

"$SYSTEMCTL" daemon-reload
"$SYSTEMCTL" enable --now lid.service
"$SYSTEMCTL" is-active --quiet lid.service
"$SYSTEMCTL" is-enabled --quiet lid.service

echo "LID service installed and running as $SERVICE_USER."
echo "Status: systemctl status lid.service"
echo "Logs:   journalctl -u lid.service -f"
