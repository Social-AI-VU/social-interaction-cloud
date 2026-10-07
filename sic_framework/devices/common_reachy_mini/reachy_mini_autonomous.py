import math
import threading
import time
from contextlib import contextmanager

import numpy as np
from reachy_mini.reachy_mini import INIT_ANTENNAS_JOINT_POSITIONS, INIT_HEAD_POSE
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
    :param speaking_movement: Wobble the head along with audio played on the speakers.
    :param breathing: Play a subtle breathing motion whenever the robot is idle.
    :param head_tracking: Follow the face of the person in front of the robot.
    :param breathing_idle_delay: Seconds without motion requests before breathing starts.
    :param audio_latency: Seconds between queueing audio and hearing it, used to
        pause head tracking while the robot speaks.
    :param control_rate: Rate (Hz) at which motor targets are sent while breathing.
    """

    def __init__(self, speaking_movement=True, breathing=True, head_tracking=False,
                 breathing_idle_delay=0.3, audio_latency=0.1, control_rate=50):
        super(ReachyMiniAutonomousConf, self).__init__()
        self.speaking_movement = speaking_movement
        self.breathing = breathing
        self.head_tracking = head_tracking
        self.breathing_idle_delay = breathing_idle_delay
        self.audio_latency = audio_latency
        self.control_rate = control_rate


class ReachyMiniSpeakingMovementRequest(SICRequest):
    """Enable or disable head movement while the robot speaks.

    :param value: True to enable, False to disable speaking movement.
    """

    def __init__(self, value):
        super(ReachyMiniSpeakingMovementRequest, self).__init__()
        self.value = value


class ReachyMiniBreathingRequest(SICRequest):
    """Enable or disable the idle breathing motion.

    :param value: True to enable, False to disable breathing.
    """

    def __init__(self, value):
        super(ReachyMiniBreathingRequest, self).__init__()
        self.value = value


class ReachyMiniListeningRequest(SICRequest):
    """Tell the robot whether it is listening to the user.

    While listening the antennas freeze and breathing pauses; afterwards they
    blend back. Send ``True`` when the user starts speaking (e.g. on a voice
    activity or speech recognition event) and ``False`` when they stop.

    :param value: True while the user is speaking, False otherwise.
    """

    def __init__(self, value):
        super(ReachyMiniListeningRequest, self).__init__()
        self.value = value


class ReachyMiniHeadTrackingRequest(SICRequest):
    """Enable or disable following the user's face with the head.

    :param value: True to enable, False to disable head tracking.
    """

    def __init__(self, value):
        super(ReachyMiniHeadTrackingRequest, self).__init__()
        self.value = value


class ReachyMiniAutonomousActuator(SICActuator):
    """Autonomous "life" movements for Reachy Mini.

    - Speaking movement: the SDK's audio-reactive head wobble, applied by the
      daemon on top of whatever pose the robot is in.
    - Head tracking: the daemon's face tracking. It is paused while the robot
      speaks so the head holds still on the user instead of fighting the wobble.
    - Breathing: while it is enabled, this component owns the head, antenna and
      body-yaw targets. A control loop sends ``set_target`` at ``control_rate``
      Hz, composed of a base pose plus the breathing offset. The base pose is
      the neutral pose until a motion request moves it elsewhere. Motion requests
      handled by :class:`ReachyMiniMotionActuator` are interpolated inside this
      loop, so they blend with breathing instead of fighting it. Breathing
      fades in once no motion was requested for ``breathing_idle_delay``
      seconds and fades out again for the next motion.
    - Listening: freezes the antennas and pauses breathing while the user speaks.

    The speakers report played audio via :meth:`notify_speech`.
    """

    # Time constant for fading breathing in and out
    _FADE_S = 0.4
    # Seconds to blend the antennas back after listening
    _ANTENNA_UNFREEZE_S = 0.4
    # Seconds to move to the base pose when breathing takes over the motors
    _TAKEOVER_S = 1.0
    # Seconds to settle into the end pose of a paused() motion
    _SETTLE_S = 0.5
    # Antennas folded further than this (rad) mean the robot is asleep
    _ASLEEP_ANTENNA = 2.5

    _instance = None

    def __init__(self, *args, **kwargs):
        super(ReachyMiniAutonomousActuator, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance

        # _lock guards all state below and serialises motor commands
        self._lock = threading.RLock()
        self._breathing_enabled = self.params.breathing
        self._head_tracking = False

        # Pose to breathe around: neutral until a motion request moves it
        self._base_head = np.array(INIT_HEAD_POSE, dtype=np.float64)
        self._base_antennas = list(INIT_ANTENNAS_JOINT_POSITIONS)
        self._last_antennas = None
        self._move = None
        self._pending_body_yaw = None
        self._paused = False
        self._owns_motors = False
        self._last_activity = time.time()
        self._breathing_gain = 0.0
        self._breathing_t0 = 0.0

        self._listening = False
        self._frozen_antennas = None
        self._antenna_unfreeze = 1.0

        self._speech_start = 0.0
        self._speech_end = 0.0
        self._speaking = False

        self._loop_thread = None

    @staticmethod
    def get_conf():
        return ReachyMiniAutonomousConf()

    @staticmethod
    def get_inputs():
        return [
            ReachyMiniSpeakingMovementRequest,
            ReachyMiniBreathingRequest,
            ReachyMiniListeningRequest,
            ReachyMiniHeadTrackingRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    @classmethod
    def get_instance(cls):
        """Return the running autonomous actuator in this process, or None."""
        return cls._instance

    def start(self):
        super(ReachyMiniAutonomousActuator, self).start()
        self._set_speaking_movement(self.params.speaking_movement)
        self._set_head_tracking(self.params.head_tracking)
        ReachyMiniAutonomousActuator._instance = self
        self._loop_thread = threading.Thread(
            target=self._control_loop, name="ReachyMiniAutonomousLoop", daemon=True,
        )
        self._loop_thread.start()

    def execute(self, request):
        with self._lock:
            if is_sic_instance(request, ReachyMiniSpeakingMovementRequest):
                self._set_speaking_movement(request.value)
            elif is_sic_instance(request, ReachyMiniBreathingRequest):
                self._breathing_enabled = bool(request.value)
            elif is_sic_instance(request, ReachyMiniListeningRequest):
                self._set_listening(bool(request.value))
            elif is_sic_instance(request, ReachyMiniHeadTrackingRequest):
                self._set_head_tracking(request.value)
        return SICMessage()

    def _set_speaking_movement(self, enabled):
        if enabled:
            self.mini.enable_wobbling()
        else:
            self.mini.disable_wobbling()

    def _set_head_tracking(self, enabled):
        enabled = bool(enabled)
        if enabled == self._head_tracking:
            return
        self._head_tracking = enabled
        self._speaking = False
        if enabled:
            self.mini.start_head_tracking(weight=1.0)
        else:
            self.mini.stop_head_tracking()

    def _set_listening(self, listening):
        if listening == self._listening:
            return
        self._listening = listening
        self._last_activity = time.time()
        if listening and self._last_antennas is not None:
            self._frozen_antennas = list(self._last_antennas)
        self._antenna_unfreeze = 0.0

    # ------------------------------------------------------------------
    # In-process API used by the other Reachy Mini components
    # ------------------------------------------------------------------

    def notify_speech(self, duration):
        """Register audio that was just queued for playback on the speakers.

        Consecutive chunks extend the current utterance, matching the
        sequential playback of the speaker queue.

        :param duration: Duration of the queued audio in seconds.
        """
        now = time.time()
        with self._lock:
            start = now + self.params.audio_latency
            if self._speech_end < start:
                self._speech_start = start
                self._speech_end = start
            self._speech_end += duration

    def goto(self, head=None, antennas=None, body_yaw=None, duration=1.0, method="minjerk"):
        """Interpolated move, blending with the breathing if it is active.

        Blocks until the move is finished, like ``ReachyMini.goto_target``.
        """
        with self._lock:
            self._last_activity = time.time()
            if not self._owns_motors or self._paused:
                # Breathing is off: let the SDK do the move. Holding the lock
                # prevents the loop from taking over halfway through.
                self.mini.goto_target(head=head, antennas=antennas, body_yaw=body_yaw,
                                      duration=duration, method=method)
                self._last_activity = time.time()
                self._remember_base(head, antennas)
                return
            done = self._start_move(head, antennas, body_yaw, duration, method)
        done.wait(duration + 1.0)

    def _start_move(self, head, antennas, body_yaw, duration, method):
        """Start interpolating the base pose inside the loop; return the move's done event."""
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
        return self._move["done"]

    def _remember_base(self, head, antennas):
        """Keep the pose the robot was sent to, to breathe around it later."""
        if head is not None:
            self._base_head = np.array(head, dtype=np.float64)
        if antennas is not None:
            self._base_antennas = list(antennas)

    def set_target(self, head=None, antennas=None, body_yaw=None):
        """Immediate target, used as the new base pose if breathing is active."""
        with self._lock:
            self._last_activity = time.time()
            if not self._owns_motors or self._paused:
                self.mini.set_target(head=head, antennas=antennas, body_yaw=body_yaw)
                self._remember_base(head, antennas)
                return
            self._finish_move()
            self._remember_base(head, antennas)
            if body_yaw is not None:
                self._pending_body_yaw = body_yaw

    @contextmanager
    def paused(self, head=None, antennas=None):
        """Suspend autonomous movement while the caller drives the motors directly.

        :param head: Pose the caller's motion ends in, used as the new base pose.
            Pass it when known: the SDK's motions can return before the robot
            has physically arrived, so reading the pose back is unreliable.
        :param antennas: Antenna positions the caller's motion ends in.

        Without them, the robot's pose on exit becomes the base pose. If
        breathing is active the robot then glides to the base pose, and
        breathing fades back in once the robot is idle.
        """
        with self._lock:
            self._paused = True
            self._finish_move()
        try:
            yield
        finally:
            with self._lock:
                self._paused = False
                self._last_activity = time.time()
                current_head = np.array(self.mini.get_current_head_pose(), dtype=np.float64)
                current_antennas = list(self.mini.get_present_antenna_joint_positions())
                target_head = current_head if head is None else head
                target_antennas = current_antennas if antennas is None else antennas
                if self._owns_motors:
                    self._base_head, self._base_antennas = current_head, current_antennas
                    self._breathing_gain = 0.0
                    self._start_move(target_head, target_antennas, None, self._SETTLE_S, "minjerk")
                else:
                    self._remember_base(target_head, target_antennas)

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
                        self._update_head_tracking(now)
                        if not self._paused:
                            self._tick(now, dt)
                except Exception as e:
                    self.logger.warning("Autonomous movement update failed: {}".format(e))
                time.sleep(max(0.0, period - (time.time() - now)))
        finally:
            self._stopped.set()

    def _update_head_tracking(self, now):
        """Pause head tracking while speaking, holding the head on the user."""
        if not self._head_tracking:
            return
        speaking = self._speech_start <= now < self._speech_end
        if speaking == self._speaking:
            return
        if speaking:
            # Only pause once a face is locked, else speech blocks acquiring one
            if not self.mini.get_tracked_face(wait=False).detected:
                return
            anchor = np.array(self.mini.get_current_head_pose(), dtype=np.float64)
            if self._owns_motors:
                self._finish_move()
                self._base_head = anchor
            else:
                self.mini.set_target(head=anchor)
            self.mini.start_head_tracking(weight=0.0)
        else:
            self.mini.start_head_tracking(weight=1.0)
        self._speaking = speaking

    def _tick(self, now, dt):
        if not self._owns_motors:
            if not self._breathing_enabled or self._is_asleep():
                return
            # Don't interrupt a motion the robot is still finishing, e.g. the
            # daemon's wake-up animation.
            self._wait_until_still()
            self._take_over_motors()

        body_yaw = self._advance_move(now)

        idle = (self._move is None and not self._listening
                and now - self._last_activity >= self.params.breathing_idle_delay)
        breathe = self._breathing_enabled and idle
        if breathe and self._breathing_gain < 1e-2:
            # Start each breathing cycle from its neutral phase
            self._breathing_t0 = now
        fade = 1.0 - math.exp(-dt / self._FADE_S)
        self._breathing_gain += fade * (float(breathe) - self._breathing_gain)

        if not self._breathing_enabled and self._breathing_gain < 1e-2 and self._move is None:
            # Faded out: send the clean base pose once and hand the motors back
            self.mini.set_target(head=self._base_head, antennas=self._base_antennas)
            self._last_antennas = list(self._base_antennas)
            self._owns_motors = False
            return

        head_offset, antenna_offset = self._breathing_offsets(now - self._breathing_t0)
        head = compose_world_offset(self._base_head, head_offset)
        antennas = self._blend_listening_antennas(
            [self._base_antennas[0] + antenna_offset, self._base_antennas[1] - antenna_offset], dt,
        )
        if self._pending_body_yaw is not None:
            body_yaw = self._pending_body_yaw
            self._pending_body_yaw = None
        self.mini.set_target(head=head, antennas=antennas, body_yaw=body_yaw)
        self._last_antennas = antennas

    def _advance_move(self, now):
        """Advance the current interpolated move; return the body yaw to send (or None)."""
        move = self._move
        if move is None:
            return None
        self._last_activity = now
        t = max(0.0, min(1.0, (now - move["t0"]) / move["duration"]))
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

    def _breathing_offsets(self, t):
        """Head offset pose (world frame) and antenna sway for breathing time ``t``.

        Same breathing as Pollen's conversation app: a slow 5 mm vertical bob
        with the antennas swaying in opposite directions, but around the
        current pose instead of returning to neutral.
        """
        g = self._breathing_gain
        z = g * 5.0 * math.sin(2.0 * math.pi * 0.1 * t)
        sway = g * math.radians(15.0) * math.sin(2.0 * math.pi * 0.5 * t)
        return create_head_pose(z=z, mm=True, degrees=True), sway

    def _blend_listening_antennas(self, target, dt):
        """Hold the antennas while listening, then blend them back to ``target``."""
        if self._frozen_antennas is None:
            return target
        if self._listening:
            return list(self._frozen_antennas)
        self._antenna_unfreeze = min(1.0, self._antenna_unfreeze + dt / self._ANTENNA_UNFREEZE_S)
        b = self._antenna_unfreeze
        blended = [f + (a - f) * b for f, a in zip(self._frozen_antennas, target)]
        if b >= 1.0:
            self._frozen_antennas = None
        return blended

    def _wait_until_still(self, timeout=2.0, tolerance=1e-3):
        deadline = time.time() + timeout
        previous = self.mini.get_current_head_pose()
        while time.time() < deadline and not self._signal_to_stop.is_set():
            time.sleep(0.1)
            current = self.mini.get_current_head_pose()
            if np.max(np.abs(np.asarray(current) - np.asarray(previous))) < tolerance:
                return
            previous = current

    def _is_asleep(self):
        """True while the robot is in its sleep pose; breathing waits for a wake-up."""
        antennas = self.mini.get_present_antenna_joint_positions()
        return max(abs(a) for a in antennas) > self._ASLEEP_ANTENNA

    def _take_over_motors(self):
        """Start sending targets: glide from the robot's current pose to the base pose."""
        target_head, target_antennas = self._base_head, self._base_antennas
        self._base_head = np.array(self.mini.get_current_head_pose(), dtype=np.float64)
        self._base_antennas = list(self.mini.get_present_antenna_joint_positions())
        self._last_antennas = list(self._base_antennas)
        self._breathing_gain = 0.0
        self._owns_motors = True
        self._start_move(target_head, target_antennas, None, self._TAKEOVER_S, "minjerk")

    def _cleanup(self):
        if ReachyMiniAutonomousActuator._instance is self:
            ReachyMiniAutonomousActuator._instance = None
        with self._lock:
            self._finish_move()
            try:
                if self._owns_motors:
                    self.mini.set_target(head=self._base_head, antennas=self._base_antennas)
                self.mini.disable_wobbling()
                if self._head_tracking:
                    self.mini.stop_head_tracking()
            except Exception:
                pass
            self._owns_motors = False


class ReachyMiniAutonomous(SICConnector):
    component_class = ReachyMiniAutonomousActuator
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniAutonomousActuator], component_group="ReachyMini")
