# Person 1: supplied-patch validation

Repository preparation and supplied-patch validation are available as a Python
API. Repair generation, run persistence, and CLI integration remain separate.

```python
from pathlib import Path
from codyssey.contracts import Task, PatchCandidate
from codyssey.sandbox.docker import DockerExecutor
from codyssey.sandbox.validator import Validator

task = Task.model_validate_json(Path("task.json").read_text(encoding="utf-8"))
validator = Validator(DockerExecutor(timeout_seconds=120))
baseline = validator.validate(task, Path("data/example/baseline"))
if baseline.status != "reproduced":
    raise RuntimeError(baseline.reason)
candidate = PatchCandidate(
    diff=Path("fix.diff").read_text(encoding="utf-8"),
    method="deterministic",
    touched_paths=["voting.py"],
)
result = validator.validate(task, Path("data/example/attempt-1"), candidate)
print(result.status, result.reason)
```

Each call requires a new artifact directory, clones the trusted task source at an
exact commit, and deletes its temporary checkout afterward. The caller must
accept baseline reproduction before submitting candidates. No attempt state is
reused and the source repository is unchanged. Git is required on the controller.

Baseline evidence requires every designated failing test to fail and every
regression test to pass. Candidate verification requires all to pass. Exit codes,
missing/duplicate identities, incorrect groups, skipped tests, collection errors,
and timeouts prevent acceptance. JUnit classname/name pairs map to required pytest
node IDs; unexpected or ambiguous identities fail closed. Custom node-ID plugins
and nonstandard JUnit formats are outside the initial adapter.

Patch checks compare actual Git diff paths with candidate metadata, check
applicability, and reject tests/configuration, hidden paths, traversal, symlinks,
binary patches, additions/deletions, renames, and mode changes. Only existing
source files can be edited. This path policy does not prove semantic correctness.

The Docker CLI executor requires a Linux daemon and a prepared image containing
Python and pytest. It accepts only `['python', '-m', 'pytest']` or `['pytest']`,
clears project `addopts`, and explicitly selects required test identities.
Containers have no network, UID/GID 65534, a read-only root and input mount,
no capabilities, no-new-privileges, 2 CPUs, 2 GiB RAM, 128 processes, and a 512 MiB
temporary workspace. Images are never pulled at execution time. Only the new
evidence directory is writable from the host; its permissions are opened to the
container user. Keep secrets and existing artifacts out of that directory.
Docker logs rotate at 1 MiB; raw console logs are not yet exported.

Timed-out containers are killed and containers are force-removed in `finally`.
Startup/cleanup failures produce infrastructure errors. The test timeout excludes
checkout and cleanup, which have separate timeouts. External cancellation, a
total-run deadline, bounded JUnit size, persisted reports, submodules,
evaluator-test installation, benchmark adapters, and crash recovery remain
Person 1/integration work. This is not the complete week-2 milestone.

## Checks

Default integration tests create a temporary Git repository and execute only the
trusted voting fixture locally. They check baseline reproduction, correct and
incorrect patches, rejection policy, clean attempts, and unchanged source.
Production execution uses Docker. To opt into its integration test in PowerShell:

```powershell
docker build -t codyssey-fixture:local tests/fixtures/boundary
$env:CODYSSEY_TEST_IMAGE = 'codyssey-fixture:local'
python -m pytest tests/integration/test_validator.py -q
```

Building the image downloads dependencies separately from isolated execution.
Without the environment variable, the Docker integration test is skipped.
The dedicated `docker-validation` CI job builds the fixture image and enables it.
Docker was unavailable on the development machine; container execution remains
unverified locally. The repository and evidence flow was checked using the trusted
fixture executor.
