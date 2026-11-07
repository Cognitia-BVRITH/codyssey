import pytest

from codyssey.config import CodysseyConfig
from codyssey.contracts import (
    EventKind,
    PatchCandidate,
    RepairOutcome,
    RepairUsage,
    RunStatus,
    Task,
)
from codyssey.fakes import (
    FakeRepairer,
    FakeValidation,
    FakeValidator,
    attempt_failed,
    attempt_verified,
    baseline_reproduced,
)
from codyssey.orchestrator import Orchestrator, summarize_failure
from codyssey.storage import ArtifactStore, InvalidTransition, RunStore

DIFF_A = (
    "--- a/voting.py\n+++ b/voting.py\n@@ -2 +2 @@\n-    return age > 18\n+    return age >= 18\n"
)
DIFF_B = DIFF_A.replace(">=", ">= 0 and age >=")


@pytest.fixture
def task():
    return Task(
        id="boundary-example",
        repo_url="https://example.com/team/fixture.git",
        base_commit="a" * 40,
        issue_title="Voting age boundary",
        issue_body="An eighteen-year-old must be eligible.",
        environment_image="codyssey-fixture:local",
        test_command=["python", "-m", "pytest"],
        fail_to_pass=["test_voting.py::test_at_voting_age"],
        pass_to_pass=["test_voting.py::test_below_voting_age"],
    )


class Harness:
    def __init__(self, tmp_path, task, config=None, clock=None):
        self.task = task
        self.store = RunStore(tmp_path / "codyssey.db")
        self.artifacts = ArtifactStore(tmp_path / "runs")
        self.store.add_task(task)
        self.config = config or CodysseyConfig()
        self.store.create_run(task.id, self.config, run_id="r1")
        self.clock = clock

    def run(self, validator, repairer):
        kwargs = {"clock": self.clock} if self.clock else {}
        orchestrator = Orchestrator(self.store, self.artifacts, validator, repairer, **kwargs)
        return orchestrator.run("r1")

    def kinds(self):
        return [e.event.kind for e in self.store.list_events("r1")]


def candidate(diff=DIFF_A, method="deterministic"):
    return PatchCandidate(diff=diff, method=method, touched_paths=["voting.py"])


def outcome(diff=DIFF_A, method="deterministic", **usage):
    return RepairOutcome(candidate=candidate(diff, method), usage=RepairUsage(**usage))


def config(**repair):
    return CodysseyConfig.model_validate({"repair": repair})


def test_verified_on_first_attempt(tmp_path, task):
    h = Harness(tmp_path, task)
    validator = FakeValidator(baseline_reproduced(task), [attempt_verified(task)])
    repairer = FakeRepairer([outcome()])

    run = h.run(validator, repairer)

    assert run.status == RunStatus.VERIFIED
    assert run.started_at and run.finished_at
    assert h.artifacts.final_patch_path("r1").read_text(encoding="utf-8") == DIFF_A
    assert (h.artifacts.run_dir("r1") / "config.json").is_file()
    [stored] = h.store.list_attempts("r1")
    assert stored.attempt.status == "tests_passed"
    assert stored.attempt.patch_path == "r1/attempt1/patch.diff"
    assert stored.attempt.method == "deterministic"
    assert [r.outcome for r in h.store.list_test_results("r1", 0)] == ["failed", "passed"]
    assert all(r.outcome == "passed" for r in h.store.list_test_results("r1", 1))
    assert h.kinds() == [
        EventKind.RUN_QUEUED,
        EventKind.RUN_STARTED,
        EventKind.BASELINE_REPRODUCED,
        EventKind.ATTEMPT_STARTED,
        EventKind.ATTEMPT_FINISHED,
        EventKind.RUN_FINISHED,
    ]
    baseline_dir, baseline_candidate = validator.calls[0]
    assert baseline_dir == h.artifacts.baseline_dir("r1") and baseline_candidate is None
    assert validator.calls[1][0] == h.artifacts.evidence_dir("r1", 1)


