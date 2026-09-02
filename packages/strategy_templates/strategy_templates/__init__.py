"""Strategy templates package for PrompTrading.

This package contains pre-built trading strategies that can be used as templates
for SaaS subscription.
"""

from strategy_templates.base import BaseTemplateStrategy, TemplateMetadata

# Auto-discover and register all templates
from strategy_templates.discovery import _templates

__all__ = ["BaseTemplateStrategy", "TemplateMetadata", "_templates"]
