"""

"""


class MotionAffectTransformation:
    """
    Apply affect-based transformations to NAOqi motion dictionaries.

    The methods adjust amplitude, timing, posture, and enforce joint limits based on valence/arousal or emotion labels.
    """

    def transform_values(self, motion, valence, arousal):
        """
        Transform a motion by applying flow, time, and weight changes based on valence and arousal.

        :param dict motion: Motion dictionary with the shape `{ "motion": { joint_name: {"angles": list[float], "times": list[float]} } }`.
        :param float valence: Valence value in [-1, 1] influencing amplitude and posture.
        :param float arousal: Arousal value in [-1, 1] influencing repetition and speed.
        :returns: The transformed motion dictionary.
        :rtype: dict
        """
        motion = self.modify_flow_parameters(motion, valence)
        motion = self.modify_time_parameters(motion, arousal)
        motion = self.modify_weight_parameters(motion, valence, arousal)
        return self.angle_limit(motion)

    def transform_label(self, motion, emotion_label):
        """
        Transform a motion by first mapping an emotion label to valence/arousal values.

        :param dict motion: Motion dictionary to transform.
        :param str emotion_label: Discrete emotion label (e.g., "happy", "sad", "angry").
        :returns: The transformed motion dictionary.
        :rtype: dict
        """
        valence, arousal = self.values_from_emotion(emotion_label)
        return self.transform_values(motion, valence, arousal)

    def angle_limit(self, motion):
        """
        Clamp joint angles to the robot's physical limits.

        :param dict motion: Motion dictionary to validate and clamp.
        :returns: The motion dictionary with angles limited to valid ranges.
        :rtype: dict
        """
        for jointName in motion["motion"].keys():
            if jointName not in self.hand_joints and jointName not in self.leg_joints:
                minimum, maximum = self.limit_check(jointName)
                for angle in motion["motion"][jointName]["angles"]:
                    index = motion["motion"][jointName]["angles"].index(angle)
                    print(angle)
                    if angle < minimum:
                        new_angle = minimum
                        print(
                            jointName,
                            ": ",
                            angle,
                            " is smaller than ",
                            minimum,
                            " so changed to ",
                            new_angle,
                        )
                        motion["motion"][jointName]["angles"][index] = new_angle
                    elif angle > maximum:
                        new_angle = maximum
                        print(
                            jointName,
                            ": ",
                            angle,
                            " is larger than ",
                            maximum,
                            " so changed to ",
                            new_angle,
                        )
                        motion["motion"][jointName]["angles"][index] = new_angle
                    else:
                        pass

            pass

        return motion

    def modify_flow_parameters(self, motion, valence):
        """
        Adjust motion amplitudes and blend towards a linear trajectory based on valence.

        :param dict motion: Motion dictionary to modify.
        :param float valence: Valence value affecting amplitude (positive increases, negative slightly decreases).
        :returns: The updated motion dictionary.
        :rtype: dict
        """
        amplitude = self.amplitude(valence)
        pivot_states = self.pivot_states(motion, self.leg_joints)
        theta_init = pivot_states[0]
        theta_end = pivot_states[-1]

        for jointName in motion["motion"].keys():
            if jointName not in self.leg_joints:
                for i in range(0, len(motion["motion"][jointName]["times"])):
                    normalized_time = (
                        motion["motion"][jointName]["times"][i]
                        - motion["motion"][jointName]["times"][0]
                    ) / (
                        motion["motion"][jointName]["times"][-1]
                        - motion["motion"][jointName]["times"][0]
                        + 1
                    )
                    line_angle = (
                        theta_init * (1 - normalized_time) + theta_end * normalized_time
                    )
                    motion["motion"][jointName]["angles"][i] = (
                        amplitude * motion["motion"][jointName]["angles"][i]
                        + (1 - amplitude) * line_angle
                    )
            return motion

    def modify_time_parameters(self, motion, arousal):
        """
        Adjust repetition (implicit via angle scaling) and speed (time scaling) based on arousal.

        :param dict motion: Motion dictionary to modify.
        :param float arousal: Arousal value affecting repetition and speed.
        :returns: The updated motion dictionary.
        :rtype: dict
        """
        repetitions = self.repetition(arousal)
        for jointName in motion["motion"].keys():
            if jointName not in self.leg_joints:
                angles = []
                for angle in motion["motion"][jointName]["angles"]:
                    angle = angle * (repetitions + 1)
                    angles.append(angle)
                motion["motion"][jointName]["angles"] = angles

        speed = self.speed(arousal)
        for jointName in motion["motion"].keys():
            if jointName not in self.leg_joints:
                times = []
                for time in motion["motion"][jointName]["times"]:
                    time = time * float(speed)
                    times.append(time)
                motion["motion"][jointName]["times"] = times
        return motion

    def modify_weight_parameters(self, motion, valence, arousal):
        """
        Add or adjust posture-related joints (e.g., head pitch) based on valence and arousal.

        :param dict motion: Motion dictionary to modify.
        :param float valence: Valence value influencing posture.
        :param float arousal: Arousal value influencing posture and added joints.
        :returns: The updated motion dictionary.
        :rtype: dict
        """
        head_pose = self.head_pose(valence, arousal)
        first_joint = list(motion["motion"].keys())[0]
        start_time = motion["motion"][first_joint]["times"][0]

        if "HeadPitch" not in motion["motion"].keys():
            motion["motion"]["HeadPitch"] = {
                "angles": [head_pose, head_pose],
                "times": [0, start_time],
            }
        else:
            motion["motion"]["HeadPitch"]["angles"] = [
                (head_pose + x) for x in motion["motion"]["HeadPitch"]["angles"]
            ]

        if arousal < -0.5:
            for jointName in self.bend:
                if jointName not in self.leg_joints:
                    if jointName not in motion["motion"]:
                        motion["motion"][jointName] = {
                            "angles": [self.bend[jointName], self.bend[jointName]],
                            "times": [0, start_time],
                        }

        elif arousal > 0.5:
            for jointName in self.upright:
                if jointName not in self.leg_joints:
                    if jointName not in motion["motion"]:
                        motion["motion"][jointName] = {
                            "angles": [
                                self.upright[jointName],
                                self.upright[jointName],
                            ],
                            "times": [0, start_time],
                        }
        else:
            for jointName in self.neutral:
                if jointName not in self.leg_joints:
                    if jointName not in motion["motion"]:
                        motion["motion"][jointName] = {
                            "angles": [
                                self.neutral[jointName],
                                self.neutral[jointName],
                            ],
                            "times": [0, start_time],
                        }
        return motion

    @staticmethod
    def pivot_states(motion, ignore_joints):
        """
        Collect unique time points across joints, excluding specified joints.

        :param dict motion: Motion dictionary containing joint time arrays.
        :param list[str] ignore_joints: Joint names to ignore when collecting time points.
        :returns: Sorted unique list of time points.
        :rtype: list[float]
        """
        time_points = []
        for joint_name in motion["motion"].keys():
            if joint_name not in ignore_joints:
                times = motion["motion"][joint_name]["times"]
                for time in times:
                    time_points.append(time)
        return sorted(set(time_points))

    @staticmethod
    def amplitude(valence):
        """
        Map valence to an amplitude scaling factor.

        :param float valence: Valence value in [-1, 1].
        :returns: Amplitude multiplier (>0).
        :rtype: float
        """
        # correlation between amplitude of motion and valence of the affect
        if valence > 0:
            amplitude_factor = 1 + valence
        else:
            amplitude_factor = 1 + 0.5 * valence
        return amplitude_factor

    @staticmethod
    def repetition(arousal):
        """
        Map arousal to a repetition factor. 
        
        Positive arousal increases the factor; non-positive returns 1.

        :param float arousal: Arousal value in [-1, 1].
        :returns: Repetition multiplier (>=1).
        :rtype: float
        """
        # positive arousal is associated with an increase in the repetition of the motion
        # negative arousal does not change the repetition of the motion
        if arousal > 0:
            repetition_factor = 1 + abs(2 * arousal)
        else:
            repetition_factor = 1
        return repetition_factor

    @staticmethod
    def speed(arousal):
        """
        Map arousal to a speed scaling factor for time values.

        :param float arousal: Arousal value in [-1, 1].
        :returns: Speed multiplier (>0).
        :rtype: float
        """
        # speed influences the perceived arousal: increase portrays high arousal,
        # whereas reduction in speed portrays low arousal
        if arousal > 0:
            speed_factor = 1 + arousal
        else:
            speed_factor = 1 - 0.5 * arousal
        return speed_factor

    @staticmethod
    def head_pose(valence, arousal, up=0.506145, down=0.349066):
        """
        Compute a head pitch offset based on valence and arousal.

        :param float valence: Valence value.
        :param float arousal: Arousal value.
        :param float up: Maximum upward pitch in radians.
        :param float down: Maximum downward pitch in radians.
        :returns: Head pitch offset in radians.
        :rtype: float
        """
        # vertical head pose is important for expressing affects in the first and third quadrant
        # pre-defined angels for up and down are set
        #
        if valence < 0 and arousal < 0:
            headpose = -down * valence
        elif valence > 0 and arousal > 0:
            headpose = up * valence
        else:
            headpose = 0
        return headpose

    @property
    def leg_joints(self):
        """
        Retrieve the list of leg joint names.

        :returns: List of leg joint identifiers.
        :rtype: list[str]
        """
        return [
            "LAnklePitch",
            "LAnkleRoll",
            "LHipPitch",
            "LHipRoll",
            "LHipYawPitch",
            "LKneePitch",
            "RAnklePitch",
            "RAnkleRoll",
            "RHipPitch",
            "RHipRoll",
            "RHipYawPitch",
            "RKneePitch",
        ]

    @property
    def hand_joints(self):
        """
        Retrieve the list of hand joint names.

        :returns: List of hand joint identifiers.
        :rtype: list[str]
        """
        return ["LHand", "RHand"]

    @property
    def upright(self):
        """
        Retrieve a posture dictionary for an upright (expanded) stance.

        :returns: Mapping from joint name to target angle in radians.
        :rtype: dict[str, float]
        """
        return {  # also called expanded
            "LHipYawPitch": -0.17,
            "LHipRoll": 0.09,
            "LHipPitch": 0.13,
            "LKneePitch": -0.08,
            "LAnklePitch": 0.08,
            "LAnkleRoll": -0.13,
            "RHipYawPitch": -0.17,
            "RHipRoll": -0.09,
            "RHipPitch": 0.13,
            "RKneePitch": -0.08,
            "RAnklePitch": 0.08,
            "RAnkleRoll": 0.13,
        }

    @property
    def neutral(self):
        """
        Retrieve a posture dictionary for a neutral stance.

        :returns: Mapping from joint name to target angle in radians.
        :rtype: dict[str, float]
        """
        return {
            "LHipYawPitch": 0.0,
            "LHipRoll": 0.0,
            "LHipPitch": 0.0,
            "LKneePitch": 0.0,
            "LAnklePitch": 0.0,
            "LAnkleRoll": 0.0,
            "RHipYawPitch": 0.0,
            "RHipRoll": 0.0,
            "RHipPitch": 0.0,
            "RKneePitch": 0.0,
            "RAnklePitch": 0.0,
            "RAnkleRoll": 0.0,
        }

    @property
    def bend(self):
        """
        Retrieve a posture dictionary for a bent (shrunk) stance.

        :returns: Mapping from joint name to target angle in radians.
        :rtype: dict[str, float]
        """
        return {  # also called shrunk
            "LHipYawPitch": 0.0,
            "LHipRoll": 0.0,
            "LHipPitch": -0.44,
            "LKneePitch": 0.69,
            "LAnklePitch": -0.35,
            "LAnkleRoll": 0.0,
            "RHipYawPitch": 0.0,
            "RHipRoll": 0.0,
            "RHipPitch": -0.44,
            "RKneePitch": 0.69,
            "RAnklePitch": -0.35,
            "RAnkleRoll": 0.0,
        }

    @staticmethod
    def limit_check(joint):
        """
        Look up the minimum and maximum allowed angles for a given joint.

        :param str joint: Joint name to query.
        :returns: Tuple of (minimum, maximum) allowed angles in radians.
        :rtype: tuple[float, float]
        """
        limit_table = {
            "HeadYaw": {"minimum": -2.0857, "maximum": 2.0857},
            "HeadPitch": {"minimum": -0.6720, "maximum": 0.5149},
            "LShoulderPitch": {"minimum": -2.0857, "maximum": 2.0857},
            "LShoulderRoll": {"minimum": -0.3142, "maximum": 1.3265},
            "LElbowYaw": {"minimum": -2.0857, "maximum": 2.0857},
            "LElbowRoll": {"minimum": -1.5446, "maximum": -0.0349},
            "LWristYaw": {"minimum": -1.8238, "maximum": 1.8238},
            "RShoulderPitch": {"minimum": -2.0857, "maximum": 2.0857},
            "RShoulderRoll": {"minimum": 1.3265, "maximum": 0.3142},
            "RElbowYaw": {"minimum": -2.0857, "maximum": 2.0857},
            "RElbowRoll": {"minimum": 0.0349, "maximum": 1.5446},
            "RWristYaw": {"minimum": -1.8238, "maximum": 1.8238},
            "LHipYawPitch": {"minimum": -1.145303, "maximum": 0.740810},
            "RHipYawPitch": {"minimum": -1.145303, "maximum": 0.740810},
            "LHipRoll": {"minimum": -0.379472, "maximum": 0.790477},
            "LHipPitch": {"minimum": -1.535889, "maximum": 0.484090},
            "LKneePitch": {"minimum": -0.092346, "maximum": 2.112528},
            "LAnklePitch": {"minimum": 1.189516, "maximum": 0.922747},
            "LAnkleRoll": {"minimum": -0.397880, "maximum": 0.769001},
            "RHipRoll": {"minimum": -0.790477, "maximum": 0.379472},
            "RHipPitch": {"minimum": -1.535889, "maximum": 0.484090},
            "RKneePitch": {"minimum": -0.103083, "maximum": 2.120198},
            "RAnklePitch": {"minimum": 1.186448, "maximum": 0.932056},
            "RAnkleRoll": {"minimum": -0.768992, "maximum": 0.397880},
        }
        return limit_table[joint]["minimum"], limit_table[joint]["maximum"]

    @staticmethod
    def values_from_emotion(emotion_label):
        """
        Map an emotion label to its (valence, arousal) pair.

        :param str emotion_label: Emotion label key (e.g., "happy", "sad").
        :returns: Tuple containing (valence, arousal).
        :rtype: tuple[float, float]
        """
        value_table = {
            "excited": {"valence": 0.3, "arousal": 0.8},  # oranje
            "happy": {"valence": 0.9, "arousal": 0.3},  # geel
            "pleased": {"valence": 1, "arousal": 0.2},  # lichtguldenroedegeel
            "content": {"valence": 0.95, "arousal": -0.2},  # lichtgeel
            "calm": {"valence": 0.8, "arousal": -0.4},  # lichtgroen
            "relaxed": {"valence": 0.7, "arousal": -0.5},  # ijsblauw
            "sleepy": {"valence": 0, "arousal": -0.8},  # blauwpaars
            "tired": {"valence": -0.4, "arousal": -0.85},  # paars
            "sad": {"valence": -0.7, "arousal": -0.5},  # middenpaars
            "frustrated": {"valence": -0.9, "arousal": 0.3},  # middenroodviolet
            "disgust": {"valence": -0.4, "arousal": 0.6},  # dieproze
            "angry": {"valence": -0.6, "arousal": 0.6},  # donkerrood
            "afraid": {"valence": -0.7, "arousal": 0.8},  # donkergroen
            "neutral": {"valence": 0, "arousal": 0},  # wit
        }

        return (
            value_table[emotion_label]["valence"],
            value_table[emotion_label]["arousal"],
        )
