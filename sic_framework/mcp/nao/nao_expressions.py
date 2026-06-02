"""
NAO expression catalog and playback for MCP servers.

This module is the NAO-specific half of a small template pattern:

- get_expressions_catalog() - JSON-serializable catalog (no robot connection).
- play_nao_expression() - map expression_id + optional overrides to SIC motion requests.

Other robots can mirror the same shape (catalog + play_*_expression) with different
kind values and default_args fields.
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

# Rudimentary starter set (extend as needed). See also demo_nao_motion.py and
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
        "id": "anim_sit_bodytalk_bodytalk_1",
        "name": "BodyTalk 1",
        "description": "Play BodyTalk_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_1"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_10",
        "name": "BodyTalk 10",
        "description": "Play BodyTalk_10 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_10"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_11",
        "name": "BodyTalk 11",
        "description": "Play BodyTalk_11 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_11"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_12",
        "name": "BodyTalk 12",
        "description": "Play BodyTalk_12 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_12"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_2",
        "name": "BodyTalk 2",
        "description": "Play BodyTalk_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_2"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_3",
        "name": "BodyTalk 3",
        "description": "Play BodyTalk_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_3"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_4",
        "name": "BodyTalk 4",
        "description": "Play BodyTalk_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_4"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_5",
        "name": "BodyTalk 5",
        "description": "Play BodyTalk_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_5"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_6",
        "name": "BodyTalk 6",
        "description": "Play BodyTalk_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_6"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_7",
        "name": "BodyTalk 7",
        "description": "Play BodyTalk_7 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_7"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_8",
        "name": "BodyTalk 8",
        "description": "Play BodyTalk_8 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_8"},
    },
    {
        "id": "anim_sit_bodytalk_bodytalk_9",
        "name": "BodyTalk 9",
        "description": "Play BodyTalk_9 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Sit/BodyTalk/BodyTalk_9"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_1",
        "name": "BodyTalk 1",
        "description": "Play BodyTalk_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_1"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_10",
        "name": "BodyTalk 10",
        "description": "Play BodyTalk_10 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_10"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_11",
        "name": "BodyTalk 11",
        "description": "Play BodyTalk_11 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_11"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_12",
        "name": "BodyTalk 12",
        "description": "Play BodyTalk_12 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_12"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_13",
        "name": "BodyTalk 13",
        "description": "Play BodyTalk_13 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_13"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_14",
        "name": "BodyTalk 14",
        "description": "Play BodyTalk_14 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_14"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_15",
        "name": "BodyTalk 15",
        "description": "Play BodyTalk_15 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_15"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_16",
        "name": "BodyTalk 16",
        "description": "Play BodyTalk_16 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_16"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_17",
        "name": "BodyTalk 17",
        "description": "Play BodyTalk_17 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_17"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_18",
        "name": "BodyTalk 18",
        "description": "Play BodyTalk_18 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_18"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_19",
        "name": "BodyTalk 19",
        "description": "Play BodyTalk_19 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_19"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_2",
        "name": "BodyTalk 2",
        "description": "Play BodyTalk_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_2"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_20",
        "name": "BodyTalk 20",
        "description": "Play BodyTalk_20 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_20"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_21",
        "name": "BodyTalk 21",
        "description": "Play BodyTalk_21 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_21"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_22",
        "name": "BodyTalk 22",
        "description": "Play BodyTalk_22 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_22"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_3",
        "name": "BodyTalk 3",
        "description": "Play BodyTalk_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_3"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_4",
        "name": "BodyTalk 4",
        "description": "Play BodyTalk_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_4"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_5",
        "name": "BodyTalk 5",
        "description": "Play BodyTalk_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_5"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_6",
        "name": "BodyTalk 6",
        "description": "Play BodyTalk_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_6"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_7",
        "name": "BodyTalk 7",
        "description": "Play BodyTalk_7 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_7"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_8",
        "name": "BodyTalk 8",
        "description": "Play BodyTalk_8 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_8"},
    },
    {
        "id": "anim_stand_bodytalk_bodytalk_9",
        "name": "BodyTalk 9",
        "description": "Play BodyTalk_9 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_9"},
    },
    {
        "id": "anim_stand_gestures_bowshort_1",
        "name": "BowShort 1",
        "description": "Play BowShort_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/BowShort_1"},
    },
    {
        "id": "anim_stand_gestures_enthusiastic_4",
        "name": "Enthusiastic 4",
        "description": "Play Enthusiastic_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Enthusiastic_4"},
    },
    {
        "id": "anim_stand_gestures_enthusiastic_5",
        "name": "Enthusiastic 5",
        "description": "Play Enthusiastic_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Enthusiastic_5"},
    },
    {
        "id": "anim_stand_gestures_explain_1",
        "name": "Explain 1",
        "description": "Play Explain_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_1"},
    },
    {
        "id": "anim_stand_gestures_explain_10",
        "name": "Explain 10",
        "description": "Play Explain_10 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_10"},
    },
    {
        "id": "anim_stand_gestures_explain_11",
        "name": "Explain 11",
        "description": "Play Explain_11 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_11"},
    },
    {
        "id": "anim_stand_gestures_explain_2",
        "name": "Explain 2",
        "description": "Play Explain_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_2"},
    },
    {
        "id": "anim_stand_gestures_explain_3",
        "name": "Explain 3",
        "description": "Play Explain_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_3"},
    },
    {
        "id": "anim_stand_gestures_explain_4",
        "name": "Explain 4",
        "description": "Play Explain_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_4"},
    },
    {
        "id": "anim_stand_gestures_explain_5",
        "name": "Explain 5",
        "description": "Play Explain_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_5"},
    },
    {
        "id": "anim_stand_gestures_explain_6",
        "name": "Explain 6",
        "description": "Play Explain_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_6"},
    },
    {
        "id": "anim_stand_gestures_explain_7",
        "name": "Explain 7",
        "description": "Play Explain_7 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_7"},
    },
    {
        "id": "anim_stand_gestures_explain_8",
        "name": "Explain 8",
        "description": "Play Explain_8 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Explain_8"},
    },
    {
        "id": "anim_stand_gestures_hey_1",
        "name": "Hey 1",
        "description": "Play Hey_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Hey_1"},
    },
    {
        "id": "anim_stand_gestures_hey_6",
        "name": "Hey 6",
        "description": "Play Hey_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Hey_6"},
    },
    {
        "id": "anim_stand_gestures_idontknow_1",
        "name": "IDontKnow 1",
        "description": "Play IDontKnow_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/IDontKnow_1"},
    },
    {
        "id": "anim_stand_gestures_idontknow_2",
        "name": "IDontKnow 2",
        "description": "Play IDontKnow_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/IDontKnow_2"},
    },
    {
        "id": "anim_stand_gestures_me_1",
        "name": "Me 1",
        "description": "Play Me_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Me_1"},
    },
    {
        "id": "anim_stand_gestures_me_2",
        "name": "Me 2",
        "description": "Play Me_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Me_2"},
    },
    {
        "id": "anim_stand_gestures_no_3",
        "name": "No 3",
        "description": "Play No_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/No_3"},
    },
    {
        "id": "anim_stand_gestures_no_8",
        "name": "No 8",
        "description": "Play No_8 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/No_8"},
    },
    {
        "id": "anim_stand_gestures_no_9",
        "name": "No 9",
        "description": "Play No_9 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/No_9"},
    },
    {
        "id": "anim_stand_gestures_please_1",
        "name": "Please 1",
        "description": "Play Please_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Please_1"},
    },
    {
        "id": "anim_stand_gestures_yes_1",
        "name": "Yes 1",
        "description": "Play Yes_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Yes_1"},
    },
    {
        "id": "anim_stand_gestures_yes_2",
        "name": "Yes 2",
        "description": "Play Yes_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Yes_2"},
    },
    {
        "id": "anim_stand_gestures_yes_3",
        "name": "Yes 3",
        "description": "Play Yes_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Yes_3"},
    },
    {
        "id": "anim_stand_gestures_youknowwhat_1",
        "name": "YouKnowWhat 1",
        "description": "Play YouKnowWhat_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/YouKnowWhat_1"},
    },
    {
        "id": "anim_stand_gestures_youknowwhat_5",
        "name": "YouKnowWhat 5",
        "description": "Play YouKnowWhat_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/YouKnowWhat_5"},
    },
    {
        "id": "anim_stand_gestures_you_1",
        "name": "You 1",
        "description": "Play You_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/You_1"},
    },
    {
        "id": "anim_stand_gestures_you_4",
        "name": "You 4",
        "description": "Play You_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/You_4"},
    },
]

# Fast lookup by catalog id; aliases (names, posture labels) go through _EXPRESSION_ALIASES.
_EXPRESSION_BY_ID: dict[str, dict[str, Any]] = {
    entry["id"]: entry for entry in NAO_EXPRESSIONS
}


def _normalize_nao_animation_path(animation_path: str) -> str:
    """
    NAOqi requires package/path (e.g. animations/Stand/Gestures/Hey_1).

    Short names like Enthusiastic_4 fail on many images with "Wrong path format".
    """
    path = (animation_path or "").strip()
    if not path:
        raise ValueError("animation_path must be non-empty.")
    if "/" in path:
        return path
    return "animations/Stand/Gestures/{}".format(path)


def _build_expression_aliases() -> dict[str, str]:
    """Map common agent/user labels to catalog id values."""
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

    play_expression contract (NAO):

    - Required: expression_id, one of the id values in expressions.
    - Optional: speed (float), overrides posture transition speed for kind=posture only.
    """
    return build_catalog(
        robot_type=ROBOT_TYPE,
        catalog_version=CATALOG_VERSION,
        expressions=list(NAO_EXPRESSIONS),
        play_expression={
            "description": (
                "Play a catalogued expression on the robot. Pass expression_id; "
                "for postures you may override speed (0.0-1.0)."
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
            "NAO default animation list: "
            "http://doc.aldebaran.com/2-1/naoqi/audio/alanimatedspeech_advanced.html#nao-robon-list-of-animations-available-by-default",
            "Postures: http://doc.aldebaran.com/2-4/family/robots/postures_robot.html",
        ],
    )


def get_expressions_json(*, indent: int = 2) -> str:
    """Serialize the catalog for MCP tool responses."""
    return catalog_to_json(get_expressions_catalog(), indent=indent)


def resolve_expression(expression_id: str) -> dict[str, Any]:
    """Look up a catalog entry or raise KeyError."""
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
    Play one catalogued expression via nao.motion.

    :param nao: Connected Nao device (ignored when stub is True).
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
        try:
            # Block so NAOqi errors (e.g. invalid BodyTalk paths) reach the MCP client.
            motion.request(NaoqiAnimationRequest(path), block=True, timeout=60.0)
        except Exception as exc:
            return f"ERROR: Failed to play animation {path!r}: {exc!r}"
        msg = f"NAO animation {path!r} (played)."
    else:
        raise ValueError(f"Unsupported expression kind {kind!r} for NAO.")

    if logger is not None:
        logger.info("Expression %s: %s", expression_id, msg)
    return msg