def test_failed_attempt_feeds_back_and_second_attempt_verifies(tmp_path, task):
    h = Harness(tmp_path, task)
    validator = FakeValidator(
        baseline_reproduced(task), [attempt_failed(task), attempt_verified(task)]
    )
    repairer = FakeRepairer([outcome(DIFF_A), outcome(DIFF_B)])

    run = h.run(validator, repairer)

    assert run.status == RunStatus.VERIFIED
    first, second = repairer.requests
    assert first.feedback is None and first.attempt_number == 1
    assert "test_voting.py::test_at_voting_age" in second.feedback
    assert second.remaining.attempts == first.remaining.attempts - 1
    statuses = [s.attempt.status for s in h.store.list_attempts("r1")]
    assert statuses == ["tests_failed", "tests_passed"]
    assert h.artifacts.final_patch_path("r1").read_text(encoding="utf-8") == DIFF_B


def test_attempt_limit_fails_the_run_without_a_final_patch(tmp_path, task):
    h = Harness(tmp_path, task, config(max_attempts=2))
    validator = FakeValidator(
        baseline_reproduced(task), [attempt_failed(task), attempt_failed(task)]
    )
    repairer = FakeRepairer([outcome(DIFF_A), outcome(DIFF_B)])

    run = h.run(validator, repairer)

    assert run.status == RunStatus.FAILED
    assert run.status_reason == "attempt limit reached (2)"
    assert h.artifacts.final_patch_path("r1") is None
    assert len(repairer.requests) == 2
    assert h.artifacts.read_text("r1/attempt2/patch.diff") == DIFF_B


def test_no_candidate_outcomes_are_charged_and_stop_at_the_token_limit(tmp_path, task):
    h = Harness(tmp_path, task, config(max_attempts=5, max_total_tokens=1000))
    rejected = RepairOutcome(
        rejection_reason="reply had no SEARCH/REPLACE blocks",
        usage=RepairUsage(input_tokens=450, output_tokens=60, requests=2),
    )
    repairer = FakeRepairer([rejected, rejected, rejected])

    run = h.run(FakeValidator(baseline_reproduced(task)), repairer)

    assert run.status == RunStatus.FAILED
    assert "token limit" in run.status_reason
    assert len(repairer.requests) == 2
    assert repairer.requests[1].feedback == "reply had no SEARCH/REPLACE blocks"
    attempts = h.store.list_attempts("r1")
    assert [a.attempt.status for a in attempts] == ["patch_invalid", "patch_invalid"]
    assert attempts[0].attempt.method is None and attempts[0].attempt.patch_path is None
    assert h.store.total_usage("r1").requests == 4


def test_provider_request_limit_counts_requests_not_attempts(tmp_path, task):
    h = Harness(tmp_path, task, config(max_attempts=5, max_llm_calls=3))
    rejected = RepairOutcome(rejection_reason="bad format", usage=RepairUsage(requests=3))
    run = h.run(FakeValidator(baseline_reproduced(task)), FakeRepairer([rejected]))
    assert "request limit" in run.status_reason


def test_duplicate_candidate_is_not_revalidated(tmp_path, task):
    h = Harness(tmp_path, task)
    validator = FakeValidator(
        baseline_reproduced(task), [attempt_failed(task), attempt_verified(task)]
    )
    repairer = FakeRepairer([outcome(DIFF_A), outcome(DIFF_A), outcome(DIFF_B)])

    run = h.run(validator, repairer)

    assert run.status == RunStatus.VERIFIED
    assert len(validator.calls) == 3  # baseline plus attempts 1 and 3 only
    second = h.store.list_attempts("r1")[1].attempt
    assert second.status == "patch_invalid"
    assert second.error_summary.startswith("duplicate of attempt 1")
    assert "duplicate of attempt 1" in repairer.requests[2].feedback


def test_unreproduced_baseline_is_an_error_not_a_repair_failure(tmp_path, task):
    h = Harness(tmp_path, task)
    baseline = FakeValidation("error", reason="docker daemon unavailable")
    repairer = FakeRepairer([])

    run = h.run(FakeValidator(baseline), repairer)

    assert run.status == RunStatus.ERROR
    assert run.status_reason == "baseline not reproduced (error): docker daemon unavailable"
    assert repairer.requests == []
    assert h.store.list_attempts("r1") == []


def test_validator_infrastructure_error_ends_the_run_as_error(tmp_path, task):
    h = Harness(tmp_path, task)
    broken = FakeValidation("error", reason="container failed to start")
    run = h.run(FakeValidator(baseline_reproduced(task), [broken]), FakeRepairer([outcome()]))

    assert run.status == RunStatus.ERROR
    assert "container failed to start" in run.status_reason
    [stored] = h.store.list_attempts("r1")
    assert stored.attempt.status == "error"
    assert h.artifacts.final_patch_path("r1") is None


