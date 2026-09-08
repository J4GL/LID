#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$PROJECT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  PYTHON_BIN=""
  for candidate in "$PROJECT_DIR/.runtime/bin/python3.12" python3.12; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
  if [[ -z "$PYTHON_BIN" ]] && command -v uv >/dev/null 2>&1; then
    export UV_CACHE_DIR="$PROJECT_DIR/.cache/uv"
    export UV_PYTHON_INSTALL_DIR="$PROJECT_DIR/.runtime/python"
    export UV_PYTHON_BIN_DIR="$PROJECT_DIR/.runtime/bin"
    uv python install 3.12
    PYTHON_BIN="$PROJECT_DIR/.runtime/bin/python3.12"
  fi
  if [[ -z "$PYTHON_BIN" ]]; then
    if [[ "$(uname -s)" == Darwin ]]; then
      echo "ERREUR : Python 3.12 manque. Installez-le avec : brew install python@3.12" >&2
    else
      echo "ERREUR : Python 3.12 manque. Sur Ubuntu 24.04 : sudo apt install python3.12 python3.12-venv" >&2
      echo "Sur Debian, installez uv (https://docs.astral.sh/uv/getting-started/installation/), puis relancez ./run.sh." >&2
    fi
    exit 1
  fi
  "$PYTHON_BIN" -m venv .venv
fi

if ! .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
  echo "ERREUR : .venv utilise une autre version de Python. Renommez .venv puis relancez ./run.sh." >&2
  exit 1
fi

if ! .venv/bin/python - <<'PY'
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
try:
    for line in Path('requirements.lock').read_text().splitlines():
        if line and not line.startswith('#'):
            name, expected = line.split('==')
            if version(name) != expected:
                raise PackageNotFoundError(name)
    import libtorrent
except (ImportError, PackageNotFoundError):
    raise SystemExit(1)
PY
then
  echo "Installation des dépendances dans .venv…"
  if ! .venv/bin/python -m pip install --disable-pip-version-check --only-binary=libtorrent -r requirements.lock; then
    echo "ERREUR : installation impossible. Vérifiez le réseau et la disponibilité d'une distribution binaire libtorrent 2.1.1 pour Python 3.12 sur votre système." >&2
    exit 1
  fi
fi

exec .venv/bin/python -m app.launch "$@"
