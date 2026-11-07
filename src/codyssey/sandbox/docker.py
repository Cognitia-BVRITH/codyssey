"""Docker CLI executor for prepared Python/pytest images; no host test execution."""

import subprocess
import uuid
from pathlib import Path

from codyssey.contracts import Task, TestReport
from codyssey.sandbox.evidence import read_junit


class DockerExecutor:
    """Each invocation creates and destroys a container, including on timeout.

    Prepared images must provide Python and pytest. No dependencies are installed
    during execution. Mounts contain only the checkout and a new evidence directory.
    """

    def __init__(self, timeout_seconds: float = 120):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def run(self, task: Task, repository: Path, artifacts: Path) -> TestReport:
        if task.test_command not in (["python", "-m", "pytest"], ["pytest"]):
            raise ValueError("Initial executor supports only python -m pytest or pytest")
        if task.environment_image.startswith("-"):
            raise ValueError("Image must not be a Docker option")
        name = f"codyssey-{uuid.uuid4().hex}"
        artifacts.chmod(0o777)
        # Copy from the host mount into a container-only writable workspace.
        # The mount is read-only; the container never receives controller secrets.
        script = (
            "import shutil,subprocess,sys; "
            "shutil.copytree('/input','/tmp/work',ignore=shutil.ignore_patterns('.git')); "
            "r=subprocess.run(sys.argv[1:],cwd='/tmp/work'); sys.exit(r.returncode)"
        )
        command = [
            "docker",
            "run",
            "--pull=never",
            "--name",
            name,
            "--network",
            "none",
            "--user",
            "65534:65534",
            "--cpus",
            "2",
            "--memory",
            "2g",
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,size=512m,mode=1777",
            "--mount",
            f"type=bind,src={repository.resolve()},dst=/input,readonly",
            "--mount",
            f"type=bind,src={artifacts.resolve()},dst=/evidence",
            "--entrypoint",
            "python",
            task.environment_image,
            "-c",
            script,
            *task.test_command,
            "-o",
            "addopts=",
            "-o",
            "junit_family=xunit2",
            "--junitxml=/evidence/junit.xml",
            "--",
            *task.fail_to_pass,
            *task.pass_to_pass,
        ]
        # A bounded Docker log driver avoids unbounded daemon-side test output.
        command[2:2] = [
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=1m",
            "--log-opt",
            "max-file=1",
        ]
        timed_out = False
        try:
            try:
                result = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out, exit_code = True, -1
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
            evidence = artifacts / "junit.xml"
            return read_junit(evidence, task, exit_code, timed_out)
        finally:
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, timeout=30, check=True
            )