def test_timeout_and_invalid_patch_map_to_attempt_statuses(tmp_path, task):
    h = Harness(tmp_path, task, config(max_attempts=2))
    validator = FakeValidator(
        baseline_reproduced(task),
        [FakeValidation("timeout", reason="tests timed out"), FakeValidation("patch_invalid")],
    )
    repairer = FakeRepairer([outcome(DIFF_A), outcome(DIFF_B)])

    run = h.run(validator, repairer)

    assert run.status == RunStatus.FAILED
    assert run.status_reason == "attempt limit reached (2)"
    statuses = [s.attempt.status for s in h.store.list_attempts("r1")]
    assert statuses == ["timeout", "patch_invalid"]
    assert "infinite loop" in repairer.requests[1].feedback


def test_cancellation_is_observed_between_attempts(tmp_path, task):
    h = Harness(tmp_path, task)

    class CancellingRepairer(FakeRepairer):
        def propose(self, request):
            result = super().propose(request)
            h.store.request_cancel("r1")
            return result

    repairer = CancellingRepairer([outcome(DIFF_A), outcome(DIFF_B)])
    validator = FakeValidator(baseline_reproduced(task), [attempt_failed(task)])

    run = h.run(validator, repairer)

    assert run.status == RunStatus.CANCELLED
    assert len(h.store.list_attempts("r1")) == 1
    assert h.kinds()[-2:] == [EventKind.ATTEMPT_FINISHED, EventKind.RUN_FINISHED]


def test_run_cancelled_while_queued_cannot_start(tmp_path, task):
    h = Harness(tmp_path, task)
    h.store.request_cancel("r1")
    with pytest.raises(InvalidTransition):
        h.run(FakeValidator(baseline_reproduced(task)), FakeRepairer([]))


def test_wall_clock_limit_stops_the_loop(tmp_path, task):
    now = [0.0]
    h = Harness(tmp_path, task, config(timeout_seconds=60), clock=lambda: now[0])

    class SlowRepairer(FakeRepairer):
        def propose(self, request):
            now[0] += 61
            return super().propose(request)

    validator = FakeValidator(baseline_reproduced(task), [attempt_failed(task)])
    run = h.run(validator, SlowRepairer([outcome()]))

    assert run.status == RunStatus.FAILED
    assert run.status_reason == "time limit reached (60s)"


def test_unexpected_exception_ends_the_run_as_error(tmp_path, task):
    h = Harness(tmp_path, task)

    class Exploding:
        def propose(self, request):
            raise RuntimeError("provider client crashed")

    run = h.run(FakeValidator(baseline_reproduced(task)), Exploding())

    assert run.status == RunStatus.ERROR
    assert "RuntimeError: provider client crashed" in run.status_reason
    assert h.kinds()[-1] == EventKind.RUN_FINISHED


def test_estimated_cost_is_persisted(tmp_path, task):
    cfg = CodysseyConfig.model_validate(
        {"llm": {"input_usd_per_million_tokens": 1.0, "output_usd_per_million_tokens": 2.0}}
    )
    h = Harness(tmp_path, task, cfg)
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000, "requests": 1}
    validator = FakeValidator(baseline_reproduced(task), [attempt_verified(task)])
    h.run(validator, FakeRepairer([outcome(method="llm", **usage)]))
    assert h.store.get_estimated_cost("r1") == pytest.approx(2.0)


def test_finished_event_summarizes_the_run(tmp_path, task):
    h = Harness(tmp_path, task)
    validator = FakeValidator(baseline_reproduced(task), [attempt_verified(task)])
    h.run(validator, FakeRepairer([outcome(input_tokens=10, output_tokens=5, requests=1)]))
    final = h.store.list_events("r1")[-1].event
    assert final.data == {"status": "verified", "attempts": 1, "tokens": 15, "requests": 1}


def test_failure_summary_is_bounded():
    report = attempt_failed(
        Task(
            id="t",
            repo_url="x",
            base_commit="a" * 40,
            issue_title="i",
            issue_body="b",
            environment_image="img",
            test_command=["pytest"],
            fail_to_pass=[f"t.py::f{i}" for i in range(30)],
            pass_to_pass=["t.py::p"],
        )
    ).report
    text = summarize_failure("tests_failed", "x" * 5000, report)
    assert len(text) == 2000
    assert summarize_failure("tests_failed", None, None) == "tests_failed"
