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
    """
    Request to start streaming joint positions.
    
    Begins continuous sampling and broadcasting of the specified joint chains'
    positions at the configured sample rate.
    
    :ivar list joints: Joint chains to stream (e.g., ["Body"], ["LArm", "RArm", "Head"]).
    
    See NAOqi documentation for joint chain definitions:
    
    - NAO: http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains
    - Pepper: http://doc.aldebaran.com/2-8/family/pepper_technical/bodyparts_pep.html
    """
    
    def __init__(self, joints):
        """
        Initialize start streaming request.
        
        :param list joints: Joint chain names to stream. Common chains include "Body",
            "Head", "LArm", "RArm", "LLeg", "RLeg" (Pepper has wheels, not legs).
        :type joints: list[str]
        """
        super(StartStreaming, self).__init__()
        self.joints = joints


class StopStreaming(SICRequest):
    """
    Request to stop streaming joint positions.
    
    Halts the continuous sampling and broadcasting of joint positions.
    """
    pass


class SetLockedJointsRequest(SICRequest):
    """
    Request to set which joint chains should be locked.
    
    Locked joints maintain stiffness=1.0 and their angles are frozen, preventing
    motion streaming from changing them. This is useful for puppeteering with
    selective joint locking.
    
    :ivar list locked_joints: Joint chain names to lock (e.g., ["LArm", "RArm"]).
    """
    
    def __init__(self, locked_joints):
        """
        Initialize locked joints request.
        
        :param list locked_joints: Joint chains to lock. Use chain names like
            "LArm", "RArm", "Head" (not individual joint names).
        :type locked_joints: list[str]
        """
        super(SetLockedJointsRequest, self).__init__()
        self.locked_joints = locked_joints


class GetLockedJointsRequest(SICRequest):
    """
    Request to retrieve the current list of locked joint chains.
    
    :returns: LockedJointsResponse containing the currently locked joint chains.
    :rtype: LockedJointsResponse
    """
    pass


class ClearLockedJointsRequest(SICRequest):
    """
    Request to unlock all joints and clear stored locked angles.
    
    Removes all joint locking constraints, allowing full motion streaming control.
    """
    pass


class LockedJointsResponse(SICMessage):
    """
    Response containing the current list of locked joint chains.
    
    :ivar list locked_joints: Currently locked joint chain names.
    """
    
    def __init__(self, locked_joints):
        """
        Initialize locked joints response.
        
        :param list locked_joints: List of currently locked joint chains.
        :type locked_joints: list[str]
        """
        super(LockedJointsResponse, self).__init__()
        self.locked_joints = locked_joints


class PepperMotionStream(SICMessage):
    """
    Message containing Pepper's current joint angles and base velocity.
    
    This message is published by the motion streamer at the configured sample
    rate and contains complete motion state information.
    
    :ivar list joints: List of joint names.
    :ivar list angles: Joint angles in radians, corresponding to joints list.
    :ivar tuple velocity: Base velocity as (vx, vy, vtheta) in (m/s, m/s, rad/s).
    """
    
    def __init__(self, joints, angles, velocity):
        """
        Initialize motion stream message.
        
        :param list joints: Joint names being streamed.
        :type joints: list[str]
        :param list angles: Current angles in radians for each joint.
        :type angles: list[float]
        :param tuple velocity: Robot base velocity (vx, vy, vtheta).
        """
        super(PepperMotionStream, self).__init__()
        self.joints = joints
        self.angles = angles
        self.velocity = velocity


