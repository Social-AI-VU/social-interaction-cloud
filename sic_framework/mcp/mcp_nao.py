from __future__ import annotations

import argparse
import os
import sys
import wave
import builtins
from typing import Optional, Tuple

from mcp.server.fastmcp import FastMCP

from sic_framework.core import sic_logging
from sic_framework.core.message_python2 import AudioRequest
from sic_framework.core.sic_application import SICApplication
from sic_framework.devices import Nao
from sic_framework.devices.common_naoqi.naoqi_leds import NaoFadeRGBRequest
from sic_framework.devices.common_naoqi.naoqi_text_to_speech import (
    NaoqiTextToSpeechRequest,
)

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

# IMPORTANT: this MCP server uses stdio transport, where stdout must be ONLY JSON-RPC.
# The SIC framework's client logger prints Redis log messages to stdout by default,
# which corrupts the JSON stream. We silence terminal printing by raising the
# threshold above CRITICAL, while still writing logs to files.
sic_logging.set_log_file(_LOG_DIR)
sic_logging.SIC_CLIENT_LOG.threshold = sic_logging.CRITICAL + 1

# SIC prints Redis log messages using a bare `print(...)` in `sic_logging.py`.
# Redirect that module-level print to stderr so it cannot corrupt MCP's stdout JSON-RPC.
def _sic_print_to_stderr(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    return builtins.print(*args, **kwargs)


sic_logging.print = _sic_print_to_stderr  # type: ignore[attr-defined]

# Encourage line-buffered stderr (helps in terminals).
try:
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


class NaoMCPServer(SICApplication):
    """
    Minimal SIC application that connects to a NAO robot and exposes LED control.

    This class owns the `Nao` device instance and lets the MCP tools send
    LED commands without having to manage the full SIC lifecycle themselves.
    """

    def __init__(self, nao_ip: str, stub: bool = False):
        super(NaoMCPServer, self).__init__()

        self.nao_ip: str = nao_ip
        self.stub: bool = stub
        self.nao: Optional[Nao] = None

        self.set_log_level(sic_logging.DEBUG)
        self.set_log_file("/Users/landon/Desktop/School/THESIS/NEW_PROJECT/RobotDetective/logs")
        self.setup()

    def setup(self) -> None:
        """Initialize the NAO device for LED control."""
        if self.stub:
            self.logger.info("STUB mode active. Skipping NAO device initialization.")
            return

        self.logger.info("Initializing NAO robot at %s for LED control...", self.nao_ip)
        # Use dev_test=True so we don't interfere with production devices by default.
        self.nao = Nao(ip=self.nao_ip)
        self.logger.info("NAO LED application setup complete.")


# Global application instance used by MCP tools.
APP: Optional[NaoMCPServer] = None
STUB_MODE: bool = False


mcp = FastMCP("Nao LED MCP Server", json_response=True)


def _require_app() -> NaoMCPServer:
    """Internal helper to ensure the global APP is available."""
    if APP is None or APP.nao is None:
        raise RuntimeError(
            "NAO LED application is not initialized. "
            "Set NAO_IP (or call 'connect') so the server can connect."
        )
    return APP


def _resolve_robot_ip(robot_ip: Optional[str]) -> str:
    if robot_ip and robot_ip.strip():
        return robot_ip.strip()
    env_ip = os.getenv("ROBOT_IP", "").strip()
    if env_ip:
        return env_ip
    env_ip = os.getenv("NAO_IP", "").strip()
    if env_ip:
        return env_ip
    raise RuntimeError(
        "No robot IP provided. Pass robot_ip to the 'connect' tool or set ROBOT_IP (or NAO_IP)."
    )


def _is_stub_enabled() -> bool:
    """Return True when NAO actions should be stubbed out."""
    return STUB_MODE


def _emit_stub_action(action: str) -> None:
    """Print stubbed NAO action to stderr (safe for MCP stdio transport)."""
    print(f"[NAO STUB] {action}", file=sys.stderr)


def _ensure_connected(robot_ip: Optional[str] = None) -> NaoMCPServer:
    """
    Ensure the global NAO application is connected.

    - If already connected, returns the existing app.
    - If `robot_ip` is provided, it is stored in `ROBOT_IP` (and `NAO_IP`) and used.
    - Otherwise, `ROBOT_IP` (or `NAO_IP`) must already be set.
    """
    global APP

    if APP is not None and (APP.nao is not None or _is_stub_enabled()):
        return APP

    if _is_stub_enabled():
        # In stub mode, skip all NAO connectivity and allow missing/placeholder IPs.
        ip = (robot_ip or os.getenv("ROBOT_IP") or os.getenv("NAO_IP") or "stub").strip()
        APP = NaoMCPServer(nao_ip=ip, stub=True)
        return APP

    if robot_ip is not None and robot_ip.strip():
        os.environ["ROBOT_IP"] = robot_ip.strip()
        # Back-compat: some tooling may still reference NAO_IP.
        os.environ["NAO_IP"] = robot_ip.strip()

    ip = _resolve_robot_ip(None)
    APP = NaoMCPServer(nao_ip=ip, stub=False)
    return APP


@mcp.tool()
def connect(robot_ip: Optional[str] = None, nao_ip: Optional[str] = None) -> str:
    """
    One-time connection setup to the robot.

    If `robot_ip` is omitted, `ROBOT_IP` is used (falling back to `NAO_IP`).

    `nao_ip` is supported for backward compatibility and is treated as `robot_ip`
    if `robot_ip` is not provided.
    """
    app = _ensure_connected(robot_ip=robot_ip or nao_ip)
    if _is_stub_enabled():
        msg = (
            f"STUB mode enabled. Skipping NAO connection "
            f"(robot_ip='{robot_ip or nao_ip or app.nao_ip}')."
        )
        _emit_stub_action(msg)
        return msg
    return f"Connected to NAO at {app.nao_ip}."


def _color_name_to_rgb(name: str) -> Tuple[float, float, float]:
    """
    Map a simple color name to RGB triplet in [0, 1].
    Defaults to white if the name is unknown.
    """
    table = {
        "red": (1.0, 0.0, 0.0),
        "green": (0.0, 1.0, 0.0),
        "blue": (0.0, 0.0, 1.0),
        "yellow": (1.0, 1.0, 0.0),
        "cyan": (0.0, 1.0, 1.0),
        "magenta": (1.0, 0.0, 1.0),
        "white": (1.0, 1.0, 1.0),
        "orange": (1.0, 0.5, 0.0),
        "purple": (0.5, 0.0, 0.5),
        "pink": (1.0, 0.75, 0.8),
        "off": (0.0, 0.0, 0.0),
    }
    return table.get(name.strip().lower(), (1.0, 1.0, 1.0))


@mcp.tool()
def set_eye_color_rgb(
    r: float,
    g: float,
    b: float,
    duration: float = 0.0,
    led_group: str = "FaceLeds",
) -> str:
    """
    Set the NAO eye LEDs to a specific RGB color.

    - `r`, `g`, `b` should be floats between 0.0 and 1.0.
    - `duration` is the fade duration in seconds (0 for instant change).
    - `led_group` defaults to "FaceLeds" which controls both eyes.
    """
    app = _ensure_connected()

    if _is_stub_enabled():
        msg = (
            f"Would set {led_group} to RGB ({r:.3f}, {g:.3f}, {b:.3f}) "
            f"over {duration:.2f}s."
        )
        _emit_stub_action(msg)
        return f"STUB: {msg}"

    try:
        app.nao.leds.request(
            NaoFadeRGBRequest(name=led_group, r=r, g=g, b=b, duration=duration)
        )
        app.logger.info(
            "Set %s to RGB=(%.3f, %.3f, %.3f) over %.2fs",
            led_group,
            r,
            g,
            b,
            duration,
        )
        return f"Set {led_group} to RGB ({r:.3f}, {g:.3f}, {b:.3f}) over {duration:.2f}s."
    except Exception as exc:
        app.logger.error("Failed to set eye color via RGB: %r", exc)
        return f"ERROR: Failed to set eye color: {exc!r}"


@mcp.tool()
def set_eye_color_name(
    color_name: str,
    duration: float = 0.0,
    led_group: str = "FaceLeds",
) -> str:
    """
    Set the NAO eye LEDs to a named color.

    Supported colors include: red, green, blue, yellow, cyan, magenta,
    white, orange, purple, pink, and off. Unknown names default to white.
    """
    app = _ensure_connected()
    r, g, b = _color_name_to_rgb(color_name)

    if _is_stub_enabled():
        msg = (
            f"Would set {led_group} to '{color_name}' "
            f"(RGB {r:.3f}, {g:.3f}, {b:.3f}) over {duration:.2f}s."
        )
        _emit_stub_action(msg)
        return f"STUB: {msg}"

    try:
        app.nao.leds.request(
            NaoFadeRGBRequest(name=led_group, r=r, g=g, b=b, duration=duration)
        )
        app.logger.info(
            "Set %s to color '%s' -> RGB=(%.3f, %.3f, %.3f) over %.2fs",
            led_group,
            color_name,
            r,
            g,
            b,
            duration,
        )
        return (
            f"Set {led_group} to '{color_name}' "
            f"(RGB {r:.3f}, {g:.3f}, {b:.3f}) over {duration:.2f}s."
        )
    except Exception as exc:
        app.logger.error("Failed to set eye color via name '%s': %r", color_name, exc)
        return f"ERROR: Failed to set eye color '{color_name}': {exc!r}"


@mcp.tool()
def play_audio(wav_path: str) -> str:
    """
    Play a local WAV file through the NAO's speakers.

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

        if _is_stub_enabled():
            msg = (
                f"Would play '{os.path.basename(path)}' at {sample_rate} Hz "
                f"({len(frames)} bytes)."
            )
            _emit_stub_action(msg)
            return f"STUB: {msg}"

        app.nao.speaker.request(AudioRequest(sample_rate=sample_rate, waveform=frames))
        app.logger.info("Played WAV '%s' at %d Hz (%d bytes).", path, sample_rate, len(frames))
        return f"Playing '{os.path.basename(path)}' at {sample_rate} Hz."
    except Exception as exc:
        app.logger.error("Failed to play WAV '%s': %r", path, exc)
        return f"ERROR: Failed to play WAV: {exc!r}"


@mcp.tool()
def say_text(text: str, animated: bool = False) -> str:
    """
    Make the NAO robot say the given text using its onboard TTS.

    - `text`: What the robot should say.
    - `animated`: If True, use animated speech (gestures, etc.) when available.
    """
    if not text or not isinstance(text, str):
        return "ERROR: text must be a non-empty string."

    app = _ensure_connected()
    if _is_stub_enabled():
        msg = f"Would say (animated={animated}): {text}"
        _emit_stub_action(msg)
        return f"STUB: {msg}"

    try:
        app.nao.tts.request(NaoqiTextToSpeechRequest(text, animated=animated))
        app.logger.info("NAO TTS said (animated=%s): %s", animated, text)
        return f"NAO said: {text}"
    except Exception as exc:
        app.logger.error("Failed to say text via TTS: %r", exc)
        return f"ERROR: Failed to say text: {exc!r}"


@mcp.tool()
def shutdown_robot() -> str:
    """
    Explicitly shut down the SIC application and disconnect from the robot.

    This is typically not required because the server will call shutdown
    automatically when it exits, but it can be useful for manual cleanup.
    """
    global APP
    if APP is None:
        return "NAO LED application is not running."

    if _is_stub_enabled():
        APP = None
        _emit_stub_action("Shutting down stub NAO application.")
        return "STUB: NAO LED application has been shut down."

    try:
        APP.shutdown()
    except SystemExit:
        # SICApplication.shutdown() ultimately calls sys.exit(0); swallow it
        # here so the MCP server process can remain alive if desired.
        pass

    APP = None
    return "NAO LED application has been shut down."


@mcp.tool()
def shutdown_nao() -> str:
    """
    Backward-compatible alias for `shutdown_robot`.
    """
    return shutdown_robot()


def main() -> None:
    """
    Entry point for running this module as an MCP server.

    The server can start without connecting to a robot. To connect, call the
    `connect` tool with an explicit `robot_ip` (or `nao_ip`) or set `ROBOT_IP`
    (or `NAO_IP`) and then call `connect`.
    """
    parser = argparse.ArgumentParser(
        description="MCP server exposing tools to control NAO eye LEDs via SIC."
    )
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport to use (default: stdio).",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Run in stub mode: print intended NAO actions and skip robot connection.",
    )
    args = parser.parse_args()

    global STUB_MODE
    STUB_MODE = bool(args.stub)
    if STUB_MODE:
        _emit_stub_action("Server started in STUB mode.")

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