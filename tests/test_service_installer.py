import os
from pathlib import Path
import subprocess


def test_lid_service_001_installs_and_enables_systemd_unit(tmp_path):
    project = Path(__file__).resolve().parents[1]
    unit_dir = tmp_path / "systemd"
    systemctl_log = tmp_path / "systemctl.log"
    systemctl = tmp_path / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$LID_SYSTEMCTL_LOG"\n'
    )
    systemctl.chmod(0o755)
    env = {
        **os.environ,
        "LID_SYSTEMD_DIR": str(unit_dir),
        "LID_SYSTEMCTL": str(systemctl),
        "LID_SYSTEMCTL_LOG": str(systemctl_log),
        "LID_SERVICE_USER": "lid-test-user",
        "LID_PLATFORM": "Linux",
    }

    result = subprocess.run(
        [str(project / "install-service.sh")],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    unit = (unit_dir / "lid.service").read_text()
    assert "Description=LID - Linux ISO Downloader" in unit
    assert "User=lid-test-user" in unit
    assert f'WorkingDirectory="{project}"' in unit
    assert f'ExecStart="{project / "run.sh"}"' in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=multi-user.target" in unit
    assert systemctl_log.read_text().splitlines() == [
        "daemon-reload",
        "enable --now lid.service",
        "is-active --quiet lid.service",
        "is-enabled --quiet lid.service",
    ]
