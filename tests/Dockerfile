FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tcpdump strace \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
COPY requirements.txt requirements.lock requirements-dev.txt run.sh config.yaml ./
COPY app ./app
RUN ./run.sh --check && .venv/bin/python -m pip install --disable-pip-version-check -r requirements-dev.txt
COPY tests ./tests
CMD [".venv/bin/python", "-m", "pytest", "tests", "-q", "--disable-warnings"]
