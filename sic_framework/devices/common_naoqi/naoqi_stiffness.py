import numpy as np
import six

from sic_framework import SICComponentManager, SICService, utils
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.devices.common_naoqi.common_naoqi_motion import NaoqiMotionTools

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class Stiffness(SICRequest):
    def __init__(self, stiffness=0.7, joints="Body", enable_joint_list_generation=True):
        """
        Initialize a stiffness control request.

        Controls how strongly the robot maintains commanded joint angles.

        For more information, see:
        - Nao: http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains
        - Pepper: http://doc.aldebaran.com/2-8/family/pepper_technical/bodyparts_pep.html

        :param float stiffness: Stiffness level to set in [0, 1].
        :param list[str] joints: Joint or joint chain names (e.g., ["Body"], ["HeadYaw", LArm]).
        :param bool enable_joint_list_generation: If True, joint lists are automatically expanded from chains.
        """
        super(Stiffness, self).__init__()
        self.stiffness = stiffness
        self.joints = joints
        self.enable_joint_list_generation = enable_joint_list_generation


class NaoqiStiffnessActuator(SICActuator, NaoqiMotionTools):
    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        NaoqiMotionTools.__init__(self, qi_session=self.session)

        self.motion = self.session.service("ALMotion")

        # According to the API you should not set stiffness on these joints. The call fails silently if you do.
        self.forbidden_pepper_joints = (
            {"Leg", "HipRoll", "HipPitch", "KneePitch"}
            if self.robot_type == "pepper"
            else set()
        )

    @staticmethod
    def get_inputs():
        return [Stiffness]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        if request.enable_joint_list_generation:
            joints = self.generate_joint_list(request.joints)
        else:
            joints = request.joints

        self.logger.info("joint list {}".format(joints))

        if len(self.forbidden_pepper_joints.intersection(joints)):
            raise ValueError("Stiffness should not be set on leg joints on pepper.")

        self.motion.setStiffnesses(joints, request.stiffness)
        return SICMessage()

    def stop(self, *args):
        """
        Stop the NAOqi stiffness actuator.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiStiffnessActuator, self).stop()


class NaoqiStiffness(SICConnector):
    component_class = NaoqiStiffnessActuator


if __name__ == "__main__":
    SICComponentManager([NaoqiStiffnessActuator])
