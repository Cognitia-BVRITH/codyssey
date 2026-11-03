import pytest
from pydantic import ValidationError

from codyssey.contracts import PatchCandidate, RepairOutcome, RepairUsage

# Example payloads other members can copy when building fakes.
DETERMINISTIC_EXAMPLE = {
    "diff": (
        "--- a/proj/voting.py\n"
        "+++ b/proj/voting.py\n"
        "@@ -2 +2 @@\n"
        "-    return age > 18\n"
        "+    return age >= 18\n"
    ),
    "method": "deterministic",
    "touched_paths": ["proj/voting.py"],
}

LLM_EXAMPLE = {
    "diff": (
        "--- a/proj/users.py\n"
        "+++ b/proj/users.py\n"
        "@@ -7 +7 @@\n"
        "-    name = data['username']\n"
        "+    name = data.get('username', '').strip()\n"
    ),
    "method": "llm",
    "touched_paths": ["proj/users.py"],
}


def test_deterministic_candidate_needs_no_token_usage() -> None:
    outcome = RepairOutcome(candidate=PatchCandidate(**DETERMINISTIC_EXAMPLE))

    assert outcome.candidate is not None
    assert outcome.usage == RepairUsage(input_tokens=0, output_tokens=0, latency_ms=0)


def test_llm_candidate_carries_usage() -> None:
    outcome = RepairOutcome(
        candidate=PatchCandidate(**LLM_EXAMPLE),
        usage=RepairUsage(input_tokens=18400, output_tokens=650, latency_ms=2300),
    )

    assert outcome.candidate is not None
    assert outcome.candidate.touched_paths == ["proj/users.py"]
    assert outcome.usage.input_tokens == 18400


def test_no_candidate_outcome_keeps_usage_for_budgeting() -> None:
    outcome = RepairOutcome(
        rejection_reason="model reply had no SEARCH/REPLACE blocks",
        usage=RepairUsage(input_tokens=9000, output_tokens=120, latency_ms=800),
    )

    assert outcome.candidate is None
    assert outcome.usage.input_tokens == 9000


def test_outcome_rejects_candidate_and_reason_together() -> None:
    with pytest.raises(ValidationError):
        RepairOutcome(
            candidate=PatchCandidate(**LLM_EXAMPLE),
            rejection_reason="should not be here",
        )


def test_outcome_rejects_neither_candidate_nor_reason() -> None:
    with pytest.raises(ValidationError):
        RepairOutcome()


def test_candidate_requires_touched_paths() -> None:
    with pytest.raises(ValidationError):
        PatchCandidate(diff="x", method="llm", touched_paths=[])


def test_candidate_rejects_blank_or_duplicate_paths() -> None:
    with pytest.raises(ValidationError):
        PatchCandidate(diff="x", method="llm", touched_paths=["  "])
    with pytest.raises(ValidationError):
        PatchCandidate(diff="x", method="llm", touched_paths=["a.py", "a.py"])


def test_usage_rejects_negative_numbers() -> None:
    with pytest.raises(ValidationError):
        RepairUsage(input_tokens=-1)
