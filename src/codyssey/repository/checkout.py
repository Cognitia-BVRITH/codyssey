"""Clone into a new destination without modifying the source repository."""

import re
import subprocess
from pathlib import Path


def checkout(source: str, commit: str, destination: Path, timeout: float = 120) -> Path:
    """Create a detached checkout of an exact commit; destination must not exist.

    Source is a trusted task input, not a candidate-supplied URL. Partial clones
    are left in the caller's disposable directory if Git fails.
    """
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("An exact 40-character Git commit is required")
    if not source or source.startswith("-"):
        raise ValueError("Invalid repository source")
    if destination.exists():
        raise FileExistsError(destination)
    subprocess.run(
        ["git", "clone", "--no-local", "--no-checkout", "--", source, str(destination)],
        check=True,
        capture_output=True,
        timeout=timeout,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--detach", commit],
        check=True,
        capture_output=True,
        timeout=timeout,
    )
    return destination
