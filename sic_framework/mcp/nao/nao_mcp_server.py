from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import wave
from typing import Any, Optional, Tuple

from mcp.server.fastmcp import FastMCP

from sic_framework.core.message_python2 import AudioRequest
from sic_framework.core.utils import extract_google_stt_transcript
from sic_framework.devices import Nao
from sic_framework.mcp.mcp_server import (
    SICMcpServer,
    call_tool_text,
    log_server_message,
    run_mcp_server,
)
from sic_framework.devices.common_naoqi.naoqi_leds import NaoFadeRGBRequest
from sic_framework.devices.common_naoqi.naoqi_text_to_speech import (
    NaoqiTextToSpeechRequest,
)
from sic_framework.mcp.nao.nao_client import require_robot_ip
from sic_framework.mcp.nao.nao_expressions import (
    get_expressions_json,
    play_nao_expression,
)
from sic_framework.mcp.mcp_client import NAO_STT_CONF_ENV
from sic_framework.services.google_stt.google_stt import (
    GetStatementRequest,
    GoogleSpeechToText,
    GoogleSpeechToTextConf,
)

LISTEN_REQUEST_TIMEOUT_S = 28.0

STT_CONF: Optional[dict] = None


def _google_stt_conf_from_dict(data: dict) -> GoogleSpeechToTextConf:
    keyfile_json = data.get("keyfile_json")
    if keyfile_json is None:
        keyfile_path = data.get("google_keyfile")
        if not keyfile_path:
            raise ValueError(
                "STT config must include 'keyfile_json' or 'google_keyfile'."
            )
        with open(str(keyfile_path), encoding="utf-8") as f:
            keyfile_json = json.load(f)
    return GoogleSpeechToTextConf(
        keyfile_json=keyfile_json,
        sample_rate_hertz=int(data.get("sample_rate_hertz", 16000)),
        language=str(data.get("language", "en-US")),
        interim_results=bool(data.get("interim_results", False)),
        timeout=data.get("timeout"),
        model=str(data.get("model", "long")),
    )


class NaoMCPServer(SICMcpServer):
    """
    Minimal SIC application that connects to a NAO robot.

    This class owns the `Nao` device instance and lets the MCP tools send
    LED commands without having to manage the full SIC lifecycle themselves.
    """

    def __init__(
        self,
        nao_ip: str,
        stub: bool = False,
        stt_conf: Optional[dict] = None,
    ):
        super(NaoMCPServer, self).__init__()

        self.nao_ip: str = nao_ip
        self.stub: bool = stub
        self.nao: Optional[Nao] = None
        self.stt: Optional[GoogleSpeechToText] = None
        self._stt_conf = stt_conf

        self.setup()

    def setup(self) -> None:
        """Initialize NAO and optional Google STT (NAO mic) from STT config."""
        if self.stub:
            self.logger.info("STUB mode active. Skipping NAO device initialization.")
            return

        self.logger.info("Initializing NAO robot at %s...", self.nao_ip)
        self.nao = Nao(ip=self.nao_ip)

        if self._stt_conf:
            conf = _google_stt_conf_from_dict(self._stt_conf)
            self.stt = GoogleSpeechToText(
                conf=conf,
                input_source=self.nao.mic,
            )
            self.logger.info(
                "Google STT bound to NAO microphone (%s Hz).",
                conf.sample_rate_hertz,
            )

        self.logger.info("NAO MCP application setup complete.")


# Global application instance used by MCP tools.
APP: Optional[NaoMCPServer] = None
STUB_MODE: bool = False


mcp = FastMCP("Nao MCP Server", json_response=True)


def _require_app() -> NaoMCPServer:
    """Internal helper to ensure the global APP is available."""
    if APP is None or APP.nao is None:
        raise RuntimeError(
            "NAO LED application is not initialized. "
            "Set NAO_IP (or call 'connect') so the server can connect."
        )
    return APP


def _is_stub_enabled() -> bool:
    """Return True when NAO actions should be stubbed out."""
    return STUB_MODE


