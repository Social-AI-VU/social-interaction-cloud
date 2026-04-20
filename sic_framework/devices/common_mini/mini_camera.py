import socket
import struct
import subprocess
import time

import numpy as np

from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    CompressedImageMessage,
    SICConfMessage,
    turbojpeg,
)
from sic_framework.core.sensor_python2 import SICSensor


class MiniCameraConf(SICConfMessage):
    """
    Configuration for the Mini camera TCP server and Android camera app.

    This component is designed to mirror the behaviour of ``MiniMicrophoneSensor``:

    - It opens a TCP server socket on the Alphamini (or host running SIC).
    - An external Android camera app connects as a client and streams frames.
    - Each frame is sent as: 4‑byte big‑endian length header + JPEG‑encoded image bytes.

    The Android app is responsible for:
    - Capturing frames from the Alphamini camera.
    - JPEG‑encoding each frame to a byte array.
    - Sending ``len(frame_bytes)`` as a 4‑byte big‑endian integer, followed by the bytes.

    Additionally, this configuration can control basic camera streaming parameters
    on the Android side by passing intent extras when the app is started:

    - target_width / target_height: desired preview resolution (if supported).
    - scale: fractional scale of the default preview size.
    - jpeg_quality: JPEG quality (0–100).
    """

    def __init__(
        self,
        host="0.0.0.0",
        port=6001,
        timeout=1.0,
        target_width=0,
        target_height=0,
        scale=1.0,
        jpeg_quality=80,
        send_fps=0.0,
    ):
        """
        :param host: Interface to bind the TCP server to (default: 0.0.0.0).
        :param port: TCP port for incoming camera frames (default: 6001).
        :param timeout: Socket timeout in seconds for accept/recv (default: 1.0).
        :param target_width:
            Desired preview width in pixels. Default 0 lets the Android Camera API
            pick its preferred preview size (typically 640x480 on Alphamini).
        :param target_height:
            Desired preview height in pixels. Default 0 uses the camera’s preferred
            preview height.
        :param scale:
            Fractional scaling factor applied on top of the desired size chosen by
            the Android side. Concretely, the Android ``CameraActivity``:

            - starts from the camera’s preferred preview size,
            - optionally overrides that with ``target_width``/``target_height`` if
              both are > 0,
            - and then multiplies the resulting width/height by ``scale`` before
              snapping to the closest supported preview size.

            For example, if the preferred size is 640x480, ``scale=0.5`` yields an
            effective target of ~320x240. If you also set ``target_width`` and
            ``target_height``, they are used first and then scaled; they are *not*
            ignored when a non‑default ``scale`` is provided.
        :param jpeg_quality:
            JPEG quality (0–100). Default 80, which is the quality used in the
            original implementation before we started tuning for latency.
        :param send_fps:
            Optional maximum send rate from this sensor into SIC/Redis (in Hz).
            If > 0, the sensor will not publish more than this many frames per
            second, even if it receives more from the Android app. If 0, no
            explicit rate limit is applied on the SIC side.
        """
        SICConfMessage.__init__(self)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.target_width = target_width
        self.target_height = target_height
        self.scale = float(scale)
        self.jpeg_quality = jpeg_quality
        self.send_fps = float(send_fps)


