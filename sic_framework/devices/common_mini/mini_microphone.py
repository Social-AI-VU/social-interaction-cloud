import socket
import time
import subprocess

import numpy as np
import pyaudio

from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage
from sic_framework.core.sensor_python2 import SICSensor

class MiniMicrophoneSensor(SICSensor):
    COMPONENT_STARTUP_TIMEOUT = 5

    def __init__(self, *args, **kwargs):
        super(MiniMicrophoneSensor, self).__init__(*args, **kwargs)

        # audio settings
        self.sample_rate = 44000
        self.channels = 2 # stereo
        self.bytes_per_sample = 2  # 16-bit audio
        self.frame_size = 1024
        self.buffer_time_ms = 250  # buffer duration in ms
        self.buffer_size = int(self.sample_rate * (self.buffer_time_ms / 1000) * self.channels * self.bytes_per_sample)
        self.buffer_accumulator = b""

        # Set up TCP server socket
        self.host = "0.0.0.0"
        self.port = 5000
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.server_socket.settimeout(1.0)
        self.client_conn = None
        self.last_connection_time = time.time()

        self.logger.info(f"Listening for connections on {self.host}:{self.port}...")

        # Start android com.example.micarraytest app
        self.logger.info("Checking if Android app is running...")
        self.start_app("com.example.micarraytest", ".MainActivity")

        # pyaudio setup for debug playback
        # self.audio = pyaudio.PyAudio()
        # self.stream = self.audio.open(
        #     format=pyaudio.paInt16,
        #     channels=self.channels,
        #     rate=self.sample_rate,
        #     output=True
        # )

    def start_app(self, package_name, activity_name):
        # can't find a way to check if an app is running on Android
        # so we just try to start it anyway
        subprocess.run([
            "am", "start", "-n", f"{package_name}/{activity_name}"
        ])
        # this is the part if the file is running on a local machine
        # result = subprocess.run(
        #     ["adb", "shell", "pidof", package_name],
        #     capture_output=True, text=True
        # )
        # pid = result.stdout.strip()
        # if bool(pid):
        #     print(f"[INFO] App '{package_name}' is already running.")
        # else:
        #     print(f"[INFO] App '{package_name}' is NOT running. Starting it...")
        #     subprocess.run([
        #         "adb", "shell", "am", "start", "-n", f"{package_name}/{activity_name}"
        #     ])

    def execute(self):
        try:
            if not self.client_conn:
                try:
                    self.client_conn, addr = self.server_socket.accept()
                    self.logger.info(f"Connected by {addr}")
                except socket.timeout:
                    self.logger.info("No client connected, sending silence while waiting...")
                    # if can't connect to client for 5 seconds, restart app
                    current_time = time.time()
                    if current_time - self.last_connection_time > 5:
                        self.logger.warning("Lost connection for 5 seconds, restarting app...")
                        self.start_app("com.example.micarraytest", ".MainActivity")
                        self.last_connection_time = current_time
                    return AudioMessage(b"\x00", sample_rate=self.sample_rate)

            # receive audio until buffer is full
            while len(self.buffer_accumulator) < self.buffer_size:
                try:
                    chunk = self.client_conn.recv(self.frame_size)
                    if not chunk:
                        self.logger.error("Socket client disconnected")
                        self.client_conn.close()
                        self.client_conn = None
                        self.last_connection_time = time.time()
                        self.buffer_accumulator = b""
                        return AudioMessage(b"\x00", sample_rate=self.sample_rate)
                    self.buffer_accumulator += chunk
                except socket.timeout:
                    continue
            # process buffer by converting stereo to mono as dialogflow only accepts mono audio
            stereo_buffer = self.buffer_accumulator[:self.buffer_size]
            stereo_np = np.frombuffer(stereo_buffer, dtype=np.int16)
            mono_np = stereo_np.reshape(-1, 2).mean(axis=1).astype(np.int16)
            mono_buffer = mono_np.tobytes()

            # Debug playback
            # self.stream.write(stereo_buffer, exception_on_underflow=False)

            msg = AudioMessage(mono_buffer, sample_rate=self.sample_rate)
            self.buffer_accumulator = self.buffer_accumulator[self.buffer_size:]

            return msg

        except socket.error as e:
            self.logger.error(f"Socket error: {e}")

    def stop(self, *args):
        super(MiniMicrophoneSensor, self).stop(*args)
        self.logger.info("Stopped microphone")

        if self.client_conn:
            self.client_conn.close()
        self.server_socket.close()
        # self.stream.close()
        # self.audio.terminate()

class MiniMicrophone(SICConnector):
    component_class = MiniMicrophoneSensor

if __name__ == "__main__":
    SICComponentManager([MiniMicrophoneSensor])