def _emit_stub_action(action: str) -> None:
    """Log stubbed NAO action to the configured log file only."""
    log_server_message("[NAO STUB] {}".format(action), app=APP)


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
        APP = NaoMCPServer(nao_ip=ip, stub=True, stt_conf=None)
        return APP

    if robot_ip is not None and robot_ip.strip():
        os.environ["ROBOT_IP"] = robot_ip.strip()
        # Back-compat: some tooling may still reference NAO_IP.
        os.environ["NAO_IP"] = robot_ip.strip()

    ip = require_robot_ip(None)
    APP = NaoMCPServer(nao_ip=ip, stub=False, stt_conf=STT_CONF)
    return APP


@mcp.tool()
def listen_for_speech() -> str:
    """
    Block until the user speaks on the NAO microphone (Google Speech-to-Text).

    Requires STT config via ``SIC_NAO_STT_CONF`` when the client spawns this server.
    """
    if _is_stub_enabled():
        _emit_stub_action("listen_for_speech (stub)")
        return ""

    app = _ensure_connected()
    if app.stt is None:
        return (
            "ERROR: Google STT is not configured. "
            "Spawn the MCP server with SIC_NAO_STT_CONF set (voice client does this automatically)."
        )
    try:
        result = app.stt.request(
            GetStatementRequest(),
            timeout=LISTEN_REQUEST_TIMEOUT_S,
        )
    except TimeoutError:
        return ""
    except Exception as exc:
        app.logger.error("listen_for_speech failed: %r", exc)
        return "ERROR: listen_for_speech failed: {!r}".format(exc)

    transcript = (extract_google_stt_transcript(result) or "").strip()
    if transcript:
        app.logger.info("[heard] %s", transcript)
    return transcript


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
def get_expressions() -> str:
    """
    Return a JSON catalog of expressions this robot can play.

    Use the id field of each entry as expression_id in play_expression.
    The catalog includes the play_expression parameter schema (required/optional
    fields differ per robot; on NAO, optional speed applies only to postures).
    """
    return get_expressions_json()


@mcp.tool()
def play_expression(expression_id: str, speed: Optional[float] = None) -> str:
    """
    Play a predefined expression (posture or animation) on the NAO.

    Call get_expressions() first to list valid expression_id values and defaults.
    For postures, speed (0.0-1.0) overrides the catalog default transition speed.
    """
    if not expression_id or not str(expression_id).strip():
        return "ERROR: expression_id must be a non-empty string."

    app = _ensure_connected()

    try:
        return play_nao_expression(
            app.nao,
            expression_id.strip(),
            speed=speed,
            stub=_is_stub_enabled(),
            logger=app.logger,
        )
    except KeyError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        app.logger.error("Failed to play expression %r: %r", expression_id, exc)
        return f"ERROR: Failed to play expression: {exc!r}"


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


