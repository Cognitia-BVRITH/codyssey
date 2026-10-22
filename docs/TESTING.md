# Testing and verification

## Controller checks

After installing `.[dev]`, run:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Default pytest collection includes `tests/unit/` and `tests/integration/`.
The initial unit suite checks task constraints and basic CLI behavior. No sandbox
integration tests exist yet. CI runs controller checks on Python 3.11 and 3.12.

## Deliberately failing target

Run this separately from controller checks:

```bash
python -m pytest tests/fixtures/boundary -q --import-mode=prepend
```

Expect one failing boundary test and two passing regression tests. Preserve this
baseline in Git. A repair experiment copies the target to a disposable location,
changes the faulty comparison, and expects all three tests to pass there.

## Required future integration checks

- Confirm an exact base commit reproduces the expected failure.
- Accept a supplied valid patch and reject malformed, unsafe, or inapplicable patches.
- Require every designated failing and regression test to execute and pass.
- Reject missing results, collection failures, and skipped required tests.
- Preserve evaluation tests and discard candidate state between attempts.
- Stop test processes on deadlines/cancellation and remove containers afterward.
- Record infrastructure failures separately from unsuccessful repair attempts.

Use fake provider responses for deterministic CI checks. Keep live-provider and
Docker-dependent experiments explicit, with their setup documented. Public pull
request checks should not need API keys.
