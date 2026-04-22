from __future__ import annotations

import argparse
import base64
import os
import queue
import sys
import threading
import time
import wave
import builtins
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from sic_framework.core import sic_logging
from sic_framework.core.message_python2 import AudioRequest
from sic_framework.core.sic_application import SICApplication
from sic_framework.devices.desktop import Desktop

# _LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
# os.makedirs(_LOG_DIR, exist_ok=True)

# # IMPORTANT: this MCP server uses stdio transport, where stdout must be ONLY JSON-RPC.
# # The SIC framework's client logger prints Redis log messages to stdout by default,
# # which corrupts the JSON stream. We silence terminal printing by raising the
# # threshold above CRITICAL, while still writing logs to files.
# sic_logging.set_log_file(_LOG_DIR)
# sic_logging.SIC_CLIENT_LOG.threshold = sic_logging.CRITICAL + 1

# # SIC prints Redis log messages using a bare `print(...)` in `sic_logging.py`.
# # Redirect that module-level print to stderr so it cannot corrupt MCP's stdout JSON-RPC.
# def _sic_print_to_stderr(*args, **kwargs):
#     kwargs.setdefault("file", sys.stderr)
#     return builtins.print(*args, **kwargs)


# sic_logging.print = _sic_print_to_stderr  # type: ignore[attr-defined]

# # Encourage line-buffered stderr (helps in terminals).
# try:
#     sys.stderr.reconfigure(line_buffering=True)
# except Exception:
#     pass


class DesktopMCPServer(SICApplication):
    """
    MCP server that uses the local Desktop device.

    This class owns the `Desktop` device instance and lets the MCP tools send
    commands without having to manage the full SIC lifecycle themselves.
    """

    def __init__(self):
        super(DesktopMCPServer, self).__init__()

        self.set_log_level(sic_logging.DEBUG)
        self.set_log_file_path("/Users/landon/Desktop/School/THESIS/NEW_PROJECT/RobotDetective/logs")
        self.setup()

    def setup(self) -> None:
        """Initialize the Desktop device."""
        self.desktop = Desktop()
        self.desktop.speakers._ping()
        self.desktop.mic._ping()


# Global application instance used by MCP tools.
APP: Optional[SICApplication] = None
MIC_STREAM_STATE: Dict[str, Any] = {
    "active": False,
    "queue": queue.Queue(maxsize=64),
    "lock": threading.Lock(),
    "callback_registered": False,
}

mcp = FastMCP("Desktop MCP Server", json_response=True)

def _ensure_connected() -> DesktopMCPServer:
    """
    Ensure the global NAO application is connected.

    - If already connected, returns the existing app.
    """
    global APP

    if APP is not None and getattr(APP, "desktop", None) is not None:
        return APP  # type: ignore[return-value]

    candidate = DesktopMCPServer()

    # SICApplication is a process-wide singleton. If an instance was created
    # earlier as SICApplication, constructing DesktopMCPServer can return that
    # base instance and skip DesktopMCPServer.__init__. In that case, ensure
    # desktop-specific fields are initialized here.
    if getattr(candidate, "desktop", None) is None:
        candidate.set_log_level(sic_logging.DEBUG)
        candidate.set_log_file_path("/Users/landon/Desktop/School/THESIS/NEW_PROJECT/RobotDetective/logs")
        candidate.desktop = Desktop()
        candidate.desktop.speakers._ping()
        candidate.desktop.mic._ping()

    APP = candidate
    return APP  # type: ignore[return-value]


def _mic_on_message(message: Any) -> None:
    """Receive desktop mic messages and enqueue JSON-safe chunks."""
    if not MIC_STREAM_STATE["active"]:
        return

    waveform = getattr(message, "waveform", None)
    if not isinstance(waveform, (bytes, bytearray)):
        return

    payload = {
        "sample_rate": int(getattr(message, "sample_rate", 44100)),
        "waveform_b64": base64.b64encode(bytes(waveform)).decode("ascii"),
        "timestamp": float(getattr(message, "_timestamp", time.time())),
    }

    try:
        MIC_STREAM_STATE["queue"].put_nowait(payload)
    except queue.Full:
        # Keep stream live by dropping oldest chunk if needed.
        try:
            MIC_STREAM_STATE["queue"].get_nowait()
            MIC_STREAM_STATE["queue"].put_nowait(payload)
        except Exception:
            pass


def _drain_mic_queue() -> None:
    q = MIC_STREAM_STATE["queue"]
    while not q.empty():
        try:
            q.get_nowait()
        except Exception:
            break


@mcp.tool()
def connect() -> str:
    """
    One-time connection setup to the robot.

    If `robot_ip` is omitted, `ROBOT_IP` is used (falling back to `NAO_IP`).

    `nao_ip` is supported for backward compatibility and is treated as `robot_ip`
    if `robot_ip` is not provided.
    """
    app = _ensure_connected()
    return f"Connected to Desktop."