async def stdio_client_stub_demo(server_args: list[str]) -> None:
    """
    Spawn this module as ``python -m sic_framework.mcp.nao.nao_mcp_server`` and exercise a few tools.

    Intended for local testing without a robot when ``server_args`` includes ``--stub``.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "sic_framework.mcp.nao.nao_mcp_server", *server_args],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("Connected:", init.serverInfo.name if init.serverInfo else init)

            listed = await session.list_tools()
            print("Tools:", ", ".join(t.name for t in listed.tools))

            for tool_name, arguments in (
                ("connect", {}),
                ("get_expressions", {}),
                ("play_expression", {"expression_id": "gesture_hey"}),
                ("set_eye_color_name", {"color_name": "cyan", "duration": 0.2}),
                ("say_text", {"text": "Hello from the MCP client demo.", "animated": False}),
                ("shutdown_robot", {}),
            ):
                out = await session.call_tool(tool_name, arguments)
                print(f"--- {tool_name}({arguments}) ---")
                print(call_tool_text(out))


def main_client_stub() -> None:
    """
    CLI entry for the stdio MCP client smoke test (spawns the NAO MCP server subprocess).

    Install the ``mcp`` PyPI package. For a real robot, pass ``--live`` and ensure SIC/NAO
    are configured; otherwise the server is started with ``--stub``.
    """
    parser = argparse.ArgumentParser(
        description="NAO MCP stdio client demo: spawn the server and call a few tools."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Spawn the server without --stub (requires working SIC + NAO).",
    )
    parser.add_argument(
        "--server-arg",
        action="append",
        default=[],
        dest="extra_server_args",
        metavar="ARG",
        help="Extra arguments for the server process, e.g. --transport sse. Repeatable.",
    )
    args = parser.parse_args()
    server_args: list[str] = ([] if args.live else ["--stub"]) + list(args.extra_server_args)

    try:
        asyncio.run(stdio_client_stub_demo(server_args))
    except ModuleNotFoundError as exc:
        if exc.name == "mcp":
            print(
                "Missing dependency 'mcp'. Install with: pip install mcp",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        raise


def _warmup_nao_app_before_serving() -> None:
    """
    Block until ``_ensure_connected()`` succeeds when a robot address is available.

    Runs before ``mcp.run()``. Status is written to the log file only (see ``--log-dir``).
    If no address is configured (non-stub), the server still starts and ``connect`` can
    supply ``robot_ip`` later.
    """
    if _is_stub_enabled():
        try:
            _ensure_connected()
        except Exception as exc:
            log_server_message(
                "NAO MCP: stub warmup failed: {!r}".format(exc), app=APP
            )
            sys.exit(1)
        log_server_message(
            "NAO MCP: stub application ready (stdio/SSE clients can call tools).",
            app=APP,
        )
        return

    ip = os.getenv("ROBOT_IP", "").strip() or os.getenv("NAO_IP", "").strip()
    if not ip:
        log_server_message(
            "NAO MCP: no ROBOT_IP/NAO_IP at startup; listening without a warm NAO link "
            "(use the `connect` tool or restart with --robot-ip / env).",
            app=APP,
        )
        return

    try:
        app = _ensure_connected()
    except Exception as exc:
        log_server_message(
            "NAO MCP: could not connect to NAO at {!r} before serving: {!r}\n"
            "Fix networking/SIC on the robot or clear ROBOT_IP to start cold.".format(
                ip, exc
            ),
            app=APP,
        )
        sys.exit(1)

    log_server_message(
        "NAO MCP: NAO application ready at {!r} (tools can run immediately).".format(
            app.nao_ip
        ),
        app=app,
    )


def _add_nao_server_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Run in stub mode: log intended NAO actions and skip robot connection.",
    )
    parser.add_argument(
        "--robot-ip",
        type=str,
        default=None,
        metavar="ADDR",
        help=(
            "Default NAO IP for this process (sets ROBOT_IP and NAO_IP). "
            "Ignored for robot hardware while --stub is set, but still exported for tools."
        ),
    )


def _configure_nao_server(args: argparse.Namespace) -> None:
    if args.robot_ip and args.robot_ip.strip():
        ip = args.robot_ip.strip()
        os.environ["ROBOT_IP"] = ip
        os.environ["NAO_IP"] = ip

    global STUB_MODE, STT_CONF
    STUB_MODE = bool(args.stub)
    raw = os.environ.get(NAO_STT_CONF_ENV, "").strip()
    if raw:
        STT_CONF = json.loads(raw)
    if STUB_MODE:
        _emit_stub_action("Server started in STUB mode.")


def main() -> None:
    """
    Entry point for running this module as an MCP server (also exposed as ``run-nao-mcp``).

    The server can start without connecting to a robot. To connect, call the
    ``connect`` tool, or pass ``--robot-ip`` / set ``ROBOT_IP`` / ``NAO_IP`` before
    starting so the first real tool call can resolve the NAO address.
    """
    run_mcp_server(
        mcp,
        description="MCP server exposing tools to control NAO via SIC.",
        configure=_configure_nao_server,
        warmup=_warmup_nao_app_before_serving,
        get_app=lambda: APP,
        extra_arguments=_add_nao_server_arguments,
    )


if __name__ == "__main__":
    main()