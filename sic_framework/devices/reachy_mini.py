import atexit
import os
import shutil
import subprocess
import threading
import time
import sys

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

    For ``"local"``, ``"sim"``, and ``"mockup-sim"`` modes the daemon is
    spawned automatically with its output silenced.  For ``"wireless"``
    the daemon is already running on the robot.

    :param mode: ``"local"`` (USB-connected Lite), ``"sim"`` (MuJoCo
        simulation), ``"mockup-sim"`` (simulation without MuJoCo), or
        ``"wireless"`` (robot on the network).
    :type mode: str
    :param headless: Run daemon without GUI (sim/mockup-sim only).
    :type headless: bool
    :param wake_up_on_start: Wake up the robot when the daemon starts.
    :type wake_up_on_start: bool
    :param camera_conf: Configuration for the camera sensor.
    :param mic_conf: Configuration for the microphone sensor.
    :param speakers_conf: Configuration for the speaker actuator.
    :param motion_conf: Configuration for the motion actuator.
    :param imu_conf: Configuration for the IMU sensor (wireless only).
    """

    _MODE_TO_CONNECTION = {
        "sim": "localhost_only",
        "mockup-sim": "localhost_only",
        "local": "localhost_only",
        "wireless": "network",
    }

    _SPAWN_MODES = ("local", "sim", "mockup-sim")

    _mini_instance = None
    _daemon_proc = None

    def __init__(self, mode="sim", headless=False, wake_up_on_start=True,
                 camera_conf=None, mic_conf=None, speakers_conf=None,
                 motion_conf=None, imu_conf=None):
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
            if self.mode in self._SPAWN_MODES:
                self._start_daemon(
                    sim=(self.mode == "sim"),
                    mockup_sim=(self.mode == "mockup-sim"),
                    headless=headless,
                    wake_up_on_start=wake_up_on_start,
                )

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

    def _start_daemon(self, sim=False, mockup_sim=False, headless=False,
                      wake_up_on_start=True):
        """Spawn the reachy-mini daemon with its output silenced."""
        if sim and sys.platform == "darwin":
            mjpython = shutil.which("mjpython")
            daemon_bin = shutil.which("reachy-mini-daemon")
            if mjpython is None:
                raise RuntimeError(
                    "mjpython not found on PATH. "
                    "MuJoCo simulation on macOS requires mjpython: pip install mujoco"
                )
            if daemon_bin is None:
                raise RuntimeError(
                    "reachy-mini-daemon not found on PATH. "
                    "Install the reachy-mini package: pip install 'reachy-mini>=1.6.0'"
                )
            cmd = [mjpython, daemon_bin]
        else:
            daemon_bin = shutil.which("reachy-mini-daemon")
            if daemon_bin is None:
                raise RuntimeError(
                    "reachy-mini-daemon not found on PATH. "
                    "Install the reachy-mini package: pip install 'reachy-mini>=1.6.0'"
                )
            cmd = [daemon_bin]

        # Silence GStreamer WebRTC signalling logs in the daemon subprocess
        os.environ["RUST_LOG"] = "error,gst_plugin_webrtc_signalling=off"
        os.environ["WEBRTCSINK_SIGNALLING_SERVER_LOG"] = "error"

        cmd.extend(["--log-level", "CRITICAL"])
        if sim:
            cmd.append("--sim")
        elif mockup_sim:
            cmd.append("--mockup-sim")
        if headless:
            cmd.append("--headless")
        if not wake_up_on_start:
            cmd.append("--no-wake-up-on-start")

        self.logger.info("Starting Reachy Mini daemon: {}".format(" ".join(cmd)))
        ReachyMiniDevice._daemon_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    @staticmethod
    def _patch_mujoco_set_resolution():
        """Patch CameraBase.set_resolution to allow MuJoCo sim cameras.

        The SDK unconditionally calls set_resolution() during camera init,
        but raises RuntimeError for MujocoCameraSpecs. This is an SDK bug:
        the guard blocks initialization, not just runtime changes. The
        patch bypasses the guard for MuJoCo only; all other cameras
        delegate to the original method.
        """
        from reachy_mini.media.camera_base import CameraBase
        from reachy_mini.media.camera_constants import MujocoCameraSpecs

        original = CameraBase.set_resolution

        def patched_set_resolution(self, resolution):
            if isinstance(self.camera_specs, MujocoCameraSpecs):
                self._resolution = resolution
                self._apply_resolution(resolution)
                return
            original(self, resolution)

        CameraBase.set_resolution = patched_set_resolution

    @staticmethod
    def _patch_glib_mainloop_context():
        """Patch GLib.MainLoop to use the thread-default context.

        The SDK's GStreamer camera and audio classes create GLib.MainLoop()
        with no context, which claims the global default GLib main context.
        When run in background threads, this conflicts with OpenCV's Qt
        backend which also needs the default context for cv2.imshow().

        This patches MainLoop.__new__ so that a bare MainLoop() picks up
        the thread-default context instead of the global default. Combined
        with pushing a custom context as thread-default during the SDK
        constructor, all GStreamer loops and bus watches share a private
        context, leaving the global default free for Qt/OpenCV.
        """
        import gi
        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        _original_new = GLib.MainLoop.__new__

        def _patched_new(cls, context=None):
            if context is None:
                context = GLib.MainContext.get_thread_default()
            return _original_new(cls, context=context)

        GLib.MainLoop.__new__ = _patched_new

    def _create_sdk_instance(self, connection_mode):
        """Create a ReachyMini instance with GStreamer on a private context.

        Pushes a dedicated GLib.MainContext as the thread-default so that
        all GLib.MainLoop and bus.add_watch calls inside the SDK constructor
        attach to it instead of the global default context.
        """
        import gi
        gi.require_version("GLib", "2.0")
        from gi.repository import GLib
        from reachy_mini import ReachyMini

        ctx = GLib.MainContext.new()
        ctx.push_thread_default()
        try:
            return ReachyMini(
                connection_mode=connection_mode,
                spawn_daemon=False,
                log_level="ERROR",
            )
        finally:
            ctx.pop_thread_default()

    def _connect_sdk(self):
        """Create the shared ReachyMini SDK connection.

        Retries to allow a freshly spawned daemon time to start up.
        If media init fails due to the MuJoCo set_resolution SDK bug,
        patches the SDK and retries.
        """
        self._patch_glib_mainloop_context()

        connection_mode = self._MODE_TO_CONNECTION.get(self.mode, "auto")
        max_attempts = 8 if self.mode in self._SPAWN_MODES else 1

        self.logger.info("Connecting to Reachy Mini SDK (mode={}, connection_mode={})".format(
            self.mode, connection_mode))

        for attempt in range(max_attempts):
            try:
                ReachyMiniDevice._mini_instance = self._create_sdk_instance(connection_mode)
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
                if "Mujoco simulated camera" not in str(e):
                    raise
                self.logger.warning(
                    "MuJoCo camera set_resolution SDK bug hit; applying workaround")
                self._patch_mujoco_set_resolution()
                ReachyMiniDevice._mini_instance = self._create_sdk_instance(connection_mode)
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
