"""
Pepper expression catalog and playback for MCP servers.
"""

from __future__ import annotations

from typing import Any, Optional

from sic_framework.devices.common_naoqi.naoqi_motion import (
    NaoqiAnimationRequest,
    PepperPostureRequest,
)
from sic_framework.mcp.expression_catalog import build_catalog, catalog_to_json

CATALOG_VERSION = 1
ROBOT_TYPE = "pepper"

PEPPER_EXPRESSIONS: list[dict[str, Any]] = [
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
        "id": "posture_stand_zero",
        "name": "StandZero",
        "description": "Go to stand-zero posture.",
        "kind": "posture",
        "default_args": {"target_posture": "StandZero", "speed": 0.4},
    },
    {
        "id": "posture_crouch",
        "name": "Crouch",
        "description": "Crouch posture.",
        "kind": "posture",
        "default_args": {"target_posture": "Crouch", "speed": 0.4},
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
        "id": "anim_stand_bodytalk_bodytalk_2",
        "name": "BodyTalk 2",
        "description": "Play BodyTalk_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/BodyTalk/BodyTalk_2"},
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
        "id": "anim_stand_emotions_negative_bored_1",
        "name": "Bored 1",
        "description": "Play Bored_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Emotions/Negative/Bored_1"},
    },
    {
        "id": "anim_stand_emotions_neutral_embarrassed_1",
        "name": "Embarrassed 1",
        "description": "Play Embarrassed_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Emotions/Neutral/Embarrassed_1"},
    },
    {
        "id": "anim_stand_emotions_positive_happy_4",
        "name": "Happy 4",
        "description": "Play Happy_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Emotions/Positive/Happy_4"},
    },
    {
        "id": "anim_stand_emotions_positive_hysterical_1",
        "name": "Hysterical 1",
        "description": "Play Hysterical_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Emotions/Positive/Hysterical_1"},
    },
    {
        "id": "anim_stand_emotions_positive_peaceful_1",
        "name": "Peaceful 1",
        "description": "Play Peaceful_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Emotions/Positive/Peaceful_1"},
    },
    {
        "id": "anim_stand_gestures_bowshort_1",
        "name": "BowShort 1",
        "description": "Play BowShort_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/BowShort_1"},
    },
    {
        "id": "anim_stand_gestures_but_1",
        "name": "But 1",
        "description": "Play But_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/But_1"},
    },
    {
        "id": "anim_stand_gestures_calmdown_1",
        "name": "CalmDown 1",
        "description": "Play CalmDown_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/CalmDown_1"},
    },
    {
        "id": "anim_stand_gestures_calmdown_5",
        "name": "CalmDown 5",
        "description": "Play CalmDown_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/CalmDown_5"},
    },
    {
        "id": "anim_stand_gestures_calmdown_6",
        "name": "CalmDown 6",
        "description": "Play CalmDown_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/CalmDown_6"},
    },
    {
        "id": "anim_stand_gestures_choice_1",
        "name": "Choice 1",
        "description": "Play Choice_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Choice_1"},
    },
    {
        "id": "anim_stand_gestures_desperate_1",
        "name": "Desperate 1",
        "description": "Play Desperate_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Desperate_1"},
    },
    {
        "id": "anim_stand_gestures_desperate_2",
        "name": "Desperate 2",
        "description": "Play Desperate_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Desperate_2"},
    },
    {
        "id": "anim_stand_gestures_desperate_4",
        "name": "Desperate 4",
        "description": "Play Desperate_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Desperate_4"},
    },
    {
        "id": "anim_stand_gestures_desperate_5",
        "name": "Desperate 5",
        "description": "Play Desperate_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Desperate_5"},
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
        "id": "anim_stand_gestures_everything_1",
        "name": "Everything 1",
        "description": "Play Everything_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Everything_1"},
    },
    {
        "id": "anim_stand_gestures_everything_2",
        "name": "Everything 2",
        "description": "Play Everything_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Everything_2"},
    },
    {
        "id": "anim_stand_gestures_everything_3",
        "name": "Everything 3",
        "description": "Play Everything_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Everything_3"},
    },
    {
        "id": "anim_stand_gestures_everything_4",
        "name": "Everything 4",
        "description": "Play Everything_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Everything_4"},
    },
    {
        "id": "anim_stand_gestures_excited_1",
        "name": "Excited 1",
        "description": "Play Excited_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Excited_1"},
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
        "id": "anim_stand_gestures_far_1",
        "name": "Far 1",
        "description": "Play Far_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Far_1"},
    },
    {
        "id": "anim_stand_gestures_far_2",
        "name": "Far 2",
        "description": "Play Far_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Far_2"},
    },
    {
        "id": "anim_stand_gestures_far_3",
        "name": "Far 3",
        "description": "Play Far_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Far_3"},
    },
    {
        "id": "anim_stand_gestures_give_3",
        "name": "Give 3",
        "description": "Play Give_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Give_3"},
    },
    {
        "id": "anim_stand_gestures_give_4",
        "name": "Give 4",
        "description": "Play Give_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Give_4"},
    },
    {
        "id": "anim_stand_gestures_give_5",
        "name": "Give 5",
        "description": "Play Give_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Give_5"},
    },
    {
        "id": "anim_stand_gestures_give_6",
        "name": "Give 6",
        "description": "Play Give_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Give_6"},
    },
    {
        "id": "anim_stand_gestures_hey_1",
        "name": "Hey 1",
        "description": "Play Hey_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Hey_1"},
    },
    {
        "id": "anim_stand_gestures_hey_3",
        "name": "Hey 3",
        "description": "Play Hey_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Hey_3"},
    },
    {
        "id": "anim_stand_gestures_hey_4",
        "name": "Hey 4",
        "description": "Play Hey_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Hey_4"},
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
        "id": "anim_stand_gestures_idontknow_3",
        "name": "IDontKnow 3",
        "description": "Play IDontKnow_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/IDontKnow_3"},
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
        "id": "anim_stand_gestures_me_4",
        "name": "Me 4",
        "description": "Play Me_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Me_4"},
    },
    {
        "id": "anim_stand_gestures_me_7",
        "name": "Me 7",
        "description": "Play Me_7 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Me_7"},
    },
    {
        "id": "anim_stand_gestures_no_1",
        "name": "No 1",
        "description": "Play No_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/No_1"},
    },
    {
        "id": "anim_stand_gestures_no_2",
        "name": "No 2",
        "description": "Play No_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/No_2"},
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
        "id": "anim_stand_gestures_nothing_2",
        "name": "Nothing 2",
        "description": "Play Nothing_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Nothing_2"},
    },
    {
        "id": "anim_stand_gestures_please_1",
        "name": "Please 1",
        "description": "Play Please_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Please_1"},
    },
    {
        "id": "anim_stand_gestures_showfloor_1",
        "name": "ShowFloor 1",
        "description": "Play ShowFloor_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowFloor_1"},
    },
    {
        "id": "anim_stand_gestures_showfloor_3",
        "name": "ShowFloor 3",
        "description": "Play ShowFloor_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowFloor_3"},
    },
    {
        "id": "anim_stand_gestures_showfloor_4",
        "name": "ShowFloor 4",
        "description": "Play ShowFloor_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowFloor_4"},
    },
    {
        "id": "anim_stand_gestures_showsky_1",
        "name": "ShowSky 1",
        "description": "Play ShowSky_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_1"},
    },
    {
        "id": "anim_stand_gestures_showsky_11",
        "name": "ShowSky 11",
        "description": "Play ShowSky_11 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_11"},
    },
    {
        "id": "anim_stand_gestures_showsky_2",
        "name": "ShowSky 2",
        "description": "Play ShowSky_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_2"},
    },
    {
        "id": "anim_stand_gestures_showsky_4",
        "name": "ShowSky 4",
        "description": "Play ShowSky_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_4"},
    },
    {
        "id": "anim_stand_gestures_showsky_5",
        "name": "ShowSky 5",
        "description": "Play ShowSky_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_5"},
    },
    {
        "id": "anim_stand_gestures_showsky_6",
        "name": "ShowSky 6",
        "description": "Play ShowSky_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_6"},
    },
    {
        "id": "anim_stand_gestures_showsky_7",
        "name": "ShowSky 7",
        "description": "Play ShowSky_7 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_7"},
    },
    {
        "id": "anim_stand_gestures_showsky_8",
        "name": "ShowSky 8",
        "description": "Play ShowSky_8 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_8"},
    },
    {
        "id": "anim_stand_gestures_showsky_9",
        "name": "ShowSky 9",
        "description": "Play ShowSky_9 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowSky_9"},
    },
    {
        "id": "anim_stand_gestures_showtablet_2",
        "name": "ShowTablet 2",
        "description": "Play ShowTablet_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowTablet_2"},
    },
    {
        "id": "anim_stand_gestures_showtablet_3",
        "name": "ShowTablet 3",
        "description": "Play ShowTablet_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/ShowTablet_3"},
    },
    {
        "id": "anim_stand_gestures_thinking_1",
        "name": "Thinking 1",
        "description": "Play Thinking_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Thinking_1"},
    },
    {
        "id": "anim_stand_gestures_thinking_3",
        "name": "Thinking 3",
        "description": "Play Thinking_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Thinking_3"},
    },
    {
        "id": "anim_stand_gestures_thinking_4",
        "name": "Thinking 4",
        "description": "Play Thinking_4 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Thinking_4"},
    },
    {
        "id": "anim_stand_gestures_thinking_6",
        "name": "Thinking 6",
        "description": "Play Thinking_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Thinking_6"},
    },
    {
        "id": "anim_stand_gestures_thinking_8",
        "name": "Thinking 8",
        "description": "Play Thinking_8 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/Thinking_8"},
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
        "id": "anim_stand_gestures_youknowwhat_2",
        "name": "YouKnowWhat 2",
        "description": "Play YouKnowWhat_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/YouKnowWhat_2"},
    },
    {
        "id": "anim_stand_gestures_youknowwhat_3",
        "name": "YouKnowWhat 3",
        "description": "Play YouKnowWhat_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/YouKnowWhat_3"},
    },
    {
        "id": "anim_stand_gestures_youknowwhat_5",
        "name": "YouKnowWhat 5",
        "description": "Play YouKnowWhat_5 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/YouKnowWhat_5"},
    },
    {
        "id": "anim_stand_gestures_youknowwhat_6",
        "name": "YouKnowWhat 6",
        "description": "Play YouKnowWhat_6 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Gestures/YouKnowWhat_6"},
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
    {
        "id": "anim_stand_waiting_showsky_1",
        "name": "ShowSky 1",
        "description": "Play ShowSky_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Waiting/ShowSky_1"},
    },
    {
        "id": "anim_stand_waiting_showsky_2",
        "name": "ShowSky 2",
        "description": "Play ShowSky_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Waiting/ShowSky_2"},
    },
    {
        "id": "anim_stand_waiting_think_1",
        "name": "Think 1",
        "description": "Play Think_1 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Waiting/Think_1"},
    },
    {
        "id": "anim_stand_waiting_think_2",
        "name": "Think 2",
        "description": "Play Think_2 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Waiting/Think_2"},
    },
    {
        "id": "anim_stand_waiting_think_3",
        "name": "Think 3",
        "description": "Play Think_3 animation.",
        "kind": "animation",
        "default_args": {"animation_path": "animations/Stand/Waiting/Think_3"},
    },
]

