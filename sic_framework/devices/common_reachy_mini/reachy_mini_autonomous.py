import math
import threading
import time
from contextlib import contextmanager

import numpy as np
from reachy_mini.utils import create_head_pose
from reachy_mini.utils.interpolation import (
    compose_world_offset,
    linear_pose_interpolation,
    time_trajectory,
)

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.utils import is_sic_instance


class ReachyMiniAutonomousConf(SICConfMessage):
    """
    :param speaking_movement: Move the head and antennas along with audio played on the speakers.
    :param breathing: Play a subtle idle breathing motion.
    :param speaking_movement_intensity: Scale factor for the speaking movement amplitude.
    :param audio_latency: Seconds between queueing audio and hearing it, used to sync movement with speech.
    :param control_rate: Rate (Hz) at which motor targets are sent while autonomous movement is active.
    """

    def __init__(self, speaking_movement=True, breathing=True,
                 speaking_movement_intensity=1.0, audio_latency=0.1,
                 control_rate=50):
        super(ReachyMiniAutonomousConf, self).__init__()
        self.speaking_movement = speaking_movement
        self.breathing = breathing
        self.speaking_movement_intensity = speaking_movement_intensity
        self.audio_latency = audio_latency
        self.control_rate = control_rate


class ReachyMiniSpeakingMovementRequest(SICRequest):
    """Enable or disable movement while the robot speaks.

    :param value: True to enable, False to disable speaking movement.
    :param intensity: Optional new amplitude scale factor (1.0 is the default).
    """

    def __init__(self, value, intensity=None):
        super(ReachyMiniSpeakingMovementRequest, self).__init__()
        self.value = value
        self.intensity = intensity


class ReachyMiniBreathingRequest(SICRequest):
    """Enable or disable the idle breathing motion.

    :param value: True to enable, False to disable breathing.
    """

    def __init__(self, value):
        super(ReachyMiniBreathingRequest, self).__init__()
        self.value = value


