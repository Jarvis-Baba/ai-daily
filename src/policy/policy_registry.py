"""Centralized policy registry — single entry point for all presentation rules.

This module aggregates policy functions from domain-specific policy modules
into one lookup table. It is the foundation for future config-driven policy
selection and runtime policy swapping.

Not yet wired into the pipeline. OutputStage continues to import directly
from output_policy.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.policy.output_policy import (
    should_render_action,
    normalize_audience,
    safe_value,
    AUDIENCE_LABELS,
)

# Registry maps "domain.key" → callable
POLICY_REGISTRY: dict[str, Callable[..., Any]] = {
    "output.should_render_action": should_render_action,
    "output.normalize_audience": normalize_audience,
    "output.safe_value": safe_value,
}

# Constants exposed through the registry
POLICY_CONSTANTS: dict[str, Any] = {
    "output.audience_labels": AUDIENCE_LABELS,
}


def resolve(name: str):
    """Look up a policy function by name. Returns None if not found."""
    return POLICY_REGISTRY.get(name)
