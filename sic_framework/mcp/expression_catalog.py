"""
Shared JSON shape for robot expression catalogs (MCP ``get_expressions`` / ``play_expression``).

Copy this module's ``build_catalog`` pattern when adding a new robot; implement playback
in a robot-specific module (e.g. ``nao_expressions.py``).
"""

from __future__ import annotations

import json
from typing import Any, Optional


def build_catalog(
    *,
    robot_type: str,
    catalog_version: int,
    expressions: list[dict[str, Any]],
    play_expression: dict[str, Any],
    expression_kinds: dict[str, Any],
    notes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Assemble a catalog dict with a consistent top-level layout for all robots.

    Each ``expressions[]`` entry should include at least:
    ``id``, ``name``, ``description``, ``kind``, ``default_args``.
    """
    # Top-level keys are stable across robots so agents can parse any get_expressions() payload.
    catalog: dict[str, Any] = {
        "robot_type": robot_type,
        "catalog_version": catalog_version,
        "play_expression": play_expression,
        "expression_kinds": expression_kinds,
        "expressions": expressions,
    }
    if notes:
        catalog["notes"] = notes
    return catalog


def catalog_to_json(catalog: dict[str, Any], *, indent: int = 2) -> str:
    return json.dumps(catalog, indent=indent)
