# Integration checks

`test_validator.py` checks repository checkout and supplied-patch validation with
the trusted local fixture. Set `CODYSSEY_TEST_IMAGE` to run its Docker test; see
[validation instructions](../../docs/VALIDATION.md).

Further tests are needed for cancellation and benchmark setup.
Tests should cover baseline reproduction, supplied-patch validation, attempt
isolation, deadlines, cancellation, and cleanup.

The deliberately failing target under `tests/fixtures/` is input data, not an
integration test. Docker-dependent checks must be explicitly marked and run on
a Docker-capable runner. The Docker test is skipped by default.
