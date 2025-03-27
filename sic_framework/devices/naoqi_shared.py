from __future__ import print_function

from abc import ABCMeta, abstractmethod

from sic_framework.core import sic_redis, utils
from sic_framework.core.utils import MAGIC_STARTED_COMPONENT_MANAGER_TEXT
from sic_framework.devices.common_naoqi.naoqi_autonomous import *
from sic_framework.devices.common_naoqi.naoqi_button import (
    NaoqiButton,
    NaoqiButtonSensor,
)
from sic_framework.devices.common_naoqi.naoqi_camera import *
from sic_framework.devices.common_naoqi.naoqi_leds import *
from sic_framework.devices.common_naoqi.naoqi_lookat import (
    NaoqiLookAt,
    NaoqiLookAtComponent,
)
from sic_framework.devices.common_naoqi.naoqi_microphone import *
from sic_framework.devices.common_naoqi.naoqi_motion import *
from sic_framework.devices.common_naoqi.naoqi_motion_recorder import *
from sic_framework.devices.common_naoqi.naoqi_motion_streamer import *
from sic_framework.devices.common_naoqi.naoqi_speakers import *
from sic_framework.devices.common_naoqi.naoqi_stiffness import *
from sic_framework.devices.common_naoqi.naoqi_text_to_speech import *
from sic_framework.devices.common_naoqi.naoqi_tracker import (
    NaoqiTracker,
    NaoqiTrackerActuator,
)
from sic_framework.devices.device import SICDevice
from sic_framework.core.message_python2 import SICPingRequest, SICPongMessage

shared_naoqi_components = [
    NaoqiTopCameraSensor,
    NaoqiBottomCameraSensor,
    NaoqiMicrophoneSensor,
    NaoqiMotionActuator,
    NaoqiTextToSpeechActuator,
    NaoqiMotionRecorderActuator,
    NaoqiMotionStreamerService,
    NaoqiStiffnessActuator,
    NaoqiAutonomousActuator,
    NaoqiLEDsActuator,
    NaoqiSpeakerComponent,
    NaoqiButtonSensor,
    NaoqiTrackerActuator,
    NaoqiLookAtComponent,
]


