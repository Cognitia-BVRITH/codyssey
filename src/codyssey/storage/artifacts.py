"""Write-once artifact files under one root: prompts, responses, patches, test evidence.

Layout (relative to the artifact root)::

    <run_id>/config.json
    <run_id>/baseline/                  # evidence directory created by the validator
    <run_id>/attempt<N>/patch.diff      # plus prompt.txt / response.txt from repair code
    <run_id>/attempt<N>/evidence/       # evidence directory created by the validator
    <run_id>/final_patch.diff           # only written for verified runs

The database stores paths relative to the root so exported records stay portable.
"""

import re
from pathlib import Path, PurePosixPath

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.match(run_id) or ".." in run_id:
            raise ValueError(f"Unsafe run id: {run_id!r}")
        return self.root / run_id

    def baseline_dir(self, run_id: str) -> Path:
        """Path for baseline evidence; not created here because the validator requires new."""
        return self.run_dir(run_id) / "baseline"

    def attempt_dir(self, run_id: str, number: int) -> Path:
        if number < 1:
            raise ValueError("Attempt numbers start at 1")
        return self.run_dir(run_id) / f"attempt{number}"

    def evidence_dir(self, run_id: str, number: int) -> Path:
        """Path for attempt evidence; not created here because the validator requires new."""
        return self.attempt_dir(run_id, number) / "evidence"

    def write_text(self, run_id: str, relative: str, text: str) -> str:
        """Create a new file under a run; refuses to overwrite. Returns the root-relative path."""
        parts = PurePosixPath(relative).parts
        if not parts or PurePosixPath(relative).is_absolute() or ".." in parts or "\\" in relative:
            raise ValueError(f"Unsafe artifact path: {relative!r}")
        target = self.run_dir(run_id).joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return target.relative_to(self.root).as_posix()

    def write_config(self, run_id: str, config_json: str) -> str:
        return self.write_text(run_id, "config.json", config_json)

    def write_patch(self, run_id: str, number: int, diff: str) -> str:
        return self.write_text(run_id, f"attempt{number}/patch.diff", diff)

    def write_final_patch(self, run_id: str, diff: str) -> str:
        return self.write_text(run_id, "final_patch.diff", diff)

    def final_patch_path(self, run_id: str) -> Path | None:
        path = self.run_dir(run_id) / "final_patch.diff"
        return path if path.is_file() else None

    def read_text(self, relative_to_root: str) -> str:
        """Read a recorded artifact path; rejects anything that resolves outside the root."""
        target = (self.root / relative_to_root).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"Path escapes artifact root: {relative_to_root!r}")
        return target.read_text(encoding="utf-8")
