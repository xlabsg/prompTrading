"""Template registry for managing strategy templates."""

from __future__ import annotations

from typing import Any
import importlib
import inspect
from pathlib import Path

from strategy_templates.base import BaseTemplateStrategy, TemplateMetadata


# Global template registry
_template_registry: dict[str, type[BaseTemplateStrategy]] = {}


def register_template(cls: type[BaseTemplateStrategy]) -> type[BaseTemplateStrategy]:
    """Decorator to register a strategy template."""
    if not issubclass(cls, BaseTemplateStrategy):
        raise TypeError(f"{cls.__name__} must inherit from BaseTemplateStrategy")

    metadata = cls.get_metadata()
    template_id = metadata.name.lower().replace(" ", "_").replace("-", "_")

    if template_id in _template_registry:
        raise ValueError(f"Template '{template_id}' is already registered")

    _template_registry[template_id] = cls
    return cls


def get_template(template_id: str) -> type[BaseTemplateStrategy] | None:
    """Get a template class by ID."""
    return _template_registry.get(template_id)


def list_templates() -> dict[str, TemplateMetadata]:
    """List all registered templates with their metadata."""
    return {
        template_id: cls.get_metadata()
        for template_id, cls in _template_registry.items()
    }


def discover_templates(package_path: str | Path = "strategy_templates/templates") -> None:
    """Auto-discover and register templates from a package directory.

    Args:
        package_path: Path to the templates package
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return

    for module_path in package_path.rglob("*.py"):
        if module_path.name.startswith("_"):
            continue

        # Convert path to module path
        rel_path = module_path.relative_to(package_path.parent)
        module_name = ".".join(rel_path.with_suffix("").parts)

        try:
            module = importlib.import_module(module_name)

            # Find all classes that inherit from BaseTemplateStrategy
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (obj is not BaseTemplateStrategy and
                    issubclass(obj, BaseTemplateStrategy) and
                    hasattr(obj, "metadata")):
                    register_template(obj)
        except Exception as e:
            # Skip modules that fail to import
            print(f"Warning: Failed to import {module_name}: {e}")


def get_template_spec(template_id: str) -> dict[str, Any] | None:
    """Get the strategy spec for a template."""
    cls = get_template(template_id)
    if cls is None:
        return None

    return {
        **cls.to_spec_dict(),
        "template_id": template_id,
        "entrypoint": {
            "function": "create_live_strategy",
            "module": f"strategy_templates.templates.{template_id}",
        },
    }
