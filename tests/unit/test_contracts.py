import pytest
from pydantic import ValidationError

from codyssey.contracts import LLMResponse, PatchCandidate, Task


@pytest.fixture
def task_data():
    return {
        "id": "boundary-example",
        "repo_url": "https://example.com/team/fixture.git",
        "base_commit": "a" * 40,
        "issue_title": "Voting age boundary",
        "issue_body": "An eighteen-year-old must be eligible.",
        "environment_image": "codyssey-fixture:local",
        "test_command": ["python", "-m", "pytest"],
        "fail_to_pass": ["test_voting.py::test_at_voting_age"],
        "pass_to_pass": ["test_voting.py::test_below_voting_age"],
    }


@pytest.mark.parametrize("field", ["fail_to_pass", "pass_to_pass"])
def test_task_requires_both_test_groups(task_data, field):
    task_data[field] = []
    with pytest.raises(ValidationError):
        Task.model_validate(task_data)


def test_task_rejects_overlapping_test_groups(task_data):
    task_data["pass_to_pass"] = task_data["fail_to_pass"]
    with pytest.raises(ValidationError):
        Task.model_validate(task_data)


def test_task_rejects_mutable_revision(task_data):
    task_data["base_commit"] = "main"
    with pytest.raises(ValidationError):
        Task.model_validate(task_data)


def test_prepared_task_round_trips(task_data):
    task = Task.model_validate(task_data)
    assert Task.model_validate_json(task.model_dump_json()) == task


def test_patch_preserves_diff_whitespace():
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    assert PatchCandidate(diff=diff, method="llm", touched_paths=["a.py"]).diff == diff


def test_provider_response_preserves_code_whitespace():
    text = "    return True\n"
    response = LLMResponse(text=text, input_tokens=1, output_tokens=1, latency_ms=1)
    assert response.text == text


def test_run_lifecycle_allows_only_forward_transitions():
    from codyssey.contracts import ALLOWED_TRANSITIONS, TERMINAL_STATUSES, RunStatus

    assert RunStatus.RUNNING in ALLOWED_TRANSITIONS[RunStatus.QUEUED]
    assert RunStatus.VERIFIED not in ALLOWED_TRANSITIONS[RunStatus.QUEUED]
    assert ALLOWED_TRANSITIONS[RunStatus.RUNNING] == TERMINAL_STATUSES
    assert all(not ALLOWED_TRANSITIONS[status] for status in TERMINAL_STATUSES)
    assert set(ALLOWED_TRANSITIONS) == set(RunStatus)


def test_attempt_method_is_optional_for_no_candidate():
    from codyssey.contracts import Attempt

    attempt = Attempt(run_id="r1", number=1, status="patch_invalid")
    assert attempt.method is None


def test_progress_event_round_trips_and_rejects_unknown_kind():
    from codyssey.contracts import EventKind, ProgressEvent

    event = ProgressEvent(kind=EventKind.ATTEMPT_STARTED, attempt=2, data={"tokens": 10})
    assert ProgressEvent.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError):
        ProgressEvent(kind="unknown")
    with pytest.raises(ValidationError):
        ProgressEvent(kind=EventKind.RUN_STARTED, data={"nested": {"a": 1}})
