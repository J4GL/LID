#!/bin/sh
set -eu
mkdir -p /work
cp -R /src/app /src/tests /src/run.sh /src/config.yaml /src/requirements.txt /src/requirements.lock /src/requirements-dev.txt /work/
cd /work
./run.sh --check
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-dev.txt >/tmp/p2p-test-install.log
.venv/bin/python -m pytest tests -q --disable-warnings