@mcp.tool()
def play_audio(wav_path: str) -> str:
    """
    Play a local WAV file through the Desktop speakers.

    The file is read by the MCP server process and sent as an AudioRequest to SIC.
    """
    if not wav_path or not isinstance(wav_path, str):
        return "ERROR: wav_path must be a non-empty string."

    app = _ensure_connected()
    path = os.path.expanduser(wav_path)
    if not os.path.isfile(path):
        return f"ERROR: WAV file not found: {path}"

    try:
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        if channels != 1:
            return f"ERROR: WAV must be mono (1 channel). Got {channels} channels."
        if sample_width != 2:
            return f"ERROR: WAV must be 16-bit PCM (sample width 2). Got {sample_width}."

        app.desktop.speakers.request(AudioRequest(sample_rate=sample_rate, waveform=frames))
        app.logger.info("Played WAV '%s' at %d Hz (%d bytes).", path, sample_rate, len(frames))
        return f"Playing '{os.path.basename(path)}' at {sample_rate} Hz."
    except Exception as exc:
        app.logger.error("Failed to play WAV '%s': %r", path, exc)
        return f"ERROR: Failed to play WAV: {exc!r}"


@mcp.tool()
def play_audio_bytes(waveform_b64: str, sample_rate: int = 44100) -> str:
    """
    Play base64-encoded PCM16 mono audio through Desktop speakers.
    """
    if not waveform_b64 or not isinstance(waveform_b64, str):
        return "ERROR: waveform_b64 must be a non-empty base64 string."
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        return "ERROR: sample_rate must be a positive integer."

    app = _ensure_connected()
    try:
        waveform = base64.b64decode(waveform_b64.encode("ascii"), validate=True)
        app.desktop.speakers.request(AudioRequest(sample_rate=sample_rate, waveform=waveform))
        return f"Played audio bytes at {sample_rate} Hz ({len(waveform)} bytes)."
    except Exception as exc:
        app.logger.error("Failed to play base64 audio bytes: %r", exc)
        return f"ERROR: Failed to play base64 audio bytes: {exc!r}"


@mcp.tool()
def listen(sample_rate: int = 44100) -> str:
    """
    Start streaming audio input from the Desktop microphone.
    """
    app = _ensure_connected()
    with MIC_STREAM_STATE["lock"]:
        if not MIC_STREAM_STATE["callback_registered"]:
            app.desktop.mic.register_callback(_mic_on_message)
            MIC_STREAM_STATE["callback_registered"] = True

        _drain_mic_queue()
        app.desktop.mic.request(AudioRequest(sample_rate=sample_rate, waveform=b""))
        MIC_STREAM_STATE["active"] = True

    return "Desktop microphone streaming started."


@mcp.tool()
def read_audio_chunk(timeout_s: float = 1.0) -> dict:
    """
    Read the next queued desktop microphone audio chunk.

    Returns:
      - {"ok": True, "sample_rate": int, "waveform_b64": str, "timestamp": float}
      - {"ok": True, "empty": True} when no chunk is available before timeout
      - {"ok": False, "error": "stream_not_active"} if listen() has not been called
    """
    if not MIC_STREAM_STATE["active"]:
        return {"ok": False, "error": "stream_not_active"}

    try:
        chunk = MIC_STREAM_STATE["queue"].get(timeout=timeout_s)
        chunk["ok"] = True
        return chunk
    except queue.Empty:
        return {"ok": True, "empty": True}


@mcp.tool()
def stop_listen() -> str:
    """
    Stop desktop microphone streaming and clear queued chunks.
    """
    with MIC_STREAM_STATE["lock"]:
        MIC_STREAM_STATE["active"] = False
        _drain_mic_queue()
    return "Desktop microphone streaming stopped."

@mcp.tool()
def shutdown_device() -> str:
    """
    Explicitly shut down the SIC application and disconnect from the Device.
    """
    global APP
    if APP is None:
        return "Desktop MCP server is not running."

    try:
        APP.shutdown()
    except SystemExit:
        # SICApplication.shutdown() ultimately calls sys.exit(0); swallow it
        # here so the MCP server process can remain alive if desired.
        pass

    APP = None
    return "Desktop MCP server has been shut down."


def main() -> None:
    """
    Entry point for running this module as an MCP server.

    The server can start without connecting to a robot. To connect, call the
    `connect` tool with an explicit `robot_ip` (or `nao_ip`) or set `ROBOT_IP`
    (or `NAO_IP`) and then call `connect`.
    """
    parser = argparse.ArgumentParser(
        description="MCP server exposing tools to control Desktop via SIC."
    )
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport to use (default: stdio).",
    )
    args = parser.parse_args()

    try:
        mcp.run(transport=args.transport)
    finally:
        # Ensure SICApplication shutdown is always invoked when the MCP server
        # stops, so that all devices and connectors are cleaned up.
        if APP is not None:
            try:
                APP.shutdown()
            except SystemExit:
                # SICApplication.exit_handler will call sys.exit(0); ignore it
                # here so that normal process teardown can continue.
                pass


if __name__ == "__main__":
    main()