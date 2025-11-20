from __future__ import print_function

from abc import ABCMeta, abstractmethod
import os
import posixpath
import shlex

from sic_framework.core import sic_redis, utils
from sic_framework.core.message_python2 import SICPingRequest, SICPongMessage, SICStopServerRequest
from sic_framework.core.utils import MAGIC_STARTED_COMPONENT_MANAGER_TEXT
from sic_framework.devices.common_naoqi.nao_motion_streamer import *
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
from sic_framework.devices.common_naoqi.naoqi_speakers import *
from sic_framework.devices.common_naoqi.naoqi_stiffness import *
from sic_framework.devices.common_naoqi.naoqi_text_to_speech import *
from sic_framework.devices.common_naoqi.naoqi_tracker import (
    NaoqiTracker,
    NaoqiTrackerActuator,
)
from sic_framework.devices.device import SICDeviceManager

shared_naoqi_components = [
    NaoqiTopCameraSensor,
    NaoqiBottomCameraSensor,
    NaoqiMicrophoneSensor,
    NaoqiMotionActuator,
    NaoqiTextToSpeechActuator,
    NaoqiMotionRecorderActuator,
    NaoqiStiffnessActuator,
    NaoqiAutonomousActuator,
    NaoqiLEDsActuator,
    NaoqiSpeakerComponent,
    NaoqiButtonSensor,
    NaoqiTrackerActuator,
    NaoqiLookAtComponent,
]


class Naoqi(SICDeviceManager):
    __metaclass__ = ABCMeta

    def __init__(
        self,
        ip,
        robot_type,
        venv,
        device_path,
        sic_version=None,
        dev_test=False,
        test_device_path="",
        test_repo=None,
        bypass_install=False,
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
            sic_version=sic_version,
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
        self.test_repo = test_repo
        self.bypass_install = bypass_install

        assert robot_type in [
            "nao",
            "pepper",
        ], "Robot type must be either 'nao' or 'pepper'"

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

            python2 {robot_wrapper_file}.py --redis_ip={redis_host} --client_id={client_id};
        """.format(
            robot_wrapper_file=robot_wrapper_file, redis_host=redis_hostname, client_id=self._client_id
        )

        # if this robot is expected to have a virtual environment, activate it
        if dev_test and venv:
            self.start_cmd = (
                """
            source ~/.test_venv/bin/activate;
        """
                + self.start_cmd
            )
        elif venv:
            self.start_cmd = (
                """
            source ~/.venv_sic/bin/activate;
        """
                + self.start_cmd
            )

        self.stop_cmd = """
            echo 'Killing all previous robot wrapper processes';
            pkill -f "python2 {robot_wrapper_file}.py"
        """.format(
            robot_wrapper_file=robot_wrapper_file
        )

        # stop SIC
        self.ssh_command(self.stop_cmd)
        time.sleep(0.1)

        self.logger.info("Checking to see if SIC is installed on remote device...")
        # make sure SIC is installed

        if self.dev_test:
            self.create_test_environment()
        elif self.bypass_install or self.check_sic_install():
            self.logger.info(
                "SIC is already installed on Naoqi device {}! starting SIC...".format(
                    self.device_ip
                )
            )
        else:
            self.logger.info(
                "SIC is not installed on Naoqi device {}, installing now".format(
                    self.device_ip
                )
            )
            self.sic_install()

        # start SIC
        self.logger.info(
            "Starting SIC on {} with redis ip {}".format(
                self.robot_type, redis_hostname
            )
        )
        self.run_sic()

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
        self.ssh_command(self.start_cmd, create_thread=True, get_pty=False)

        self.logger.debug(
            "Attempting to ping remote ComponentManager to see if it has started"
        )

        # try to ping remote ComponentManager to see if it has started
        ping_tries = 3
        for i in range(ping_tries):
            try:
                response = self._redis.request(
                    self.device_ip, SICPingRequest(), timeout=self._PING_TIMEOUT, block=True
                )
                if response == SICPongMessage():
                    break
            except TimeoutError:
                self.logger.debug(
                    "ComponentManager on ip {} hasn't started yet... retrying ping {} more times".format(
                        self.device_ip, ping_tries - 1 - i
                    )
                )
        else:
            raise RuntimeError(
                "Could not start SIC on remote device\nSee sic.log for details"
            )

        self.logger.debug("ComponentManager on ip {} has started!".format(self.device_ip))

    def stop_device(self):
        """
        Stops the device and all its components.

        Makes sure the process is killed and the device is stopped.
        """
        # send StopRequest to ComponentManager
        self._redis.request(self.device_ip, SICStopServerRequest())

        # make sure the process is killed
        stdin, stdout, stderr = self.ssh_command(self.stop_cmd)
        status = stdout.channel.recv_exit_status()
        if status != 0:
            self.logger.error("Failed to stop device, exit code: {status}".format(status=status))
            self.logger.error(stderr.read().decode("utf-8"))

    def upload_file(self, local_path, remote_path):
        """
        Upload a file to the Naoqi device using SCP.

        :param local_path: Path to the local file to upload.
        :type local_path: str
        :param remote_path: Destination path on the robot. Must be under /home/nao.
        :type remote_path: str

        :raises ValueError: If the local file does not exist or the remote path is invalid.
        :raises RuntimeError: If SCP is unavailable, the SSH connection is missing, or the upload fails.
        """
        if not local_path or not isinstance(local_path, str):
            raise ValueError("A valid local_path string is required.")

        if not remote_path or not isinstance(remote_path, str):
            raise ValueError("A valid remote_path string is required.")

        if not os.path.isfile(local_path):
            raise ValueError("Local path '{}' does not exist or is not a file.".format(local_path))

        if not remote_path.startswith("/home/nao"):
            raise ValueError("Destination path must start with '/home/nao'. Provided: '{}'".format(remote_path))

        if not self.SCPClient:
            raise RuntimeError("SCPClient is not available. Cannot upload file.")

        if not hasattr(self, "ssh"):
            raise RuntimeError("SSH connection has not been initialized. Cannot upload file.")

        remote_is_dir = remote_path.endswith("/") or remote_path == "/home/nao"
        if remote_is_dir:
            remote_dir = remote_path
            remote_file_path = posixpath.join(remote_dir, os.path.basename(local_path))
        else:
            remote_dir = posixpath.dirname(remote_path) or "/home/nao"
            remote_file_path = remote_path

        if not remote_dir.startswith("/home/nao"):
            raise ValueError("Destination directory must remain within '/home/nao'. Computed: '{}'".format(remote_dir))

        mkdir_cmd = "mkdir -p {}".format(shlex.quote(remote_dir))
        _, _, stderr, status = self.ssh_command(mkdir_cmd)
        if status != 0:
            error_output = stderr.read().decode("utf-8")
            raise RuntimeError(
                "Failed to create remote directory '{}': {}".format(remote_dir, error_output.strip())
            )

        # ensure destination file does not already exist
        check_cmd = "test -e {}".format(shlex.quote(remote_file_path))
        _, _, _, status = self.ssh_command(check_cmd)
        if status == 0:
            self.logger.info(
                "Skipping upload: destination file '%s' already exists on the Naoqi device.",
                remote_file_path,
            )
            return

        try:
            with self.SCPClient(self.ssh.get_transport()) as scp:
                destination = remote_dir if remote_is_dir else remote_file_path
                scp.put(local_path, destination)
        except Exception as exc:
            raise RuntimeError(
                "Failed to upload '{}' to '{}': {}".format(local_path, remote_file_path, exc)
            )

        self.logger.info("Uploaded '{}' to '{}' on the Naoqi device.".format(local_path, remote_file_path))

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
