import subprocess
from types import SimpleNamespace

import pytest

from codyssey.sandbox.docker import DockerExecutor


@pytest.mark.parametrize("times_out", [False, True])
def test_container_limits_and_cleanup(monkeypatch, tmp_path, times_out):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1] == "run" and times_out:
            raise subprocess.TimeoutExpired(command, 1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    task = SimpleNamespace(
        test_command=["python", "-m", "pytest"],
        environment_image="fixture",
        fail_to_pass=["test_a.py::test_a"],
        pass_to_pass=["test_a.py::test_b"],
    )
    report = DockerExecutor(1).run(task, tmp_path, tmp_path)
    command = calls[0]
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--user") + 1] == "65534:65534"
    assert "--read-only" in command
    assert "--pull=never" in command
    assert "--pids-limit" in command
    assert calls[-1][:3] == ["docker", "rm", "--force"]
    assert report.timed_out == times_out
    assert report.collection_errors  # A successful process without evidence cannot verify.
    if times_out:
        assert calls[1][:2] == ["docker", "kill"]
