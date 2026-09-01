"""Unit tests for template registry."""

import pytest

from strategy_templates.base import BaseTemplateStrategy, TemplateMetadata
from strategy_templates.registry import (
    register_template,
    get_template,
    list_templates,
    get_template_spec,
)


class DummyTemplateStrategy(BaseTemplateStrategy):
    """Dummy strategy for testing."""

    metadata = TemplateMetadata(
        name="dummy_strategy",
        description="A dummy strategy for testing",
        version="1.0.0",
    )

    def on_bar(self, bar, history, broker):
        pass


class TestTemplateRegistry:
    """Tests for template registry."""

    def test_register_template(self):
        """Test registering a template."""
        # Register should work
        register_template(DummyTemplateStrategy)

        # Should be able to retrieve it
        retrieved = get_template("dummy_strategy")
        assert retrieved is DummyTemplateStrategy

    def test_register_duplicate_fails(self):
        """Test that duplicate registration fails."""
        register_template(DummyTemplateStrategy)

        with pytest.raises(ValueError, match="already registered"):
            register_template(DummyTemplateStrategy)

    def test_get_nonexistent_returns_none(self):
        """Test getting a nonexistent template returns None."""
        result = get_template("nonexistent_strategy")
        assert result is None

    def test_list_templates(self):
        """Test listing all templates."""
        register_template(DummyTemplateStrategy)

        templates = list_templates()
        assert "dummy_strategy" in templates
        assert templates["dummy_strategy"].name == "Dummy Strategy"

    def test_get_template_spec(self):
        """Test getting template spec."""
        register_template(DummyTemplateStrategy)

        spec = get_template_spec("dummy_strategy")
        assert spec is not None
        assert spec["name"] == "dummy_strategy"
        assert spec["description"] == "A dummy strategy for testing"
        assert spec["version"] == "1.0.0"
        assert spec["entrypoint"]["function"] == "create_live_strategy"


class TestBaseTemplateStrategy:
    """Tests for BaseTemplateStrategy."""

    def test_get_metadata(self):
        """Test getting template metadata."""
        metadata = DummyTemplateStrategy.get_metadata()
        assert metadata.name == "dummy_strategy"
        assert metadata.description == "A dummy strategy for testing"

    def test_to_spec_dict(self):
        """Test converting to spec dict."""
        spec = DummyTemplateStrategy.to_spec_dict()
        assert spec["name"] == "dummy_strategy"
        assert spec["description"] == "A dummy strategy for testing"
        assert spec["version"] == "1.0.0"

    def test_initialize_raises_without_context(self):
        """Test that operations fail without initialization."""
        strategy = DummyTemplateStrategy()

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = strategy.context

    def test_get_param(self):
        """Test getting parameters."""
        metadata = TemplateMetadata(
            name="test",
            description="test",
        )
        strategy = DummyTemplateStrategy()
        strategy._params = {"foo": "bar", "num": 42}

        assert strategy.get_param("foo") == "bar"
        assert strategy.get_param("num") == 42
        assert strategy.get_param("nonexistent", "default") == "default"
