import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _run_git(args, cwd):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


def _make_checkout(tmp_path, project):
    """Origin (bare) + a 'seed' clone that publishes commits + the checkout under test."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )

    seed = tmp_path / "seed"
    seed.mkdir()
    _run_git(["init", "-b", "main"], seed)
    _run_git(["config", "user.email", "test@example.com"], seed)
    _run_git(["config", "user.name", "Test"], seed)
    (seed / "README.txt").write_text("v1\n")
    (seed / ".gitignore").write_text("data/\ndownloads/\nconfig.yaml\n")
    _run_git(["add", "."], seed)
    _run_git(["commit", "-m", "initial"], seed)
    _run_git(["remote", "add", "origin", str(origin)], seed)
    _run_git(["push", "origin", "main"], seed)

    checkout = tmp_path / "checkout"
    _run_git(["clone", str(origin), str(checkout)], tmp_path)
    _run_git(["config", "user.email", "test@example.com"], checkout)
    _run_git(["config", "user.name", "Test"], checkout)

    shutil.copy(project / "upgrade.sh", checkout / "upgrade.sh")
    os.chmod(checkout / "upgrade.sh", 0o755)

    data_dir = checkout / "data"
    data_dir.mkdir()
    (data_dir / "state.db").write_text("important-data")
    downloads_dir = checkout / "downloads"
    downloads_dir.mkdir()
    (downloads_dir / "movie.iso").write_bytes(b"binary-data")

    return origin, seed, checkout


def _fake_systemctl(tmp_path):
    systemctl_log = tmp_path / "systemctl.log"
    systemctl = tmp_path / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n" 'printf "%s\\n" "$*" >> "$LID_SYSTEMCTL_LOG"\n'
    )
    systemctl.chmod(0o755)
    return systemctl, systemctl_log


def test_lid_service_003_upgrades_checkout_and_restarts_system_service(tmp_path):
    project = Path(__file__).resolve().parents[1]
    origin, seed, checkout = _make_checkout(tmp_path, project)
    systemctl, systemctl_log = _fake_systemctl(tmp_path)

    (seed / "README.txt").write_text("v2\n")
    _run_git(["commit", "-am", "v2"], seed)
    _run_git(["push", "origin", "main"], seed)

    system_unit_dir = tmp_path / "system-systemd"
    system_unit_dir.mkdir()
    (system_unit_dir / "lid.service").write_text("[Unit]\n")

    env = {
        **os.environ,
        "LID_SYSTEMCTL": str(systemctl),
        "LID_SYSTEMCTL_LOG": str(systemctl_log),
        "LID_PLATFORM": "Linux",
        "LID_SYSTEMD_SYSTEM_DIR": str(system_unit_dir),
        "LID_SYSTEMD_USER_DIR": str(tmp_path / "no-user-systemd"),
    }

    result = subprocess.run(
        [str(checkout / "upgrade.sh")],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert (checkout / "README.txt").read_text() == "v2\n"
    assert (checkout / "data" / "state.db").read_text() == "important-data"
    assert (checkout / "downloads" / "movie.iso").read_bytes() == b"binary-data"
    assert systemctl_log.read_text().splitlines() == [
        "daemon-reload",
        "restart lid.service",
        "is-active --quiet lid.service",
    ]


def test_lid_service_004_upgrades_checkout_and_restarts_user_service(tmp_path):
    project = Path(__file__).resolve().parents[1]
    origin, seed, checkout = _make_checkout(tmp_path, project)
    systemctl, systemctl_log = _fake_systemctl(tmp_path)

    (seed / "README.txt").write_text("v2\n")
    _run_git(["commit", "-am", "v2"], seed)
    _run_git(["push", "origin", "main"], seed)

    user_unit_dir = tmp_path / "user-systemd"
    user_unit_dir.mkdir()
    (user_unit_dir / "lid.service").write_text("[Unit]\n")

    env = {
        **os.environ,
        "LID_SYSTEMCTL": str(systemctl),
        "LID_SYSTEMCTL_LOG": str(systemctl_log),
        "LID_PLATFORM": "Linux",
        "LID_SYSTEMD_SYSTEM_DIR": str(tmp_path / "no-system-systemd"),
        "LID_SYSTEMD_USER_DIR": str(user_unit_dir),
    }

    result = subprocess.run(
        [str(checkout / "upgrade.sh")],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert (checkout / "README.txt").read_text() == "v2\n"
    assert systemctl_log.read_text().splitlines() == [
        "--user daemon-reload",
        "--user restart lid.service",
        "--user is-active --quiet lid.service",
    ]


def test_lid_service_005_aborts_on_diverged_checkout(tmp_path):
    project = Path(__file__).resolve().parents[1]
    origin, seed, checkout = _make_checkout(tmp_path, project)
    systemctl, systemctl_log = _fake_systemctl(tmp_path)

    (seed / "README.txt").write_text("v2-from-origin\n")
    _run_git(["commit", "-am", "v2-from-origin"], seed)
    _run_git(["push", "origin", "main"], seed)

    (checkout / "README.txt").write_text("local-edit\n")
    _run_git(["commit", "-am", "local-edit"], checkout)

    system_unit_dir = tmp_path / "system-systemd"
    system_unit_dir.mkdir()
    (system_unit_dir / "lid.service").write_text("[Unit]\n")

    env = {
        **os.environ,
        "LID_SYSTEMCTL": str(systemctl),
        "LID_SYSTEMCTL_LOG": str(systemctl_log),
        "LID_PLATFORM": "Linux",
        "LID_SYSTEMD_SYSTEM_DIR": str(system_unit_dir),
        "LID_SYSTEMD_USER_DIR": str(tmp_path / "no-user-systemd"),
    }

    result = subprocess.run(
        [str(checkout / "upgrade.sh")],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert (checkout / "README.txt").read_text() == "local-edit\n"
    log_lines = (
        systemctl_log.read_text().splitlines() if systemctl_log.exists() else []
    )
    assert not any("restart" in line for line in log_lines)
