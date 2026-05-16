"""
Shared MCP server runtime: file-only SIC logging and common transport CLI.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP

from sic_framework.core import sic_logging
from sic_framework.core.sic_application import SICApplication

# Do not print SIC Redis client logs to the terminal in MCP server processes.
_TERMINAL_LOG_THRESHOLD = sic_logging.CRITICAL + 1
_log_dir: Optional[str] = None
_file_only_logging_installed = False


def get_mcp_server_log_dir() -> Optional[str]:
    """Return the log directory set by :func:`configure_mcp_server_log_dir`, if any."""
    return _log_dir


def configure_mcp_server_log_dir(path: str) -> str:
    """
    Enable SIC file logging under ``path``; nothing is written to the terminal.

    Call from ``main()`` before creating the robot SIC application.
    """
    global _log_dir
    # MCP stdio must not flood the JSON-RPC stream with Redis log lines on stderr.
    _log_dir = os.path.abspath(path.strip())
    os.makedirs(_log_dir, exist_ok=True)
    sic_logging.set_log_file(_log_dir)
    sic_logging.SIC_CLIENT_LOG.file_log_threshold = sic_logging.DEBUG
    install_mcp_server_file_only_logging()
    return _log_dir


def suppress_terminal_client_log() -> None:
    """Keep Redis log subscription but do not print SIC logs to stderr/stdout."""
    sic_logging.SIC_CLIENT_LOG.threshold = _TERMINAL_LOG_THRESHOLD


def _sic_print_to_logfile(*args, **kwargs) -> None:
    """Route framework print() calls to the log file when logging is configured."""
    if not sic_logging.SIC_CLIENT_LOG.write_to_logfile:
        return
    parts = [str(a) for a in args]
    end = kwargs.get("end", "\n")
    msg = " ".join(parts)
    if end and end != "\n":
        msg = msg + end
    elif not msg.endswith("\n"):
        msg = msg + "\n"
    sic_logging.SIC_CLIENT_LOG._write_to_logfile(msg)


def install_mcp_server_file_only_logging() -> None:
    """Install file-only ``sic_logging.print`` and terminal suppression (idempotent)."""
    global _file_only_logging_installed
    suppress_terminal_client_log()
    if not _file_only_logging_installed:
        sic_logging.print = _sic_print_to_logfile  # type: ignore[attr-defined]
        _file_only_logging_installed = True


def log_server_message(msg: str, *, app: Optional[SICApplication] = None) -> None:
    """Write a status line to the MCP server log file only."""
    if app is not None:
        app.logger.info(msg)
    else:
        sic_logging.print(msg)


class SICMcpServer(SICApplication):
    """
    SIC application base for MCP server processes.

    Skips signal/atexit handlers that call ``sys.exit`` and keeps SIC logs off the
    terminal (see :func:`configure_mcp_server_log_dir`).
    """

    def __new__(cls, *args, **kwargs):
        # MCP server apps are full subclasses; do not return the process-wide
        # SICApplication singleton (see SICApplication.__new__).
        return object.__new__(cls)

    def register_exit_handler(self) -> None:
        # Mark handlers as registered without wiring SIGINT/atexit that call sys.exit.
        self._shutdown_handler_registered = True

    def __init__(self) -> None:
        super(SICMcpServer, self).__init__()
        suppress_terminal_client_log()
        self.logger.setLevel(sic_logging.DEBUG)
        log_dir = get_mcp_server_log_dir()
        if log_dir:
            self.set_log_file_path(log_dir)


def add_mcp_server_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``--transport`` and ``--log-dir`` on an argument parser."""
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport to use (default: stdio).",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        required=True,
        metavar="DIR",
        help="Directory for SIC file logs (required; logs are not printed to stderr).",
    )


def run_mcp_server(
    mcp: FastMCP,
    *,
    description: str,
    configure: Callable[[argparse.Namespace], None],
    warmup: Callable[[], None],
    get_app: Callable[[], Optional[SICApplication]],
    extra_arguments: Optional[Callable[[argparse.ArgumentParser], None]] = None,
) -> None:
    """
    Parse CLI args, configure logging, run warmup, then ``mcp.run()``.

    ``configure`` runs after ``--log-dir`` is applied (set env, stub flags, etc.).
    ``get_app`` returns the global app for shutdown in ``finally``.
    """
    parser = argparse.ArgumentParser(description=description)
    add_mcp_server_arguments(parser)
    if extra_arguments is not None:
        extra_arguments(parser)
    args = parser.parse_args()

    configure_mcp_server_log_dir(args.log_dir.strip())
    # Robot-specific flags (stub, STT env, IP) are applied after logging is ready.
    configure(args)

    # Eager connect when IP is known so the first tool call does not pay cold-start cost.
    warmup()

    try:
        mcp.run(transport=args.transport)
    finally:
        app = get_app()
        if app is not None:
            try:
                app.shutdown()
            except SystemExit:
                # SICApplication.shutdown() may call sys.exit; keep the MCP process exit clean.
                pass


def call_tool_text(result: Any) -> str:
    """Flatten MCP ``CallToolResult`` content into a single string."""
    import mcp.types as mcp_types

    lines: list[str] = []
    for block in result.content:
        if isinstance(block, mcp_types.TextContent):
            lines.append(block.text)
    if lines:
        return "\n".join(lines)
    if getattr(result, "structuredContent", None):
        return str(result.structuredContent)
    return str(result)
