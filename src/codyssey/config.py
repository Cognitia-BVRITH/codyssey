"""Runtime configuration: validated settings read from YAML; secrets stay in the environment."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from codyssey.contracts import Contract

SQLITE_PREFIX = "sqlite:///"


class ConfigError(Exception):
    """Raised when a configuration file cannot be read or fails validation."""


class StorageConfig(Contract):
    database_url: str = f"{SQLITE_PREFIX}data/codyssey.db"
    artifact_root: str = "data/runs"

    @model_validator(mode="after")
    def validate_database_url(self) -> "StorageConfig":
        if not self.database_url.startswith(SQLITE_PREFIX) or self.database_url == SQLITE_PREFIX:
            raise ValueError(f"database_url must look like {SQLITE_PREFIX}path/to/file.db")
        return self

    @property
    def database_path(self) -> Path:
        return Path(self.database_url.removeprefix(SQLITE_PREFIX))


class LLMConfig(Contract):
    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str | None = None
    model: str | None = None
    # Name of the environment variable holding the key; the key itself is never stored.
    api_key_env: str = Field(default="CODYSSEY_LLM_API_KEY", min_length=1)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=2000, gt=0)
    max_retries: int = Field(default=3, ge=0)
    # Price assumptions are saved with every run so estimated cost can be reproduced.
    input_usd_per_million_tokens: float | None = Field(default=None, ge=0)
    output_usd_per_million_tokens: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_pricing_pair(self) -> "LLMConfig":
        prices = (self.input_usd_per_million_tokens, self.output_usd_per_million_tokens)
        if (prices[0] is None) != (prices[1] is None):
            raise ValueError("Set both input and output prices, or neither")
        return self


class RepairConfig(Contract):
    strategy: Literal["deterministic", "llm", "hybrid"] = "hybrid"
    max_attempts: int = Field(default=5, ge=1)
    max_deterministic_candidates: int = Field(default=3, ge=0)
    max_total_tokens: int = Field(default=300_000, gt=0)
    max_llm_calls: int = Field(default=10, ge=0)
    max_context_tokens: int = Field(default=20_000, gt=0)
    timeout_seconds: int = Field(default=1200, gt=0)
    max_estimated_cost_usd: float | None = Field(default=None, gt=0)


class SandboxConfig(Contract):
    image: str | None = None
    network_enabled: bool = False
    run_as_non_root: bool = True
    cpu_limit: float = Field(default=2, gt=0)
    memory_limit: str = Field(default="2g", min_length=1)
    process_limit: int = Field(default=128, gt=0)
    test_timeout_seconds: int = Field(default=120, gt=0)
    max_output_bytes: int = Field(default=1_048_576, gt=0)
    recreate_between_attempts: bool = True


class CodysseyConfig(Contract):
    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    repair: RepairConfig = Field(default_factory=RepairConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)

    @model_validator(mode="after")
    def validate_cross_settings(self) -> "CodysseyConfig":
        if self.repair.strategy != "deterministic" and self.repair.max_llm_calls == 0:
            raise ValueError(
                "repair.max_llm_calls must be positive unless strategy is deterministic"
            )
        if self.repair.max_estimated_cost_usd is not None and (
            self.llm.input_usd_per_million_tokens is None
        ):
            raise ValueError("repair.max_estimated_cost_usd requires llm price settings")
        return self


def load_config(path: Path) -> CodysseyConfig:
    """Read and validate a YAML file; an empty file yields the defaults."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return CodysseyConfig.model_validate({} if raw is None else raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(str(exc)) from exc
