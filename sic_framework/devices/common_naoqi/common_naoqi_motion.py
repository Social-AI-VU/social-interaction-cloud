class NaoqiMotionTools(object):
    """
    Provides utility functions for handling NAOqi robot motion models.

    :ivar str robot_type: Type of robot, either 'nao' or 'pepper'.
    """

    def __init__(self, qi_session):
        """
        Initialize the motion tools by determining the robot type.

        :param qi.Session qi_session: A qi.Session() instance used to determine robot type.
        :raises NotImplementedError: If the robot type is not supported.
        """

        robot_model_service = qi_session.service("ALRobotModel")
        if robot_model_service.getRobotType() == "Nao":
            self.robot_type = "nao"
        elif robot_model_service.getRobotType() == "Juliette":
            self.robot_type = "pepper"
        else:
            raise NotImplementedError("Romeo is not supported")

    def generate_joint_list(self, joint_chains):
        """
        Generate a flat list of valid joints for a given robot based on input joint chains.

        :param list[str] joint_chains: List of joint chains or individual joints to resolve.
        :returns: A flat list of valid joint names for the current robot.
        :rtype: list[str]
        :raises ValueError: If a provided joint or chain is not recognized.
        """
        joints = []
        for joint_chain in joint_chains:
            if joint_chain == "Body":
                joints += self.all_joints
            elif not joint_chain == "Body" and joint_chain in self.body_model.keys():
                joints += self.body_model[joint_chain]
            elif (
                joint_chain not in self.body_model.keys()
                and joint_chain in self.all_joints
            ):
                joints.append(joint_chain)
            else:
                raise ValueError("Joint {} not recognized.".format(joint_chain))
        return joints

    @property
    def body_model(self):
        """
        Retrieve the mapping of joint chains to their respective joints for the current robot.

        For more information, see robot documentation:
        - Nao: http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains
        - Pepper: http://doc.aldebaran.com/2-8/family/pepper_technical/bodyparts_pep.html

        :returns: Dictionary of joint chains and their associated joints.
        :rtype: dict[str, list[str]]
        """
        body_model = {
            "nao": {
                "Body": ["Head", "LArm", "LLeg", "RLeg", "RArm"],
                "Head": ["HeadYaw", "HeadPitch"],
                "LArm": [
                    "LShoulderPitch",
                    "LShoulderRoll",
                    "LElbowYaw",
                    "LElbowRoll",
                    "LWristYaw",
                    "LHand",
                ],
                "LLeg": [
                    "LHipYawPitch",
                    "LHipRoll",
                    "LHipPitch",
                    "LKneePitch",
                    "LAnklePitch",
                    "LAnkleRoll",
                ],
                "RLeg": [
                    "RHipYawPitch",
                    "RHipRoll",
                    "RHipPitch",
                    "RKneePitch",
                    "RAnklePitch",
                    "RAnkleRoll",
                ],
                "RArm": [
                    "RShoulderPitch",
                    "RShoulderRoll",
                    "RElbowYaw",
                    "RElbowRoll",
                    "RWristYaw",
                    "RHand",
                ],
            },
            "pepper": {
                "Body": ["Head", "LArm", "Leg", "RArm"],
                "Head": ["HeadYaw", "HeadPitch"],
                "LArm": [
                    "LShoulderPitch",
                    "LShoulderRoll",
                    "LElbowYaw",
                    "LElbowRoll",
                    "LWristYaw",
                    "LHand",
                ],
                "Leg": ["HipRoll", "HipPitch", "KneePitch"],
                "RArm": [
                    "RShoulderPitch",
                    "RShoulderRoll",
                    "RElbowYaw",
                    "RElbowRoll",
                    "RWristYaw",
                    "RHand",
                ],
            },
        }
        return body_model[self.robot_type]

    @property
    def all_joints(self):
        """
        Retrieve all joints available for the current robot.

        :returns: List of all joint names.
        :rtype: list[str]
        """
        all_joints = []
        for chain in self.body_model["Body"]:
            all_joints += self.body_model[chain]
        return all_joints
