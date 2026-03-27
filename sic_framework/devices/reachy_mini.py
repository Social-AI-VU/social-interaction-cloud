import atexit
import shutil
import subprocess
import threading
import time

from sic_framework import SICComponentManager, utils
from sic_framework.devices.common_reachy_mini.reachy_mini_camera import (
    ReachyMiniCamera,
    ReachyMiniCameraSensor,
)
from sic_framework.devices.common_reachy_mini.reachy_mini_microphone import (
    ReachyMiniMicrophone,
    ReachyMiniMicrophoneSensor,
)
from sic_framework.devices.common_reachy_mini.reachy_mini_speakers import (
    ReachyMiniSpeakers,
    ReachyMiniSpeakersActuator,
)
from sic_framework.devices.common_reachy_mini.reachy_mini_motion import (
    ReachyMiniMotion,
    ReachyMiniMotionActuator,
)
from sic_framework.devices.common_reachy_mini.reachy_mini_imu import (
    ReachyMiniIMU,
    ReachyMiniIMUSensor,
)
from sic_framework.devices.device import SICDeviceManager

reachy_mini_active = False


class ReachyMiniDevice(SICDeviceManager):
    """Device manager for the Reachy Mini robot.

    Runs all SIC components locally and connects to the Reachy Mini daemon
    via the SDK over HTTP, following the same pattern as :class:`Desktop`.

    For ``"local"`` and ``"sim"`` modes the daemon is spawned automatically
    with its output silenced.  For ``"wireless"`` the daemon is already
    running on the robot.

    :param mode: ``"local"`` (USB-connected Lite), ``"sim"`` (MuJoCo
        simulation), or ``"wireless"`` (robot on the network).
    :type mode: str
    :param camera_conf: Configuration for the camera sensor.
    :param mic_conf: Configuration for the microphone sensor.
    :param speakers_conf: Configuration for the speaker actuator.
    :param motion_conf: Configuration for the motion actuator.
    :param imu_conf: Configuration for the IMU sensor (wireless only).
    """

    _MODE_TO_CONNECTION = {
        "sim": "localhost_only",
        "local": "localhost_only",
        "wireless": "network",
    }

    _mini_instance = None
    _daemon_proc = None

    def __init__(self, mode="sim", camera_conf=None, mic_conf=None,
                 speakers_conf=None, motion_conf=None, imu_conf=None):
        super(ReachyMiniDevice, self).__init__(ip="127.0.0.1")

        self.mode = mode
        self.manager = None

        self.configs[ReachyMiniCamera] = camera_conf
        self.configs[ReachyMiniMicrophone] = mic_conf
        self.configs[ReachyMiniSpeakers] = speakers_conf
        self.configs[ReachyMiniMotion] = motion_conf
        self.configs[ReachyMiniIMU] = imu_conf

        global reachy_mini_active

        if not reachy_mini_active:
            if self.mode in ("local", "sim"):
                self._start_daemon(sim=(self.mode == "sim"))

            self._connect_sdk()

            # Build component list; IMU only for wireless
            components = [
                ReachyMiniCameraSensor,
                ReachyMiniMicrophoneSensor,
                ReachyMiniSpeakersActuator,
                ReachyMiniMotionActuator,
            ]
            if self.mode == "wireless":
                components.append(ReachyMiniIMUSensor)

            self.manager = SICComponentManager(
                components,
                client_id=utils.get_ip_adress(),
                auto_serve=False,
                name="ReachyMini",
            )
            self.manager.is_main_thread = False

            def managed_serve():
                try:
                    self.manager.serve()
                finally:
                    self.manager.stop_component_manager()

            self.thread = threading.Thread(
                target=managed_serve,
                name="ReachyMiniComponentManager-singleton",
                daemon=True,
            )
            self.thread.start()

            atexit.register(self.stop_device)
            reachy_mini_active = True

    def _start_daemon(self, sim=False):
        """Spawn the reachy-mini daemon with its output silenced."""
        daemon_bin = shutil.which("reachy-mini-daemon")
        if daemon_bin is None:
            raise RuntimeError(
                "reachy-mini-daemon not found on PATH. "
                "Install the reachy-mini package: pip install reachy-mini"
            )
        cmd = [daemon_bin]
        if sim:
            cmd.append("--sim")

        self.logger.info("Starting Reachy Mini daemon: {}".format(" ".join(cmd)))
        ReachyMiniDevice._daemon_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _connect_sdk(self):
        """Create the shared ReachyMini SDK connection.

        Retries to allow a freshly spawned daemon time to start up.
        If media initialization fails (known SDK issue with MuJoCo sim
        camera resolution), falls back to ``no_media``.
        """
        from reachy_mini import ReachyMini

        connection_mode = self._MODE_TO_CONNECTION.get(self.mode, "auto")
        needs_daemon_wait = self.mode in ("local", "sim")
        max_attempts = 8 if needs_daemon_wait else 1

        self.logger.info("Connecting to Reachy Mini SDK (mode={}, connection_mode={})".format(
            self.mode, connection_mode))

        for attempt in range(max_attempts):
            try:
                ReachyMiniDevice._mini_instance = ReachyMini(
                    connection_mode=connection_mode,
                    spawn_daemon=False,
                    log_level="CRITICAL",
                )
                return
            except ConnectionError:
                if attempt < max_attempts - 1:
                    self.logger.info("Daemon not ready, retrying ({}/{})...".format(
                        attempt + 1, max_attempts))
                    time.sleep(2)
                else:
                    self.logger.error("Failed to connect to Reachy Mini daemon after {} attempts".format(
                        max_attempts))
                    raise
            except RuntimeError as e:
                # SDK bug: MuJoCo sim camera does not support set_resolution()
                # in the GStreamer LOCAL backend. Fall back to no_media.
                self.logger.warning("Media init failed ({}), retrying with no_media".format(e))
                ReachyMiniDevice._mini_instance = ReachyMini(
                    connection_mode=connection_mode,
                    spawn_daemon=False,
                    log_level="CRITICAL",
                    media_backend="no_media",
                )
                return

    def stop_device(self):
        """Stop the Reachy Mini device and all its components."""
        global reachy_mini_active

        if self.manager is not None:
            self.manager.stop_component_manager()
            self.manager = None

        if ReachyMiniDevice._mini_instance is not None:
            self.logger.info("Closing Reachy Mini SDK connection")
            try:
                ReachyMiniDevice._mini_instance.__exit__(None, None, None)
            except Exception:
                pass
            ReachyMiniDevice._mini_instance = None

        if ReachyMiniDevice._daemon_proc is not None:
            self.logger.info("Stopping Reachy Mini daemon")
            ReachyMiniDevice._daemon_proc.terminate()
            try:
                ReachyMiniDevice._daemon_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ReachyMiniDevice._daemon_proc.kill()
            ReachyMiniDevice._daemon_proc = None

        reachy_mini_active = False

    @property
    def camera(self):
        return self._get_connector(ReachyMiniCamera)

    @property
    def mic(self):
        return self._get_connector(ReachyMiniMicrophone)

    @property
    def speakers(self):
        return self._get_connector(ReachyMiniSpeakers)

    @property
    def motion(self):
        return self._get_connector(ReachyMiniMotion)

    @property
    def imu(self):
        return self._get_connector(ReachyMiniIMU)


reachy_mini_component_list = [
    ReachyMiniCameraSensor,
    ReachyMiniMicrophoneSensor,
    ReachyMiniSpeakersActuator,
    ReachyMiniMotionActuator,
    ReachyMiniIMUSensor,
]


if __name__ == "__main__":
    SICComponentManager(reachy_mini_component_list, name="ReachyMini")