_EXPRESSION_BY_ID: dict[str, dict[str, Any]] = {
    entry["id"]: entry for entry in PEPPER_EXPRESSIONS
}


def _normalize_animation_path(animation_path: str) -> str:
    path = (animation_path or "").strip()
    if not path:
        raise ValueError("animation_path must be non-empty.")
    if "/" in path:
        return path
    return "animations/Stand/Gestures/{}".format(path)


def _build_expression_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for entry in PEPPER_EXPRESSIONS:
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
    return build_catalog(
        robot_type=ROBOT_TYPE,
        catalog_version=CATALOG_VERSION,
        expressions=list(PEPPER_EXPRESSIONS),
        play_expression={
            "description": (
                "Play a catalogued expression on Pepper. Pass expression_id; "
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
                "sic_request": "PepperPostureRequest",
                "args": ["target_posture", "speed"],
            },
            "animation": {
                "sic_request": "NaoqiAnimationRequest",
                "args": ["animation_path"],
            },
        },
        notes=[
            "Pepper default animation list: "
            "http://doc.aldebaran.com/2-1/naoqi/audio/alanimatedspeech_advanced.html#juju-roboj-list-of-animations-available-by-default",
            "Pepper postures supported by SIC: Crouch, Stand, StandInit, StandZero.",
        ],
    )


def get_expressions_json(*, indent: int = 2) -> str:
    return catalog_to_json(get_expressions_catalog(), indent=indent)


def resolve_expression(expression_id: str) -> dict[str, Any]:
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


def play_pepper_expression(
    pepper: Any,
    expression_id: str,
    *,
    speed: Optional[float] = None,
    stub: bool = False,
    logger: Any = None,
) -> str:
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

    if pepper is None:
        raise RuntimeError("Pepper device is not connected.")

    motion = pepper.motion
    if kind == "posture":
        target = args["target_posture"]
        posture_speed = args.get("speed", 0.4)
        motion.request(PepperPostureRequest(target, posture_speed))
        msg = f"Pepper posture {target!r} (speed={posture_speed:.2f})."
    elif kind == "animation":
        path = _normalize_animation_path(args["animation_path"])
        try:
            motion.request(NaoqiAnimationRequest(path), block=True, timeout=60.0)
        except Exception as exc:
            return f"ERROR: Failed to play animation {path!r}: {exc!r}"
        msg = f"Pepper animation {path!r} (played)."
    else:
        raise ValueError(f"Unsupported expression kind {kind!r} for Pepper.")

    if logger is not None:
        logger.info("Expression %s: %s", expression_id, msg)
    return msg