class Naoqi(SICDevice):
    __metaclass__ = ABCMeta

    def __init__(
        self,
        ip,
        robot_type,
        venv,
        device_path,
        dev_test=False,
        test_device_path="",
        top_camera_conf=None,
        bottom_camera_conf=None,
        mic_conf=None,
        motion_conf=None,
        tts_conf=None,
        motion_record_conf=None,
        motion_stream_conf=None,
        stiffness_conf=None,
        speaker_conf=None,
        lookat_conf=None,
        username=None,
        passwords=None,
    ):
        super().__init__(
            ip,
            username=username,
            passwords=passwords,
        )

        # Set the component configs
        self.configs[NaoqiTopCamera] = top_camera_conf
        self.configs[NaoqiBottomCamera] = bottom_camera_conf
        self.configs[NaoqiMicrophone] = mic_conf
        self.configs[NaoqiMotion] = motion_conf
        self.configs[NaoqiTextToSpeech] = tts_conf
        self.configs[NaoqiMotionRecorder] = motion_record_conf
        self.configs[NaoqiMotionStreamer] = motion_stream_conf
        self.configs[NaoqiStiffness] = stiffness_conf
        self.configs[NaoqiSpeaker] = speaker_conf
        self.configs[NaoqiLookAt] = lookat_conf

        self.robot_type = robot_type
        self.dev_test = dev_test

        assert robot_type in [
            "nao",
            "pepper",
        ], "Robot type must be either 'nao' or 'pepper'"

        # self.auto_install()
        
        redis_hostname, _ = sic_redis.get_redis_db_ip_password()

        if redis_hostname == "127.0.0.1" or redis_hostname == "localhost":
            # get own public ip address for the device to use
            redis_hostname = utils.get_ip_adress()

        # set start and stop scripts
        if dev_test:
            robot_wrapper_file = test_device_path + "/" + robot_type
        else:
            robot_wrapper_file = device_path + "/" + robot_type
    
        self.start_cmd = """            
            # export environment variables so that it can find the naoqi library
            export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages;
            export LD_LIBRARY_PATH=/opt/aldebaran/lib/naoqi;

            python2 {robot_wrapper_file}.py --redis_ip={redis_host};
        """.format(
            robot_wrapper_file=robot_wrapper_file, redis_host=redis_hostname
        )

        # if this robot is expected to have a virtual environment, activate it
        if dev_test and venv:
            self.start_cmd = """
            source ~/.test_venv/bin/activate;
        """ + self.start_cmd            
        elif venv:
            self.start_cmd = """
            source ~/.venv_sic/bin/activate;
        """ + self.start_cmd
        

        self.stop_cmd = """
            echo 'Killing all previous robot wrapper processes';
            pkill -f "python2 {robot_wrapper_file}.py"
        """.format(
            robot_wrapper_file=robot_wrapper_file
        )

        # stop SIC
        self.ssh.exec_command(self.stop_cmd)
        time.sleep(0.1)

        self.logger.info("Checking to see if SIC is installed on remote device...")
        # make sure SIC is installed
        self.verify_sic()

        # start SIC
        self.logger.info(
            "Starting SIC on {} with redis ip {}".format(
                self.robot_type, redis_hostname
            )
        )
        self.run_sic()

    def verify_sic(self):
        """
        Checks if SIC is installed on the device. installs SIC if not.
        """
        if not self.check_sic_install():
            # TODO: change to log statements
            self.logger.info(
                "SIC is not installed on Naoqi device {}, installing now".format(
                    self.ip
                )
            )
            self.sic_install()
        else:
            self.logger.info(
                "SIC is already installed on Naoqi device {}! starting SIC...".format(
                    self.ip
                )
            )

    @abstractmethod
    def check_sic_install():
        """
        Naos and Peppers have different ways of verifying SIC is installed.
        """
        pass

    @abstractmethod
    def sic_install():
        """
        Naos and Peppers have different ways of installing SIC.
        """
        pass

    def run_sic(self):
        """
        Starts SIC on the device.
        """
        stdin, stdout, _ = self.ssh.exec_command(self.start_cmd, get_pty=False)
        # merge stderr to stdout to simplify (and prevent potential deadlock as stderr is not read)
        stdout.channel.set_combine_stderr(True)

        # Set up error monitoring
        self.stopping = False

        def check_if_exit():
            # wait for the process to exit
            status = stdout.channel.recv_exit_status()
            # if remote threads exits before local main thread, report to user.
            if threading.main_thread().is_alive() and not self.stopping:
                raise RuntimeError(
                    "Remote SIC program has stopped unexpectedly.\nSee sic.log for details"
                )

        thread = threading.Thread(target=check_if_exit)
        thread.name = "remote_SIC_process_monitor"
        thread.start()

        # try to ping remote ComponentManager to see if it has started
        ping_tries = 3
        for i in range(ping_tries):
            try:
                response = self._redis.request(
                    self.ip, SICPingRequest(), timeout=self._PING_TIMEOUT, block=True
                )
                if response == SICPongMessage():
                    break
            except TimeoutError:
                self.logger.debug("ComponentManager on ip {} hasn't started yet... retrying ping {} more times".format(self.ip, ping_tries - 1 - i))
        else:
            raise RuntimeError(
                "Could not start SIC on remote device\nSee sic.log for details"
            )
        
        self.logger.debug("ComponentManager on ip {} has started!".format(self.ip))


    def stop(self):
        for connector in self.connectors.values():
            connector.stop()

        self.stopping = True
        self.ssh.exec_command(self.stop_cmd)

    @property
    def top_camera(self):
        return self._get_connector(NaoqiTopCamera)

    @property
    def bottom_camera(self):
        return self._get_connector(NaoqiBottomCamera)

    @property
    def mic(self):
        return self._get_connector(NaoqiMicrophone)

    @property
    def motion(self):
        return self._get_connector(NaoqiMotion)

    @property
    def tts(self):
        return self._get_connector(NaoqiTextToSpeech)

    @property
    def motion_record(self):
        return self._get_connector(NaoqiMotionRecorder)

    @property
    def motion_streaming(self):
        return self._get_connector(NaoqiMotionStreamer)

    @property
    def stiffness(self):
        return self._get_connector(NaoqiStiffness)

    @property
    def autonomous(self):
        return self._get_connector(NaoqiAutonomous)

    @property
    def leds(self):
        return self._get_connector(NaoqiLEDs)

    @property
    def speaker(self):
        return self._get_connector(NaoqiSpeaker)

    @property
    def buttons(self):
        return self._get_connector(NaoqiButton)

    @property
    def tracker(self):
        return self._get_connector(NaoqiTracker)

    @property
    def look_at(self):
        return self._get_connector(NaoqiLookAt)

    def __del__(self):
        if hasattr(self, "logfile"):
            self.logfile.close()


if __name__ == "__main__":
    pass
