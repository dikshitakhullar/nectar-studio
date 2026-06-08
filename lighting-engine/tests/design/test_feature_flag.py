"""Tests for the v1 designer feature flag."""

import pytest

from lighting_engine.design.feature_flag import is_v1_designer_enabled


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIGHTING_ENGINE_USE_V1_DESIGNER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert is_v1_designer_enabled() is False


def test_explicit_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGHTING_ENGINE_USE_V1_DESIGNER", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert is_v1_designer_enabled() is False


def test_enabled_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGHTING_ENGINE_USE_V1_DESIGNER", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert is_v1_designer_enabled() is True


def test_enabled_without_api_key_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag on but no key → disable rather than crash at runtime."""
    monkeypatch.setenv("LIGHTING_ENGINE_USE_V1_DESIGNER", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert is_v1_designer_enabled() is False


def test_accepts_truthy_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    for value in ("true", "TRUE", "1", "yes", "Yes"):
        monkeypatch.setenv("LIGHTING_ENGINE_USE_V1_DESIGNER", value)
        assert is_v1_designer_enabled() is True, value
