from pathlib import Path

import pytest

from codyssey.config import CodysseyConfig, ConfigError, load_config

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.yaml"


def test_example_config_is_valid():
    config = load_config(EXAMPLE)
    assert config.repair.strategy == "hybrid"
    assert config.storage.database_path == Path("data/codyssey.db")
    assert config.sandbox.network_enabled is False


def test_empty_file_yields_defaults(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_config(path) == CodysseyConfig()


@pytest.mark.parametrize(
    "text",
    [
        "repair: {max_attempts: 0}",
        "repair: {strategy: random}",
        "repair: {unknown_key: 1}",
        "storage: {database_url: postgres://x/y}",
        "storage: {database_url: 'sqlite:///'}",
        "llm: {temperature: 5}",
        "llm: {input_usd_per_million_tokens: 1.0}",
        "repair: {strategy: llm, max_llm_calls: 0}",
        "repair: {max_estimated_cost_usd: 1.0}",
        "- not a mapping",
        "repair: [unclosed",
    ],
)
def test_invalid_config_is_rejected(tmp_path, text):
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")


def test_cost_ceiling_with_prices_is_accepted(tmp_path):
    path = tmp_path / "cost.yaml"
    path.write_text(
        "llm: {input_usd_per_million_tokens: 1.0, output_usd_per_million_tokens: 4.0}\n"
        "repair: {max_estimated_cost_usd: 2.5}\n",
        encoding="utf-8",
    )
    assert load_config(path).repair.max_estimated_cost_usd == 2.5


def test_deterministic_strategy_allows_zero_llm_calls(tmp_path):
    path = tmp_path / "det.yaml"
    path.write_text("repair: {strategy: deterministic, max_llm_calls: 0}\n", encoding="utf-8")
    assert load_config(path).repair.max_llm_calls == 0
