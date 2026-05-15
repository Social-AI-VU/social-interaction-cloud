"""
NAO expression catalog and playback for MCP servers.

This module is the NAO-specific half of a small template pattern:

- ``get_expressions_catalog()`` — JSON-serializable catalog (no robot connection).
- ``play_nao_expression()`` — map ``expression_id`` + optional overrides to SIC motion requests.

Other robots can mirror the same shape (catalog + ``play_*_expression``) with different
``kind`` values and ``default_args`` fields.
"""

from __future__ import annotations

from typing import Any, Optional

from sic_framework.devices.common_naoqi.naoqi_motion import (
    NaoPostureRequest,
    NaoqiAnimationRequest,
)
from sic_framework.mcp.expression_catalog import build_catalog, catalog_to_json

# Catalog version bumps when the JSON schema or expression list changes.
CATALOG_VERSION = 2
ROBOT_TYPE = "nao"

# Rudimentary starter set (extend as needed). See also ``demo_nao_motion.py`` and
# http://doc.aldebaran.com/2-4/naoqi/motion/alanimationplayer-advanced.html
NAO_EXPRESSIONS: list[dict[str, Any]] = [
    {
        "id": "posture_stand",
        "name": "Stand",
        "description": "Go to the standard standing posture.",
        "kind": "posture",
        "default_args": {"target_posture": "Stand", "speed": 0.5},
    },
    {
        "id": "posture_stand_init",
        "name": "StandInit",
        "description": "Go to the initial stand posture.",
        "kind": "posture",
        "default_args": {"target_posture": "StandInit", "speed": 0.4},
    },
    {
        "id": "posture_sit",
        "name": "Sit",
        "description": "Sit down.",
        "kind": "posture",
        "default_args": {"target_posture": "Sit", "speed": 0.4},
    },
    {
        "id": "posture_sit_relax",
        "name": "SitRelax",
        "description": "Sit in a relaxed pose.",
        "kind": "posture",
        "default_args": {"target_posture": "SitRelax", "speed": 0.4},
    },
    {
        "id": "posture_crouch",
        "name": "Crouch",
        "description": "Crouch posture.",
        "kind": "posture",
        "default_args": {"target_posture": "Crouch", "speed": 0.4},
    },
    {
        "id": "gesture_hey",
        "name": "Hey wave",
        "description": "Wave hello (Stand gesture).",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Hey_1"},
    },
    {
        "id": "gesture_show_sky",
        "name": "Show sky",
        "description": "Point or gesture toward the sky.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_5"},
    },
    {
        "id": "gesture_enthusiastic",
        "name": "Enthusiastic",
        "description": "Enthusiastic standing gesture (full NAOqi path required on robot).",
        "kind": "animation",
        "default_args": {
            "animation_path": "animations/Stand/Gestures/Enthusiastic_4",
        },
    },
    {
        "id": "gesture_bodytalk",
        "name": "Body talk",
        "description": "Seated body-language animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_1"},
    },
]

_EXPRESSION_BY_ID: dict[str, dict[str, Any]] = {
    entry["id"]: entry for entry in NAO_EXPRESSIONS
}


def _normalize_nao_animation_path(animation_path: str) -> str:
    """
    NAOqi requires ``package/path`` (e.g. ``animations/Stand/Gestures/Hey_1``).

    Short names like ``Enthusiastic_4`` fail on many images with "Wrong path format".
    """
    path = (animation_path or "").strip()
    if not path:
        raise ValueError("animation_path must be non-empty.")
    if "/" in path:
        return path
    return "animations/Stand/Gestures/{}".format(path)


def _build_expression_aliases() -> dict[str, str]:
    """Map common agent/user labels to catalog ``id`` values."""
    aliases: dict[str, str] = {}
    for entry in NAO_EXPRESSIONS:
        eid = entry["id"]
        aliases[eid] = eid
        aliases[eid.lower()] = eid
        name = entry.get("name")
        if name:
            aliases[name.strip().lower()] = eid
        args = entry.get("default_args") or {}
        if entry.get("kind") == "posture":
            posture = args.get("target_posture")
            if posture:
                aliases[str(posture).strip().lower()] = eid
        elif entry.get("kind") == "animation":
            anim_path = args.get("animation_path", "")
            if anim_path:
                base = str(anim_path).split("/")[-1]
                aliases[base.lower()] = eid
                aliases[base] = eid
    return aliases


