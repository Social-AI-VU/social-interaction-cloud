from __future__ import annotations

import argparse
import base64
import os
import queue
import time
import wave
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from sic_framework.core import sic_logging
from sic_framework.core.message_python2 import AudioRequest
from sic_framework.core.sic_application import SICApplication
from sic_framework.devices import Pepper
from sic_framework.devices.common_naoqi.naoqi_text_to_speech import NaoqiTextToSpeechRequest


class PepperMCPServer(SICApplication):
    """
    MCP server wrapper around a Pepper device.
    """

    def __init__(self, robot_ip: str):
        super(PepperMCPServer, self).__init__()
        self.robot_ip = robot_ip
        self.pepper: Optional[Pepper] = None

        self.set_log_level(sic_logging.DEBUG)
        self.set_log_file_path("/Users/landon/Desktop/School/THESIS/NEW_PROJECT/RobotDetective/logs")
        self.setup()

    def setup(self) -> None:
        self.pepper = Pepper(ip=self.robot_ip)


APP: Optional[PepperMCPServer] = None
MIC_STREAM_STATE: Dict[str, Any] = {
    "active": False,
    "sample_rate": 16000,
    "queue": queue.Queue(maxsize=64),
}

mcp = FastMCP("Pepper MCP Server", json_response=True)


def _resolve_robot_ip(robot_ip: Optional[str]) -> str:
    if robot_ip and robot_ip.strip():
        return robot_ip.strip()
    env_ip = os.getenv("ROBOT_IP", "").strip()
    if env_ip:
        return env_ip
    env_ip = os.getenv("PEPPER_IP", "").strip()
    if env_ip:
        return env_ip
    raise RuntimeError(
        "No robot IP provided. Pass robot_ip to connect() or set ROBOT_IP/PEPPER_IP."
    )


def _ensure_connected(robot_ip: Optional[str] = None) -> PepperMCPServer:
    global APP
    if APP is not None and getattr(APP, "pepper", None) is not None:
        return APP
    ip = _resolve_robot_ip(robot_ip)
    APP = PepperMCPServer(robot_ip=ip)
    return APP


def _require_pepper(app: PepperMCPServer) -> Pepper:
    pepper = getattr(app, "pepper", None)
    if pepper is None:
        raise RuntimeError("Pepper device is not initialized.")
    return pepper


@mcp.tool()
def connect(robot_ip: Optional[str] = None) -> str:
    app = _ensure_connected(robot_ip=robot_ip)
    return f"Connected to Pepper at {app.robot_ip}."


@mcp.tool()
def say_text(text: str, animated: bool = False, language: str = "English") -> str:
    if not text or not isinstance(text, str):
        return "ERROR: text must be a non-empty string."
    app = _ensure_connected()
    try:
        pepper = _require_pepper(app)
        pepper.tts.request(NaoqiTextToSpeechRequest(text, animated=animated, language=language))
        return f"Pepper said: {text}"
    except Exception as exc:
        app.logger.error("Failed Pepper TTS: %r", exc)
        return f"ERROR: Failed Pepper TTS: {exc!r}"


@mcp.tool()
def play_audio(wav_path: str) -> str:
    if not wav_path or not isinstance(wav_path, str):
        return "ERROR: wav_path must be a non-empty string."
    app = _ensure_connected()
    path = os.path.expanduser(wav_path)
    if not os.path.isfile(path):
        return f"ERROR: WAV file not found: {path}"
    try:
        pepper = _require_pepper(app)
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        if channels != 1:
            return f"ERROR: WAV must be mono (1 channel). Got {channels}."
        if sample_width != 2:
            return f"ERROR: WAV must be 16-bit PCM. Got sample width {sample_width}."
        pepper.speaker.request(AudioRequest(sample_rate=sample_rate, waveform=frames))
        return f"Playing '{os.path.basename(path)}' at {sample_rate} Hz."
    except Exception as exc:
        app.logger.error("Failed to play WAV on Pepper: %r", exc)
        return f"ERROR: Failed to play WAV: {exc!r}"


@mcp.tool()
def play_audio_bytes(waveform_b64: str, sample_rate: int = 16000) -> str:
    if not waveform_b64 or not isinstance(waveform_b64, str):
        return "ERROR: waveform_b64 must be a non-empty base64 string."
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        return "ERROR: sample_rate must be a positive integer."
    app = _ensure_connected()
    try:
        pepper = _require_pepper(app)
        waveform = base64.b64decode(waveform_b64.encode("ascii"), validate=True)
        pepper.speaker.request(AudioRequest(sample_rate=sample_rate, waveform=waveform))
        return f"Played audio bytes at {sample_rate} Hz ({len(waveform)} bytes)."
    except Exception as exc:
        app.logger.error("Failed to play base64 audio on Pepper: %r", exc)
        return f"ERROR: Failed to play base64 audio: {exc!r}"


@mcp.tool()
def listen(sample_rate: int = 16000) -> str:
    MIC_STREAM_STATE["active"] = True
    MIC_STREAM_STATE["sample_rate"] = int(sample_rate)
    return "Pepper microphone streaming started."


@mcp.tool()
def read_audio_chunk(timeout_s: float = 1.0) -> dict:
    if not MIC_STREAM_STATE["active"]:
        return {"ok": False, "error": "stream_not_active"}

    app = _ensure_connected()
    try:
        pepper = _require_pepper(app)
        sample_rate = int(MIC_STREAM_STATE["sample_rate"])
        msg = pepper.mic.request(AudioRequest(sample_rate=sample_rate, waveform=b""))
        waveform = getattr(msg, "waveform", b"")
        return {
            "ok": True,
            "sample_rate": int(getattr(msg, "sample_rate", sample_rate)),
            "waveform_b64": base64.b64encode(bytes(waveform)).decode("ascii"),
            "timestamp": float(getattr(msg, "_timestamp", time.time())),
        }
    except Exception as exc:
        app.logger.error("Failed Pepper listen: %r", exc)
        return {"ok": False, "error": repr(exc)}


@mcp.tool()
def stop_listen() -> str:
    MIC_STREAM_STATE["active"] = False
    return "Pepper microphone streaming stopped."


@mcp.tool()
def shutdown_robot() -> str:
    global APP
    if APP is None:
        return "Pepper MCP server is not running."
    try:
        APP.shutdown()
    except SystemExit:
        pass
    APP = None
    return "Pepper MCP server has been shut down."


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server exposing tools to control Pepper via SIC.")
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport to use (default: stdio).",
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