class MiniCameraSensor(SICSensor):
    """
    A SICSensor component that receives JPEG‑compressed image frames over TCP
    from an external Android camera application running on Alphamini.

    Protocol (one frame):
        [4 bytes]  big‑endian unsigned int N  = length of JPEG payload
        [N bytes]  JPEG‑encoded image bytes

    For each complete frame, this sensor:
        - Decodes the JPEG bytes to a NumPy RGB array.
        - Wraps it in a ``CompressedImageMessage`` for downstream services
          (e.g. face detection, object detection, depth, etc.).
    """

    COMPONENT_STARTUP_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        super(MiniCameraSensor, self).__init__(*args, **kwargs)

        # Ensure configuration defaults exist
        default_conf = self.get_conf()
        for field in [
            "host",
            "port",
            "timeout",
            "target_width",
            "target_height",
            "scale",
            "jpeg_quality",
            "send_fps",
        ]:
            if not hasattr(self.params, field):
                setattr(self.params, field, getattr(default_conf, field))

        self.host = self.params.host
        self.port = self.params.port
        self.timeout = self.params.timeout

        # TCP server state
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.server_socket.settimeout(self.timeout)
        self.client_conn = None
        self.last_connection_time = time.time()

        # Buffer for assembling a single frame
        self._recv_buffer = b""

        # Simple rate logging for received frames
        self._frames_since_log = 0
        self._last_rate_log_time = time.time()

        # Optional send-rate limiting into SIC/Redis
        self._send_fps = float(getattr(self.params, "send_fps", 0.0))
        self._last_sent_time = 0.0

        # Check TurboJPEG availability once at startup so we know which encoder/decoder is used.
        if hasattr(turbojpeg, "encode") and hasattr(turbojpeg, "decode"):
            self.logger.info("MiniCameraSensor using TurboJPEG for image encode/decode")
        else:
            # In practice, message_python2 provides a FakeTurboJpeg fallback when TurboJPEG
            # is not available; log this explicitly so users know performance may be lower.
            self.logger.warning(
                "MiniCameraSensor: TurboJPEG not available, using fallback JPEG implementation"
            )

        self.logger.info(
            "MiniCameraSensor listening for frames on {host}:{port}".format(
                host=self.host, port=self.port
            )
        )

        # Start Android camera app on the Alphamini (mirrors MiniMicrophoneSensor behaviour)
        self.logger.info("Checking if Android camera app is running...")
        self.start_app("com.example.alphamini.camera", ".CameraActivity")

    @staticmethod
    def get_conf():
        return MiniCameraConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return CompressedImageMessage

    def start_app(self, package_name, activity_name):
        """
        Start the Android camera app on the Alphamini.

        This assumes the code is running on the robot (Termux environment),
        so we can call the Activity Manager (am) directly, analogous to
        MiniMicrophoneSensor.start_app.
        """
        try:
            cmd = [
                "am",
                "start",
                "-n",
                "{pkg}/{act}".format(pkg=package_name, act=activity_name),
                # Camera configuration extras
                "--ei",
                "target_width",
                str(getattr(self.params, "target_width", 0)),
                "--ei",
                "target_height",
                str(getattr(self.params, "target_height", 0)),
                "--ei",
                # Scale factor is passed as fixed-point int (scale * 10_000)
                "scale_factor",
                str(int(getattr(self.params, "scale", 1.0) * 10000)),
                "--ei",
                "jpeg_quality",
                str(getattr(self.params, "jpeg_quality", 60)),
            ]
            subprocess.run(cmd, check=False)
        except Exception as e:
            self.logger.error(
                "MiniCameraSensor failed to start app {pkg}/{act}: {err}".format(
                    pkg=package_name, act=activity_name, err=e
                )
            )

    def stop_app(self, package_name, activity_name):
        """
        Request a clean shutdown of the Android camera activity by sending it
        a broadcast that the activity listens for. This avoids relying on any
        privileged force-stop permissions.
        """
        try:
            cmd = [
                "am",
                "broadcast",
                "-a",
                "com.example.alphamini.camera.ACTION_STOP",
            ]
            subprocess.run(cmd, check=False)
        except Exception as e:
            self.logger.error(
                "MiniCameraSensor failed to stop app {pkg}/{act}: {err}".format(
                    pkg=package_name, act=activity_name, err=e
                )
            )

    def _accept_client(self):
        """
        Accept a new client connection if none is active.
        """
        if self.client_conn is not None:
            return

        try:
            self.client_conn, addr = self.server_socket.accept()
            self.client_conn.settimeout(self.timeout)
            self.logger.info("MiniCameraSensor connected by {addr}".format(addr=addr))
            self.last_connection_time = time.time()
            # Reset buffer when a new client connects
            self._recv_buffer = b""
        except socket.timeout:
            # No client yet; optionally restart the Android app after a timeout
            current_time = time.time()
            if current_time - self.last_connection_time > 5:
                self.logger.warning(
                    "No camera client for 5 seconds, restarting Android camera app..."
                )
                self.start_app("com.example.alphamini.camera", ".CameraActivity")
                self.last_connection_time = current_time

    def _recv_exactly(self, n_bytes):
        """
        Receive exactly n_bytes from the current client connection.
        Returns bytes on success, or None on failure / disconnect / timeout.
        """
        data = b""
        while len(data) < n_bytes:
            try:
                chunk = self.client_conn.recv(n_bytes - len(data))
            except socket.timeout:
                return None
            if not chunk:
                # Client disconnected
                return None
            data += chunk
        return data

    def execute(self):
        try:
            # Ensure we have a client
            if not self.client_conn:
                self._accept_client()
                # No client yet => nothing to send
                if not self.client_conn:
                    return None

            # Read 8-byte capture timestamp (ms since epoch) and 4‑byte length header
            ts_bytes = self._recv_exactly(8)
            if ts_bytes is None:
                self.logger.warning("MiniCameraSensor: client disconnected before timestamp")
                try:
                    self.client_conn.close()
                except Exception:
                    pass
                self.client_conn = None
                self.last_connection_time = time.time()
                return None

            header = self._recv_exactly(4)
            if header is None:
                self.logger.warning("MiniCameraSensor: client disconnected before header")
                try:
                    self.client_conn.close()
                except Exception:
                    pass
                self.client_conn = None
                self.last_connection_time = time.time()
                return None

            (timestamp_ms,) = struct.unpack("!Q", ts_bytes)
            (frame_len,) = struct.unpack("!I", header)
            if frame_len <= 0:
                self.logger.warning(
                    "MiniCameraSensor received non‑positive frame length: {length}".format(
                        length=frame_len
                    )
                )
                return None

            # Read frame payload
            payload = self._recv_exactly(frame_len)
            if payload is None:
                self.logger.warning("MiniCameraSensor: failed to receive full frame payload")
                try:
                    self.client_conn.close()
                except Exception:
                    pass
                self.client_conn = None
                self.last_connection_time = time.time()
                return None

            # Decode JPEG to numpy array (H, W, 3) in RGB
            try:
                # The core message module exposes turbojpeg/jpeg2np via CompressedImageMessage,
                # but here we can just rely on its JPEG decoder.
                from sic_framework.core.message_python2 import turbojpeg

                image_np = turbojpeg.decode(payload)
            except Exception as e:
                self.logger.error("MiniCameraSensor JPEG decode error: {!r}".format(e))
                return None

            # Ensure we have a proper 3‑channel image
            if not isinstance(image_np, np.ndarray) or image_np.ndim < 2:
                self.logger.warning("MiniCameraSensor received invalid image array")
                return None

            # Update and occasionally log effective receive rate
            self._frames_since_log += 1
            now = time.time()
            if now - self._last_rate_log_time >= 5.0:
                fps = self._frames_since_log / (now - self._last_rate_log_time)
                self.logger.debug(
                    "MiniCameraSensor receiving ~{fps:.1f} fps from Android camera".format(
                        fps=fps
                    )
                )
                self._frames_since_log = 0
                self._last_rate_log_time = now

            # Optional send-FPS limiting: drop frames if sending too fast into Redis
            if self._send_fps > 0.0 and self._last_sent_time > 0.0:
                min_interval = 1.0 / self._send_fps
                if now - self._last_sent_time < min_interval:
                    return None

            msg = CompressedImageMessage(image_np)
            # Store the original capture timestamp (seconds since epoch) for latency analysis
            msg.image_timestamp = timestamp_ms / 1000.0
            self._last_sent_time = now
            return msg

        except socket.error as e:
            self.logger.error("MiniCameraSensor socket error: {err}".format(err=e))
            try:
                if self.client_conn:
                    self.client_conn.close()
            except Exception:
                pass
            self.client_conn = None
            return None

    def _cleanup(self):
        self.logger.info("MiniCameraSensor cleanup: closing sockets")
        # Ask the Android side to shut down the camera activity if it is still running.
        self.stop_app("com.example.alphamini.camera", ".CameraActivity")
        try:
            if self.client_conn:
                self.client_conn.close()
        except Exception:
            pass
        try:
            self.server_socket.close()
        except Exception:
            pass


class MiniCamera(SICConnector):
    component_class = MiniCameraSensor
    component_group = "Alphamini"


if __name__ == "__main__":
    SICComponentManager([MiniCameraSensor])

