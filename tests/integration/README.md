# Integration checks

Add tests here when repository checkout and sandbox execution are implemented.
Tests should cover baseline reproduction, supplied-patch validation, attempt
isolation, deadlines, cancellation, and cleanup.

The deliberately failing target under `tests/fixtures/` is input data, not an
integration test. Docker-dependent checks must be explicitly marked and run on
a Docker-capable runner. No Docker integration tests exist yet.
