import pytest

from codyssey.budget import BudgetGuard, BudgetLimits
from codyssey.config import CodysseyConfig
from codyssey.contracts import RepairUsage


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def make_guard(**overrides):
    values = {
        "max_attempts": 3,
        "max_total_tokens": 1000,
        "max_llm_calls": 4,
        "timeout_seconds": 60,
    }
    values.update(overrides)
    clock = Clock()
    guard = BudgetGuard(BudgetLimits(**values), clock=clock)
    guard.start()
    return guard, clock


def test_fresh_guard_has_full_allowances():
    guard, _ = make_guard()
    assert guard.exhausted_reason() is None
    remaining = guard.remaining()
    assert (remaining.attempts, remaining.tokens, remaining.llm_requests) == (3, 1000, 4)
    assert remaining.seconds == 60
    assert remaining.cost_usd is None


def test_time_is_checked_before_everything_else():
    guard, clock = make_guard()
    guard.record_attempt()
    clock.now += 60
    assert "time limit" in guard.exhausted_reason()
    assert guard.remaining().seconds == 0


def test_attempt_limit():
    guard, _ = make_guard(max_attempts=2)
    guard.record_attempt()
    assert guard.exhausted_reason() is None
    guard.record_attempt()
    assert "attempt limit" in guard.exhausted_reason()


def test_usage_without_a_candidate_is_still_charged():
    guard, _ = make_guard()
    guard.record_usage(RepairUsage(input_tokens=900, output_tokens=100, requests=1))
    assert guard.tokens_used == 1000
    assert "token limit" in guard.exhausted_reason()
    assert guard.remaining().tokens == 0


def test_request_limit_counts_format_retries():
    guard, _ = make_guard(max_llm_calls=3)
    guard.record_usage(RepairUsage(input_tokens=1, requests=2))
    assert guard.exhausted_reason() is None
    guard.record_usage(RepairUsage(input_tokens=1, requests=1))
    assert "request limit" in guard.exhausted_reason()


def test_zero_request_limit_does_not_block_deterministic_work():
    guard, _ = make_guard(max_llm_calls=0)
    assert guard.exhausted_reason() is None


def test_cost_estimate_and_ceiling():
    guard, _ = make_guard(
        max_total_tokens=10_000_000,
        max_estimated_cost_usd=1.0,
        input_usd_per_million_tokens=1.0,
        output_usd_per_million_tokens=4.0,
    )
    guard.record_usage(RepairUsage(input_tokens=500_000, output_tokens=100_000, requests=1))
    assert guard.estimated_cost_usd == pytest.approx(0.9)
    assert guard.exhausted_reason() is None
    assert guard.remaining().cost_usd == pytest.approx(0.1)
    guard.record_usage(RepairUsage(output_tokens=50_000, requests=1))
    assert "cost limit" in guard.exhausted_reason()


def test_cost_is_unknown_without_prices():
    guard, _ = make_guard()
    guard.record_usage(RepairUsage(input_tokens=5, requests=1))
    assert guard.estimated_cost_usd is None


def test_time_requires_start():
    guard = BudgetGuard(BudgetLimits(1, 1, 1, 1))
    with pytest.raises(RuntimeError):
        guard.exhausted_reason()


def test_limits_come_from_config():
    config = CodysseyConfig.model_validate(
        {"repair": {"max_attempts": 7, "timeout_seconds": 90, "max_total_tokens": 5}}
    )
    limits = BudgetLimits.from_config(config)
    assert (limits.max_attempts, limits.timeout_seconds, limits.max_total_tokens) == (7, 90, 5)
