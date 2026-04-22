from __future__ import annotations

import argparse
import base64
import os
import queue
import time
import wave
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from mini import MouthLampColor, MouthLampMode

from sic_framework.core import sic_logging
from sic_framework.core.message_python2 import AudioRequest
from sic_framework.core.sic_application import SICApplication
from sic_framework.devices.alphamini import Alphamini, SDKAnimationType


class AlphaminiMCPServer(SICApplication):
    """
    MCP server wrapper around an Alphamini device.
    """

    def __init__(
        self,
        robot_ip: str,
        mini_id: str,
        mini_password: str,
        redis_ip: str,
    ):
        super(AlphaminiMCPServer, self).__init__()
        self.robot_ip = robot_ip
        self.mini_id = mini_id
        self.mini_password = mini_password
        self.redis_ip = redis_ip
        self.mini: Optional[Alphamini] = None

        self.set_log_level(sic_logging.DEBUG)
        self.set_log_file_path("/Users/landon/Desktop/School/THESIS/NEW_PROJECT/RobotDetective/logs")
        self.setup()

    def setup(self) -> None:
        self.mini = Alphamini(
            ip=self.robot_ip,
            mini_id=self.mini_id,
            mini_password=self.mini_password,
            redis_ip=self.redis_ip,
        )


APP: Optional[AlphaminiMCPServer] = None
MIC_STREAM_STATE: Dict[str, Any] = {
    "active": False,
    "sample_rate": 16000,
    "queue": queue.Queue(maxsize=64),
}

mcp = FastMCP("Alphamini MCP Server", json_response=True)


def _get_required_env(name: str, explicit: Optional[str]) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise RuntimeError(f"Missing required value for {name}.")


def _ensure_connected(
    robot_ip: Optional[str] = None,
    mini_id: Optional[str] = None,
    mini_password: Optional[str] = None,
    redis_ip: Optional[str] = None,
) -> AlphaminiMCPServer:
    global APP
    if APP is not None and getattr(APP, "mini", None) is not None:
        return APP
    APP = AlphaminiMCPServer(
        robot_ip=_get_required_env("ALPHAMINI_IP", robot_ip),
        mini_id=_get_required_env("ALPHAMINI_ID", mini_id),
        mini_password=_get_required_env("ALPHAMINI_PASSWORD", mini_password),
        redis_ip=_get_required_env("DB_IP", redis_ip),
    )
    return APP


def _require_mini(app: AlphaminiMCPServer) -> Alphamini:
    mini = getattr(app, "mini", None)
    if mini is None:
        raise RuntimeError("Alphamini device is not initialized.")
    return mini


@mcp.tool()
def connect(
    robot_ip: Optional[str] = None,
    mini_id: Optional[str] = None,
    mini_password: Optional[str] = None,
    redis_ip: Optional[str] = None,
) -> str:
    app = _ensure_connected(robot_ip, mini_id, mini_password, redis_ip)
    return f"Connected to Alphamini at {app.robot_ip} (id={app.mini_id})."


@mcp.tool()
def play_audio(wav_path: str) -> str:
    if not wav_path or not isinstance(wav_path, str):
        return "ERROR: wav_path must be a non-empty string."
    app = _ensure_connected()
    path = os.path.expanduser(wav_path)
    if not os.path.isfile(path):
        return f"ERROR: WAV file not found: {path}"
    try:
        mini = _require_mini(app)
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        if channels != 1:
            return f"ERROR: WAV must be mono (1 channel). Got {channels}."
        if sample_width != 2:
            return f"ERROR: WAV must be 16-bit PCM. Got sample width {sample_width}."
        mini.speaker.request(AudioRequest(sample_rate=sample_rate, waveform=frames))
        return f"Playing '{os.path.basename(path)}' at {sample_rate} Hz."
    except Exception as exc:
        app.logger.error("Failed to play WAV on Alphamini: %r", exc)
        return f"ERROR: Failed to play WAV: {exc!r}"


