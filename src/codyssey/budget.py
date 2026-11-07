"""Run budgets: attempts, tokens, provider requests, wall-clock time, and estimated cost.

Limits that depend on provider-reported usage are best-effort. Usage is recorded after
each request, so one request can overshoot a limit; `remaining()` lets callers bound
the next one.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from codyssey.config import CodysseyConfig
from codyssey.contracts import RepairUsage

TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class BudgetLimits:
    max_attempts: int
    max_total_tokens: int
    max_llm_calls: int
    timeout_seconds: float
    max_estimated_cost_usd: float | None = None
    input_usd_per_million_tokens: float | None = None
    output_usd_per_million_tokens: float | None = None

    @classmethod
    def from_config(cls, config: CodysseyConfig) -> "BudgetLimits":
        return cls(
            max_attempts=config.repair.max_attempts,
            max_total_tokens=config.repair.max_total_tokens,
            max_llm_calls=config.repair.max_llm_calls,
            timeout_seconds=config.repair.timeout_seconds,
            max_estimated_cost_usd=config.repair.max_estimated_cost_usd,
            input_usd_per_million_tokens=config.llm.input_usd_per_million_tokens,
            output_usd_per_million_tokens=config.llm.output_usd_per_million_tokens,
        )


@dataclass(frozen=True)
class Remaining:
    """Allowances left for the next action; counts never go below zero."""

    attempts: int
    tokens: int
    llm_requests: int
    seconds: float
    cost_usd: float | None


class BudgetGuard:
    def __init__(self, limits: BudgetLimits, clock: Callable[[], float] = time.monotonic):
        self.limits = limits
        self._clock = clock
        self._started_at: float | None = None
        self.attempts_made = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests_made = 0

    def start(self) -> None:
        """Begin the wall-clock deadline; call once, when the run starts."""
        self._started_at = self._clock()

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def elapsed_seconds(self) -> float:
        if self._started_at is None:
            raise RuntimeError("BudgetGuard.start() must be called before checking time")
        return self._clock() - self._started_at

    @property
    def estimated_cost_usd(self) -> float | None:
        """Local estimate from configured prices; None when no prices are configured."""
        limits = self.limits
        if limits.input_usd_per_million_tokens is None:
            return None
        output_price = limits.output_usd_per_million_tokens or 0.0
        return (
            self.input_tokens * limits.input_usd_per_million_tokens
            + self.output_tokens * output_price
        ) / TOKENS_PER_MILLION

    def record_attempt(self) -> None:
        self.attempts_made += 1

    def record_usage(self, usage: RepairUsage) -> None:
        """Charge usage from every outcome, including ones that produced no candidate."""
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.requests_made += usage.requests

    def exhausted_reason(self) -> str | None:
        """Return why no further work may start, or None while allowances remain."""
        limits = self.limits
        if self.elapsed_seconds >= limits.timeout_seconds:
            return f"time limit reached ({limits.timeout_seconds:g}s)"
        if self.attempts_made >= limits.max_attempts:
            return f"attempt limit reached ({limits.max_attempts})"
        if self.tokens_used >= limits.max_total_tokens:
            return f"token limit reached ({limits.max_total_tokens})"
        if self.requests_made >= limits.max_llm_calls and self.requests_made > 0:
            return f"provider request limit reached ({limits.max_llm_calls})"
        cost = self.estimated_cost_usd
        if (
            cost is not None
            and limits.max_estimated_cost_usd is not None
            and cost >= limits.max_estimated_cost_usd
        ):
            return f"estimated cost limit reached (${limits.max_estimated_cost_usd:g})"
        return None

    def remaining(self) -> Remaining:
        limits = self.limits
        cost = self.estimated_cost_usd
        cost_left = None
        if cost is not None and limits.max_estimated_cost_usd is not None:
            cost_left = max(0.0, limits.max_estimated_cost_usd - cost)
        return Remaining(
            attempts=max(0, limits.max_attempts - self.attempts_made),
            tokens=max(0, limits.max_total_tokens - self.tokens_used),
            llm_requests=max(0, limits.max_llm_calls - self.requests_made),
            seconds=max(0.0, limits.timeout_seconds - self.elapsed_seconds),
            cost_usd=cost_left,
        )