class PepperMotionStreamerConf(SICConfMessage):
    """
    Configuration for Pepper motion streamer component.
    
    Controls the behavior of the motion streamer including stiffness, speed,
    sampling rate, and joint locking configuration.
    
    :ivar float stiffness: Stiffness for consuming motion streams [0.0-1.0].
    :ivar float speed: Speed fraction for reaching target positions [0.0-1.0].
    :ivar float stream_stiffness: Stiffness when producing motion streams [0.0-1.0].
    :ivar bool use_sensors: If True, read sensor angles; if False, read command angles.
    :ivar int samples_per_second: Streaming frequency in Hz.
    :ivar list locked_joints: Initial list of locked joint chains.
    
    .. note::
        - Use ``stiffness`` to control force when Pepper receives motion commands
        - Use ``stream_stiffness`` to control stiffness when Pepper is being moved manually
        - For puppeteering, set stream_stiffness=0.0 on the puppet (source robot)
    """
    
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
        Initialize motion streamer configuration.
        
        :param float stiffness: Motor power for consuming streams [0.0-1.0].
            Higher values provide more force. Defaults to 0.6.
        :param float speed: Movement speed fraction [0.0-1.0]. Defaults to 0.75.
        :param float stream_stiffness: Stiffness when producing streams [0.0-1.0].
            Use 0.0 for manual manipulation. Defaults to 0.
        :param bool use_sensors: Read sensor (True) vs command (False) angles.
            Defaults to False.
        :param int samples_per_second: Streaming rate in Hz. Defaults to 20.
        :param list locked_joints: Joint chains to lock with stiffness=1.0.
            These joints won't be affected by incoming motion streams. Defaults to None.
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
    """
    Service component for Pepper motion streaming.
    
    Provides bidirectional motion streaming capabilities:
    
    - Produces motion streams by reading Pepper's joint angles and velocity
    - Consumes motion streams by setting Pepper's joints to received angles
    - Supports selective joint locking for advanced control scenarios
    
    This component runs a background thread that continuously samples joint
    positions at the configured rate when streaming is active. It can also
    receive and execute motion commands from external sources.
    
    The component handles both joint-level control and base movement, making
    it suitable for full-body teleoperation and puppeteering applications.
    
    .. note::
        All operations are thread-safe, with proper synchronization between
        the streaming thread and request handlers.
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialize the motion streamer service.
        
        Sets up NAOqi session, motion service, joint mappings, and starts the
        background streaming thread.
        
        :param args: Variable length argument list passed to parent.
        :param kwargs: Arbitrary keyword arguments passed to parent.
        """
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
        """
        Get default configuration for this component.
        
        :returns: Default configuration instance.
        :rtype: PepperMotionStreamerConf
        """
        return PepperMotionStreamerConf()

    @staticmethod
    def get_inputs():
        """
        Get list of input message types this component accepts.
        
        :returns: List of accepted message types including motion streams and control requests.
        :rtype: list
        """
        return [PepperMotionStream, StartStreaming, StopStreaming, SetLockedJointsRequest, GetLockedJointsRequest, ClearLockedJointsRequest]

    def _get_joints_in_locked_chains(self):
        """
        Get all individual joint names that belong to locked chains.
        
        Expands locked chain names (e.g., "LArm") into their constituent joint
        names (e.g., ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll"]).
        
        :returns: Individual joint names in locked chains.
        :rtype: list[str]
        """
        locked_individual_joints = []
        for chain in self.locked_joints:
            if chain in self.chain_to_joints:
                locked_individual_joints.extend(self.chain_to_joints[chain])
        return locked_individual_joints

    def on_request(self, request):
        """
        Handle control requests for the motion streamer.
        
        Processes various request types to control streaming behavior and
        manage joint locking state.
        
        :param request: The incoming request (StartStreaming, StopStreaming,
            SetLockedJointsRequest, GetLockedJointsRequest, or ClearLockedJointsRequest).
        :returns: Acknowledgment or response data.
        :rtype: SICMessage or LockedJointsResponse
        """
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
        Execute motion from incoming PepperMotionStream message.
        
        Applies the received joint angles and base velocity to the robot,
        respecting locked joint constraints. Locked joints maintain their
        stored angles instead of following the stream.
        
        The method:
        
        1. Sets appropriate stiffness for locked vs non-locked joints
        2. Overrides locked joint angles with stored values
        3. Applies joint angles at configured speed
        4. Executes base movement with received velocity
        
        :param PepperMotionStream message: Motion stream containing joint angles
            and base velocity to apply.
        
        .. note::
            Locked joints are set to stiffness=1.0 and maintain their frozen
            angles, while non-locked joints follow the incoming stream.
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
        """
        Get the output message type this component produces.
        
        :returns: PepperMotionStream class.
        :rtype: type
        """
        return PepperMotionStream

    def stream_motion(self):
        """
        Background thread for continuous motion streaming.
        
        Runs in a separate thread, continuously sampling joint angles and robot
        velocity at the configured rate when streaming is active. Publishes
        :class:`PepperMotionStream` messages containing the current robot state.
        
        The thread:
        
        1. Waits for streaming to be enabled (StartStreaming request)
        2. Ensures locked joints maintain stiffness=1.0
        3. Captures current angles for all joints (including locked ones)
        4. Reads robot base velocity
        5. Publishes complete motion state
        6. Sleeps to maintain configured sample rate
        
        .. note::
            **Thread Lifecycle**: Started in ``__init__()``, runs until component is stopped
            via ``_signal_to_stop``. Uses ``do_streaming`` event to pause/resume without
            destroying the thread.
            
            **Error Handling**: Logs exceptions and triggers component shutdown on critical errors.
            
            **Locked Joints**: Locked joints have their angles captured and stored on first
            sample after locking. These frozen angles are included in the stream to maintain
            locked positions on consumer robots.
        """
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
        Stop the motion streamer and clean up resources.
        
        Closes the NAOqi session, stops the streaming thread, and performs
        cleanup of parent components.
        
        :param args: Variable length argument list (unused).
        """
        self.session.close()
        self._stopped.set()
        super(PepperMotionStreamerService, self).stop()


class PepperMotionStreamer(SICConnector):
    """
    Connector for accessing Pepper's motion streaming capabilities.
    
    Provides a high-level interface to the :class:`PepperMotionStreamerService` component.
    Access this through the Pepper device's ``motion_streaming()`` method.
    
    This connector supports both producing and consuming motion streams, enabling
    bidirectional teleoperation and puppeteering scenarios.
    
    Example usage::
    
        # Simple streaming:
        pepper.motion_streaming().request(StartStreaming(["Head", "RArm", "LArm"]))
        
        # Puppeteering (connect two robots):
        puppet_stream = puppet.motion_streaming()
        performer_stream = performer.motion_streaming(input_source=puppet_stream)
        puppet_stream.request(StartStreaming(["Head", "RArm", "LArm"]))
        
        # With joint locking:
        pepper.motion_streaming().request(SetLockedJointsRequest(["RArm"]))
    """
    component_class = PepperMotionStreamerService


if __name__ == "__main__":
    SICComponentManager([PepperMotionStreamerService])