@mcp.tool()
def play_audio_bytes(waveform_b64: str, sample_rate: int = 16000) -> str:
    if not waveform_b64 or not isinstance(waveform_b64, str):
        return "ERROR: waveform_b64 must be a non-empty base64 string."
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        return "ERROR: sample_rate must be a positive integer."
    app = _ensure_connected()
    try:
        mini = _require_mini(app)
        waveform = base64.b64decode(waveform_b64.encode("ascii"), validate=True)
        mini.speaker.request(AudioRequest(sample_rate=sample_rate, waveform=waveform))
        return f"Played audio bytes at {sample_rate} Hz ({len(waveform)} bytes)."
    except Exception as exc:
        app.logger.error("Failed to play base64 audio on Alphamini: %r", exc)
        return f"ERROR: Failed to play base64 audio: {exc!r}"


@mcp.tool()
def listen(sample_rate: int = 16000) -> str:
    MIC_STREAM_STATE["active"] = True
    MIC_STREAM_STATE["sample_rate"] = int(sample_rate)
    return "Alphamini microphone streaming started."


@mcp.tool()
def read_audio_chunk(timeout_s: float = 1.0) -> dict:
    if not MIC_STREAM_STATE["active"]:
        return {"ok": False, "error": "stream_not_active"}

    app = _ensure_connected()
    try:
        mini = _require_mini(app)
        sample_rate = int(MIC_STREAM_STATE["sample_rate"])
        msg = mini.mic.request(AudioRequest(sample_rate=sample_rate, waveform=b""))
        waveform = getattr(msg, "waveform", b"")
        return {
            "ok": True,
            "sample_rate": int(getattr(msg, "sample_rate", sample_rate)),
            "waveform_b64": base64.b64encode(bytes(waveform)).decode("ascii"),
            "timestamp": float(getattr(msg, "_timestamp", time.time())),
        }
    except Exception as exc:
        app.logger.error("Failed Alphamini listen: %r", exc)
        return {"ok": False, "error": repr(exc)}


@mcp.tool()
def stop_listen() -> str:
    MIC_STREAM_STATE["active"] = False
    return "Alphamini microphone streaming stopped."


@mcp.tool()
def animate(animation_type: str, animation_id: str, run_async: bool = False) -> str:
    app = _ensure_connected()
    try:
        atype = SDKAnimationType(animation_type.strip().lower())
        mini = _require_mini(app)
        mini.animate(atype, animation_id, run_async=run_async)
        return f"Triggered animation {atype.value}:{animation_id}."
    except Exception as exc:
        app.logger.error("Failed Alphamini animation: %r", exc)
        return f"ERROR: Failed animation: {exc!r}"


@mcp.tool()
def set_mouth_lamp(
    color: str = "GREEN",
    mode: str = "NORMAL",
    duration: int = -1,
    breath_duration: int = 1000,
) -> str:
    app = _ensure_connected()
    try:
        mini = _require_mini(app)
        lamp_color = MouthLampColor[color.strip().upper()]
        lamp_mode = MouthLampMode[mode.strip().upper()]
        mini.set_mouth_lamp(
            lamp_color, lamp_mode, duration=duration, breath_duration=breath_duration
        )
        return (
            f"Set mouth lamp color={lamp_color.name} mode={lamp_mode.name} "
            f"duration={duration} breath_duration={breath_duration}."
        )
    except Exception as exc:
        app.logger.error("Failed setting mouth lamp: %r", exc)
        return f"ERROR: Failed setting mouth lamp: {exc!r}"


@mcp.tool()
def shutdown_robot() -> str:
    global APP
    if APP is None:
        return "Alphamini MCP server is not running."
    try:
        APP.shutdown()
    except SystemExit:
        pass
    APP = None
    return "Alphamini MCP server has been shut down."


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server exposing tools to control Alphamini via SIC.")
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
