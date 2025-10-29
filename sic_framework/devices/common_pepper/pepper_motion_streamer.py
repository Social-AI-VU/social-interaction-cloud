import threading
import time

from sic_framework import (
    SICComponentManager,
    SICConfMessage,
    SICMessage,
    SICRequest,
    utils,
)
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.devices.common_naoqi.common_naoqi_motion import NaoqiMotionTools

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class StartStreaming(SICRequest):
    def __init__(self, joints):
        """
        Start streaming the positions of the selected joints. For more information see robot documentation:
        For nao: http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains
        For pepper: http://doc.aldebaran.com/2-8/family/pepper_technical/bodyparts_pep.html


        :param joints: One of the robot's "Joint chains" such as ["Body"] or ["LArm", "HeadYaw"]
        :type joints: list[str]
        """
        super(StartStreaming, self).__init__()
        self.joints = joints


class StopStreaming(SICRequest):
    pass


class SetLockedJointsRequest(SICRequest):
    """Request to set which joints should be locked (maintain stiffness=1.0)."""
    def __init__(self, locked_joints):
        """
        :param locked_joints: List of joint chains that should be locked (e.g., ["LArm", "RArm", "Head"])
        :type locked_joints: list[str]
        """
        super(SetLockedJointsRequest, self).__init__()
        self.locked_joints = locked_joints


class GetLockedJointsRequest(SICRequest):
    """Request to get the current list of locked joints."""
    pass


class ClearLockedJointsRequest(SICRequest):
    """Request to clear all locked joints and their stored angles."""
    pass


class LockedJointsResponse(SICMessage):
    """Response containing the current list of locked joints."""
    def __init__(self, locked_joints):
        self.locked_joints = locked_joints


class PepperMotionStream(SICMessage):
    def __init__(self, joints, angles, velocity):
        self.joints = joints
        self.angles = angles
        self.velocity = velocity


class PepperMotionStreamerConf(SICConfMessage):
    def __init__(
        self,
        stiffness=0.6,
        speed=0.75,
        stream_stiffness=0,
        use_sensors=False,
        samples_per_second=20,
        locked_joints=None,
    ):
        """
        :param stiffness: Control how much power the robot should use to reach the given joint angles
        :param speed: Set the fraction of the maximum speed used to reach the target position.
        :param stream_stiffness: Control the stiffness of the robot when streaming its joint positions.
        Note: Use stiffness, not stream_stiffness,  to control the stiffness of the robot when consuming a stream of
        joint postions.
        :param use_sensors: If true, sensor angles will be returned, otherwise command angles are used.
        :param samples_per_second: How many times per second the joint positions are sampled.
        :param locked_joints: List of joint chains that should maintain stiffness=1.0 (not be set to 0.0 during streaming)
        :type locked_joints: list[str] or None
        """
        SICConfMessage.__init__(self)
        self.stiffness = stiffness
        self.speed = speed
        self.stream_stiffness = stream_stiffness
        self.use_sensors = use_sensors
        self.samples_per_second = samples_per_second
        self.locked_joints = locked_joints or []


