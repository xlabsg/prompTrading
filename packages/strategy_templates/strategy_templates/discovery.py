"""Auto-discovery and registration of strategy templates.

This module scans the templates directory and registers all strategy templates.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Type

from strategy_templates.base import BaseTemplateStrategy
from strategy_templates.registry import register_template


def discover_and_register_templates() -> dict[str, Type[BaseTemplateStrategy]]:
    """Discover and register all strategy templates.

    Scans the templates directory for strategy modules and automatically
    registers any classes that inherit from BaseTemplateStrategy.

    Returns:
        Dictionary mapping template_id to template class
    """
    templates_dir = Path(__file__).parent / "templates"

    if not templates_dir.exists():
        return {}

    discovered = {}

    # Walk through all subdirectories in templates/
    for template_path in templates_dir.iterdir():
        if not template_path.is_dir() or template_path.name.startswith("_"):
            continue

        # Look for __init__.py in the template directory
        init_file = template_path / "__init__.py"
        if not init_file.exists():
            continue

        # Convert path to module name
        rel_path = template_path.relative_to(Path(__file__).parent.parent)
        module_name = ".".join(rel_path.parts)

        try:
            # Import the module
            module = importlib.import_module(module_name)

            # Find all classes that inherit from BaseTemplateStrategy
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (obj is not BaseTemplateStrategy and
                    issubclass(obj, BaseTemplateStrategy) and
                    hasattr(obj, "metadata")):
                    # Register the template
                    try:
                        register_template(obj)
                        template_id = obj.get_metadata().name
                        discovered[template_id] = obj
                        print(f"Registered template: {template_id}")
                    except ValueError as e:
                        # Template already registered or invalid
                        print(f"Warning: {e}")

        except Exception as e:
            # Skip modules that fail to import
            print(f"Warning: Failed to import {module_name}: {e}")

    return discovered


# Auto-discover on module import
_templates = discover_and_register_templates()
