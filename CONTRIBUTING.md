# Contributing to Codyssey

## Setup

Use Python 3.11 or newer. Docker is needed for the planned sandbox, but the
starter CLI and unit tests do not require it.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
codyssey --help
codyssey version
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead.
Example configuration files describe planned runtime settings. The starter CLI
does not load them or make provider requests. See [configuration](docs/CONFIGURATION.md).

## Working agreement

Follow the ownership and handoffs in [TEAM_DIVISION.md](TEAM_DIVISION.md).
Create a short feature branch and link its pull request to a scoped issue with
acceptance criteria. Review shared contract changes with both consuming members.
Keep source implementation, relevant tests, and its documentation together as
one logical change; split unrelated changes into separate commits.

Every individual logical change gets a single-line conventional commit message:

```text
feat(contracts): add validated task input
fix(sandbox): clean up timed-out containers
test(validator): reject missing regression results
docs(setup): explain local installation
ci: run unit checks on pull requests
```

Use an imperative description. Do not mix unrelated cleanup or generated repair
artifacts into a feature commit. Obtain at least one other member's review before
merging. The project has not selected a license; agree on one before representing
the repository as licensed for reuse.

## Checks

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

See [testing](docs/TESTING.md) for the intentionally failing fixture and future
sandbox checks. Keep API keys, local configuration, generated repositories,
database files, and prompt/test artifacts out of commits. Record implemented
behavior accurately; proposed components belong in the plan until delivered.