_EXPRESSION_ALIASES = _build_expression_aliases()


def get_expressions_catalog() -> dict[str, Any]:
    """
    Return the full expression catalog for agents and other MCP clients.

    ``play_expression`` contract (NAO):

    - **Required:** ``expression_id`` — one of the ``id`` values in ``expressions``.
    - **Optional:** ``speed`` (float) — overrides posture transition speed for ``kind=posture`` only.
    """
    return build_catalog(
        robot_type=ROBOT_TYPE,
        catalog_version=CATALOG_VERSION,
        expressions=list(NAO_EXPRESSIONS),
        play_expression={
            "description": (
                "Play a catalogued expression on the robot. Pass expression_id; "
                "for postures you may override speed (0.0–1.0)."
            ),
            "parameters": {
                "expression_id": {
                    "type": "string",
                    "required": True,
                    "description": "Catalog entry id (see expressions[].id).",
                },
                "speed": {
                    "type": "number",
                    "required": False,
                    "description": "Only for kind=posture. Transition speed; default from catalog.",
                },
            },
        },
        expression_kinds={
            "posture": {
                "sic_request": "NaoPostureRequest",
                "args": ["target_posture", "speed"],
            },
            "animation": {
                "sic_request": "NaoqiAnimationRequest",
                "args": ["animation_path"],
            },
        },
        notes=[
            "Full NAO animation list: "
            "http://doc.aldebaran.com/2-4/naoqi/motion/alanimationplayer-advanced.html",
            "Postures: http://doc.aldebaran.com/2-4/family/robots/postures_robot.html",
        ],
    )


def get_expressions_json(*, indent: int = 2) -> str:
    """Serialize the catalog for MCP tool responses."""
    return catalog_to_json(get_expressions_catalog(), indent=indent)


def resolve_expression(expression_id: str) -> dict[str, Any]:
    """Look up a catalog entry or raise ``KeyError``."""
    key = (expression_id or "").strip()
    if key in _EXPRESSION_BY_ID:
        return _EXPRESSION_BY_ID[key]
    alias_key = key.lower()
    if alias_key in _EXPRESSION_ALIASES:
        return _EXPRESSION_BY_ID[_EXPRESSION_ALIASES[alias_key]]
    known = ", ".join(sorted(_EXPRESSION_BY_ID))
    raise KeyError(
        f"Unknown expression_id {key!r}. Known ids: {known or '(none)'}"
    )


def play_nao_expression(
    nao: Any,
    expression_id: str,
    *,
    speed: Optional[float] = None,
    stub: bool = False,
    logger: Any = None,
) -> str:
    """
    Play one catalogued expression via ``nao.motion``.

    :param nao: Connected ``Nao`` device (ignored when ``stub`` is True).
    :returns: Human-readable result message.
    """
    entry = resolve_expression(expression_id)
    kind = entry["kind"]
    args: dict[str, Any] = dict(entry.get("default_args") or {})

    if kind == "posture" and speed is not None:
        args["speed"] = float(speed)

    label = entry.get("name") or expression_id

    if stub:
        return (
            f"STUB: Would play expression {expression_id!r} ({label}, kind={kind}) "
            f"with args={args!r}."
        )

    if nao is None:
        raise RuntimeError("NAO device is not connected.")

    motion = nao.motion
    if kind == "posture":
        target = args["target_posture"]
        posture_speed = args.get("speed", 0.4)
        motion.request(NaoPostureRequest(target, posture_speed))
        msg = f"NAO posture {target!r} (speed={posture_speed:.2f})."
    elif kind == "animation":
        path = _normalize_nao_animation_path(args["animation_path"])
        # Do not block until the clip finishes (can exceed MCP / Ctrl+C patience).
        motion.request(NaoqiAnimationRequest(path), block=False)
        msg = f"NAO animation {path!r} (started)."
    else:
        raise ValueError(f"Unsupported expression kind {kind!r} for NAO.")

    if logger is not None:
        logger.info("Expression %s: %s", expression_id, msg)
    return msg
