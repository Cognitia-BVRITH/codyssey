# Boundary repair fixture

This target deliberately contains `age > 18` where the expected behavior is
`age >= 18`. It is excluded from the project's default pytest collection.

From the repository root, reproduce the bug explicitly:

```bash
python -m pytest tests/fixtures/boundary -q --import-mode=prepend
```

Expected baseline: one failure (`test_at_voting_age`) and two passes
(`test_below_voting_age`, `test_above_voting_age`). A nonzero exit is expected.
The correct boundary replacement should yield three passes.

Keep the checked-in target buggy. Apply experimental repairs only to a disposable
copy. This fixture does not yet provide a Docker image or benchmark task adapter.