class PepperMotionStreamerService(SICComponent, NaoqiMotionTools):
    def __init__(self, *args, **kwargs):
        SICComponent.__init__(self, *args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        NaoqiMotionTools.__init__(self, qi_session=self.session)

        self.motion = self.session.service("ALMotion")

        self.samples_per_second = self.params.samples_per_second

        self.do_streaming = threading.Event()

        # A list of joint names (not chains)
        self.joints = self.generate_joint_list(["Body"])
        
        # Locked joint chains that should maintain stiffness=1.0
        self.locked_joints = list(self.params.locked_joints)
        # Store the angles for locked joints
        self.locked_angles = {}

        # Chain to joint mapping for Pepper
        self.chain_to_joints = {
            "LArm": ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll"],
            "RArm": ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll"],
            "Head": ["HeadYaw", "HeadPitch"]
        }

        self.stream_thread = threading.Thread(target=self.stream_motion)
        self.stream_thread.name = self.get_component_name()
        self.stream_thread.start()

    @staticmethod
    def get_conf():
        return PepperMotionStreamerConf()

    @staticmethod
    def get_inputs():
        return [PepperMotionStream, StartStreaming, StopStreaming, SetLockedJointsRequest, GetLockedJointsRequest, ClearLockedJointsRequest]

    def _get_joints_in_locked_chains(self):
        """Get all individual joints that belong to locked chains."""
        locked_individual_joints = []
        for chain in self.locked_joints:
            if chain in self.chain_to_joints:
                locked_individual_joints.extend(self.chain_to_joints[chain])
        return locked_individual_joints

    def on_request(self, request):
        if request == StartStreaming:
            self.joints = self.generate_joint_list(request.joints)
            self.do_streaming.set()
            return SICMessage()

        if request == StopStreaming:
            self.do_streaming.clear()
            return SICMessage()
            
        if isinstance(request, SetLockedJointsRequest):
            # Get the new list of locked joints
            new_locked_joints = list(request.locked_joints)
            
            # Clear locked angles for joints that are no longer locked
            new_locked_individual_joints = []
            for chain in new_locked_joints:
                if chain in self.chain_to_joints:
                    new_locked_individual_joints.extend(self.chain_to_joints[chain])
            
            # Remove angles for joints that are no longer locked
            for joint in list(self.locked_angles.keys()):
                if joint not in new_locked_individual_joints:
                    del self.locked_angles[joint]
            
            # Update locked joints list
            self.locked_joints = new_locked_joints
            
            # Set stiffness=1.0 for newly locked chains and store their current angles
            if self.locked_joints:
                self.motion.setStiffnesses(self.locked_joints, 1.0)
                # Store current angles for locked joints
                if new_locked_individual_joints:
                    current_angles = self.motion.getAngles(new_locked_individual_joints, self.params.use_sensors)
                    self.locked_angles.update(dict(zip(new_locked_individual_joints, current_angles)))
            return SICMessage()
            
        if isinstance(request, GetLockedJointsRequest):
            return LockedJointsResponse(list(self.locked_joints))
            
        if isinstance(request, ClearLockedJointsRequest):
            self.locked_joints = []
            self.locked_angles = {}
            return SICMessage()

    def on_message(self, message):
        """
        Move the joints and base of the robot according to PepperMotionStream message
        """
        # Get all individual joints that belong to locked chains
        locked_individual_joints = self._get_joints_in_locked_chains()
        
        # Set stiffness for non-locked joints
        non_locked_joints = [j for j in self.joints if j not in locked_individual_joints]
        if non_locked_joints:
            self.motion.setStiffnesses(non_locked_joints, self.params.stiffness)
        
        # Set stiffness for locked chains (chain-level calls that work on Pepper)
        if self.locked_joints:
            self.motion.setStiffnesses(self.locked_joints, 1.0)

        # For locked joints, override the streamed angles with their locked angles
        modified_joints = []
        modified_angles = []
        
        for joint, angle in zip(message.joints, message.angles):
            if joint in self.locked_angles:
                # Use stored locked angle - this will be sent continuously to maintain position
                modified_joints.append(joint)
                modified_angles.append(self.locked_angles[joint])
            else:
                # Use normal streamed angle
                modified_joints.append(joint)
                modified_angles.append(angle)
        
        # Send all angles (locked joints get their frozen angles, others get streamed angles)
        if modified_joints:
            self.motion.setAngles(modified_joints, modified_angles, self.params.speed)

        # also move the base of the robot
        x, y, theta = message.velocity
        self.motion.move(x, y, theta)

    @staticmethod
    def get_output():
        return PepperMotionStream

    def stream_motion(self):
        # Set the stiffness value of a list of joint chain.
        # For Nao joint chains are: Head, RArm, LArm, RLeg, LLeg
        try:

            while not self._signal_to_stop.is_set():

                # check both do_streaming and _signal_to_stop periodically
                self.do_streaming.wait(1)
                if not self.do_streaming.is_set():
                    continue
                
                # Ensure locked chains maintain stiffness=1.0 and store their angles if not already stored
                if self.locked_joints:
                    self.motion.setStiffnesses(self.locked_joints, 1.0)
                    # Store current angles for locked joints if not already stored
                    locked_individual_joints = self._get_joints_in_locked_chains()
                    for joint in locked_individual_joints:
                        if joint not in self.locked_angles:
                            angle = self.motion.getAngles([joint], self.params.use_sensors)[0]
                            self.locked_angles[joint] = angle

                # Get angles for all joints (including locked ones)
                angles = self.motion.getAngles(self.joints, self.params.use_sensors)

                velocity = self.motion.getRobotVelocity()
                
                self.output_message(PepperMotionStream(self.joints, angles, velocity))

                time.sleep(1 / float(self.samples_per_second))
        except Exception as e:
            self.logger.exception(e)
            self.stop()

    def stop(self, *args):
        """
        Stop the Pepper motion streamer.
        """
        self.session.close()
        self._stopped.set()
        super(PepperMotionStreamerService, self).stop()


class PepperMotionStreamer(SICConnector):
    component_class = PepperMotionStreamerService


if __name__ == "__main__":
    SICComponentManager([PepperMotionStreamerService])