class ReachyMiniAutonomousActuator(SICActuator):
    """Autonomous "life" movements for Reachy Mini.

    While any autonomous behaviour is enabled, this component owns the head,
    antenna and body-yaw targets: a control loop sends ``set_target`` at
    ``control_rate`` Hz, composed of a base pose plus additive offsets
    (speaking movement, breathing). Motion requests handled by
    :class:`ReachyMiniMotionActuator` are interpolated inside this loop, so
    the robot keeps moving naturally during scripted motions instead of the
    two fighting over the motors.

    Speaking movement is driven by audio pushed to
    :class:`ReachyMiniSpeakersActuator`, which forwards it via
    :meth:`feed_speech`.
    """

    # Loudness (dBFS) mapped to speech level 0 and 1 respectively
    _SILENCE_DB = -45.0
    _LOUD_DB = -15.0
    _HOP_S = 0.02
    _ATTACK_S = 0.05
    _RELEASE_S = 0.15
    # Time constant for fading behaviours in and out
    _FADE_S = 0.4

    _instance = None

    def __init__(self, *args, **kwargs):
        super(ReachyMiniAutonomousActuator, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance

        # _lock guards all state below and serialises motor commands
        self._lock = threading.RLock()
        self._speaking_enabled = self.params.speaking_movement
        self._breathing_enabled = self.params.breathing
        self._intensity = self.params.speaking_movement_intensity

        self._base_head = None
        self._base_antennas = None
        self._move = None
        self._pending_body_yaw = None
        self._paused = False
        self._owns_motors = False

        self._speaking_gain = 0.0
        self._breathing_gain = 0.0
        self._speech_env = np.zeros(0)
        self._speech_t0 = 0.0
        self._speech_level = 0.0

        self._loop_thread = None

    @staticmethod
    def get_conf():
        return ReachyMiniAutonomousConf()

    @staticmethod
    def get_inputs():
        return [ReachyMiniSpeakingMovementRequest, ReachyMiniBreathingRequest]

    @staticmethod
    def get_output():
        return SICMessage

    @classmethod
    def get_instance(cls):
        """Return the running autonomous actuator in this process, or None."""
        return cls._instance

    def start(self):
        super(ReachyMiniAutonomousActuator, self).start()
        ReachyMiniAutonomousActuator._instance = self
        self._loop_thread = threading.Thread(
            target=self._control_loop, name="ReachyMiniAutonomousLoop", daemon=True,
        )
        self._loop_thread.start()

    def execute(self, request):
        with self._lock:
            if is_sic_instance(request, ReachyMiniSpeakingMovementRequest):
                self._speaking_enabled = bool(request.value)
                if request.intensity is not None:
                    self._intensity = request.intensity
            elif is_sic_instance(request, ReachyMiniBreathingRequest):
                self._breathing_enabled = bool(request.value)
        return SICMessage()

    # ------------------------------------------------------------------
    # In-process API used by the other Reachy Mini components
    # ------------------------------------------------------------------

    def feed_speech(self, samples, sample_rate):
        """Schedule speaking movement for audio that was just queued for playback.

        Consecutive chunks are appended to the schedule, matching the
        sequential playback of the speaker queue.

        :param samples: Mono float samples in [-1, 1].
        :param sample_rate: Sample rate of ``samples``.
        """
        hop = int(sample_rate * self._HOP_S)
        n = len(samples) // hop
        if n == 0:
            return
        frames = np.asarray(samples[: n * hop], dtype=np.float32).reshape(n, hop)
        rms = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9
        db = 20.0 * np.log10(rms)
        env = np.clip((db - self._SILENCE_DB) / (self._LOUD_DB - self._SILENCE_DB), 0.0, 1.0)

        now = time.time()
        with self._lock:
            speech_end = self._speech_t0 + len(self._speech_env) * self._HOP_S
            start = now + self.params.audio_latency
            if speech_end > start:
                # Still playing earlier audio: drop the part already played and append
                played = max(0, int((now - self._speech_t0) / self._HOP_S))
                self._speech_env = np.concatenate([self._speech_env[played:], env])
                self._speech_t0 += played * self._HOP_S
            else:
                self._speech_env = env
                self._speech_t0 = start

    def goto(self, head=None, antennas=None, body_yaw=None, duration=1.0, method="minjerk"):
        """Interpolated move, blending with the autonomous movement if it is active.

        Blocks until the move is finished, like ``ReachyMini.goto_target``.
        """
        with self._lock:
            if not self._owns_motors or self._paused:
                # Autonomous movement is off: let the SDK do the move. Holding the
                # lock prevents the loop from taking over halfway through.
                self.mini.goto_target(head=head, antennas=antennas, body_yaw=body_yaw,
                                      duration=duration, method=method)
                return
            if self._move is not None:
                # Start the new move from wherever the previous one got to
                self._move["done"].set()
            start_yaw = None
            if body_yaw is not None:
                start_yaw = self.mini.get_current_joint_positions()[0][0]
            self._move = dict(
                t0=time.time(), duration=max(duration, 1e-3), method=method,
                start_head=self._base_head, target_head=head,
                start_antennas=list(self._base_antennas), target_antennas=antennas,
                start_yaw=start_yaw, target_yaw=body_yaw,
                done=threading.Event(),
            )
            done = self._move["done"]
        done.wait(duration + 1.0)

    def set_target(self, head=None, antennas=None, body_yaw=None):
        """Immediate target, used as the new base pose if autonomous movement is active."""
        with self._lock:
            if not self._owns_motors or self._paused:
                self.mini.set_target(head=head, antennas=antennas, body_yaw=body_yaw)
                return
            self._finish_move()
            if head is not None:
                self._base_head = np.array(head, dtype=np.float64)
            if antennas is not None:
                self._base_antennas = list(antennas)
            if body_yaw is not None:
                self._pending_body_yaw = body_yaw

    @contextmanager
    def paused(self):
        """Suspend autonomous movement while the caller drives the motors directly.

        On exit the base pose is re-read from the robot and the autonomous
        movement fades back in.
        """
        with self._lock:
            self._paused = True
            self._finish_move()
        try:
            yield
        finally:
            with self._lock:
                self._paused = False
                if self._owns_motors:
                    self._sync_base_from_robot()

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------

    def _control_loop(self):
        period = 1.0 / self.params.control_rate
        last = time.time()
        try:
            while not self._signal_to_stop.is_set():
                now = time.time()
                dt = now - last
                last = now
                try:
                    with self._lock:
                        if not self._paused:
                            self._tick(now, dt)
                except Exception as e:
                    self.logger.warning("Autonomous movement update failed: {}".format(e))
                time.sleep(max(0.0, period - (time.time() - now)))
        finally:
            self._stopped.set()

    def _tick(self, now, dt):
        enabled = self._speaking_enabled or self._breathing_enabled
        fade = 1.0 - math.exp(-dt / self._FADE_S)
        self._speaking_gain += fade * (float(self._speaking_enabled) - self._speaking_gain)
        self._breathing_gain += fade * (float(self._breathing_enabled) - self._breathing_gain)

        if not self._owns_motors:
            if not enabled:
                return
            # Don't freeze the robot halfway through a motion it is still
            # finishing, e.g. the daemon's wake-up animation.
            self._wait_until_still()
            self._sync_base_from_robot()
            self._owns_motors = True

        active = enabled or self._speaking_gain > 1e-2 or self._breathing_gain > 1e-2
        if not active and self._move is None:
            # Faded out: send the clean base pose once and hand the motors back
            self.mini.set_target(head=self._base_head, antennas=self._base_antennas)
            self._owns_motors = False
            return

        body_yaw = self._advance_move(now)
        level = self._update_speech_level(now, dt)
        head_offset, antenna_offset = self._offsets(now, level)

        head = compose_world_offset(self._base_head, head_offset)
        antennas = [self._base_antennas[0] + antenna_offset[0],
                    self._base_antennas[1] + antenna_offset[1]]
        if self._pending_body_yaw is not None:
            body_yaw = self._pending_body_yaw
            self._pending_body_yaw = None
        self.mini.set_target(head=head, antennas=antennas, body_yaw=body_yaw)

    def _advance_move(self, now):
        """Advance the current interpolated move; return the body yaw to send (or None)."""
        move = self._move
        if move is None:
            return None
        t = min(1.0, (now - move["t0"]) / move["duration"])
        s = time_trajectory(t, move["method"])
        if move["target_head"] is not None:
            self._base_head = linear_pose_interpolation(move["start_head"], move["target_head"], s)
        if move["target_antennas"] is not None:
            self._base_antennas = [
                a + (b - a) * s for a, b in zip(move["start_antennas"], move["target_antennas"])
            ]
        body_yaw = None
        if move["target_yaw"] is not None:
            body_yaw = move["start_yaw"] + (move["target_yaw"] - move["start_yaw"]) * s
        if t >= 1.0:
            self._finish_move()
        return body_yaw

    def _finish_move(self):
        """Jump the base to the current move's target and release its waiter."""
        move = self._move
        if move is None:
            return
        if move["target_head"] is not None:
            self._base_head = np.array(move["target_head"], dtype=np.float64)
        if move["target_antennas"] is not None:
            self._base_antennas = list(move["target_antennas"])
        if move["target_yaw"] is not None:
            self._pending_body_yaw = move["target_yaw"]
        self._move = None
        move["done"].set()

    def _update_speech_level(self, now, dt):
        i = int((now - self._speech_t0) / self._HOP_S)
        target = self._speech_env[i] if 0 <= i < len(self._speech_env) else 0.0
        tau = self._ATTACK_S if target > self._speech_level else self._RELEASE_S
        self._speech_level += (1.0 - math.exp(-dt / tau)) * (target - self._speech_level)
        return self._speech_level

    def _offsets(self, now, level):
        """Head offset pose (world frame) and antenna offsets for this tick."""
        s = level * self._speaking_gain * self._intensity
        b = self._breathing_gain
        tau = 2.0 * math.pi

        # Speaking: a loudness-modulated mix of incommensurate oscillations so the
        # motion does not look periodic, plus a slight lift of the head when loud.
        pitch = s * (4.0 * math.sin(tau * 2.1 * now) - 2.0)
        roll = s * 3.0 * math.sin(tau * 1.3 * now + 0.7)
        yaw = s * 4.0 * math.sin(tau * 0.9 * now + 1.9)
        z = s * 2.0 * math.sin(tau * 2.1 * now + 0.3)
        antenna = s * 0.25 * math.sin(tau * 2.7 * now)

        # Breathing: slow vertical bob with a hint of pitch, gently swaying antennas
        z += b * 2.5 * math.sin(tau * 0.2 * now)
        pitch += b * 1.5 * math.sin(tau * 0.2 * now - 0.5)
        sway = b * 0.1 * math.sin(tau * 0.12 * now)

        head_offset = create_head_pose(z=z, roll=roll, pitch=pitch, yaw=yaw, mm=True, degrees=True)
        return head_offset, (antenna + sway, -antenna - sway)

    def _wait_until_still(self, timeout=2.0, tolerance=1e-3):
        deadline = time.time() + timeout
        previous = self.mini.get_current_head_pose()
        while time.time() < deadline and not self._signal_to_stop.is_set():
            time.sleep(0.1)
            current = self.mini.get_current_head_pose()
            if np.max(np.abs(np.asarray(current) - np.asarray(previous))) < tolerance:
                return
            previous = current

    def _sync_base_from_robot(self):
        """Take the robot's current pose as base and fade the offsets in from zero."""
        self._base_head = np.array(self.mini.get_current_head_pose(), dtype=np.float64)
        self._base_antennas = list(self.mini.get_present_antenna_joint_positions())
        self._speaking_gain = 0.0
        self._breathing_gain = 0.0

    def _cleanup(self):
        if ReachyMiniAutonomousActuator._instance is self:
            ReachyMiniAutonomousActuator._instance = None
        with self._lock:
            self._finish_move()
            if self._owns_motors:
                try:
                    self.mini.set_target(head=self._base_head, antennas=self._base_antennas)
                except Exception:
                    pass
            self._owns_motors = False


class ReachyMiniAutonomous(SICConnector):
    component_class = ReachyMiniAutonomousActuator
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniAutonomousActuator], component_group="ReachyMini")
