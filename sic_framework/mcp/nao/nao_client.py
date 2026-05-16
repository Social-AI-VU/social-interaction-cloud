"""
NAO-specific MCP LangChain client configuration and helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from sic_framework.mcp.mcp_client import (
    DEFAULT_SSE_MCP_URL,
    NAO_STT_CONF_ENV,
    McpClientTransport,
    McpRobotClientConfig,
    mcp_sse_connection as _mcp_sse_connection,
    mcp_stdio_connection as _mcp_stdio_connection,
    print_mcp_sse_connection_help as _print_mcp_sse_connection_help,
    print_mcp_stdio_spawn_help as _print_mcp_stdio_spawn_help,
    require_robot_ip as _require_robot_ip,
    resolve_robot_ip as _resolve_robot_ip,
)

MCP_SERVER_MODULE = "sic_framework.mcp.nao.nao_mcp_server"
MCP_SERVER_NAME = "nao"
NAO_MIC_SAMPLE_RATE_HZ = 16000


def build_google_stt_conf(
    *,
    google_keyfile: str,
    language: str = "en-US",
    sample_rate_hertz: int = NAO_MIC_SAMPLE_RATE_HZ,
    interim_results: bool = False,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """
    Build a JSON-serializable Google STT config for the NAO MCP server subprocess.

    Passed via ``SIC_NAO_STT_CONF`` when spawning stdio MCP (see :func:`mcp_stdio_connection`).
    """
    with open(google_keyfile, encoding="utf-8") as f:
        keyfile_json = json.load(f)
    return {
        "keyfile_json": keyfile_json,
        "sample_rate_hertz": sample_rate_hertz,
        "language": language,
        "interim_results": interim_results,
        "timeout": timeout,
    }

def nao_mcp_session_log_dir(*, caller_file: str) -> str:
    """
    Default SIC log directory for NAO MCP demo clients (under sic_applications/logs/mcp).
    """
    root = Path(caller_file).resolve().parent.parent.parent
    log_dir = root / "logs" / "mcp"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir)


NAO_MCP_CLIENT = McpRobotClientConfig(
    server_name=MCP_SERVER_NAME,
    mcp_server_module=MCP_SERVER_MODULE,
    robot_display_name="NAO",
    run_server_command="run-nao-mcp",
    extra_ip_env_vars=("NAO_IP",),
)


def resolve_robot_ip(robot_ip: Optional[str] = None) -> Optional[str]:
    return _resolve_robot_ip(
        robot_ip, extra_ip_env_vars=NAO_MCP_CLIENT.extra_ip_env_vars
    )


def require_robot_ip(robot_ip: Optional[str] = None) -> str:
    return _require_robot_ip(
        robot_ip,
        extra_ip_env_vars=NAO_MCP_CLIENT.extra_ip_env_vars,
        robot_display_name=NAO_MCP_CLIENT.robot_display_name,
    )


def mcp_sse_connection(*, url: str) -> dict[str, dict[str, Any]]:
    return _mcp_sse_connection(server_name=NAO_MCP_CLIENT.server_name, url=url)


def mcp_stdio_connection(
    *,
    robot_ip: Optional[str],
    server_stub: bool,
    extra_server_args: list[str],
    log_dir: Optional[str] = None,
    stt_conf: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    return _mcp_stdio_connection(
        config=NAO_MCP_CLIENT,
        robot_ip=robot_ip,
        server_stub=server_stub,
        extra_server_args=extra_server_args,
        log_dir=log_dir,
        stt_conf=stt_conf,
    )


def print_mcp_sse_connection_help(
    *,
    url: str,
    exc: BaseException,
    user_supplied_url: bool,
    extra_hint: str = "",
) -> None:
    _print_mcp_sse_connection_help(
        config=NAO_MCP_CLIENT,
        url=url,
        exc=exc,
        user_supplied_url=user_supplied_url,
        extra_hint=extra_hint,
    )


def print_mcp_stdio_spawn_help(exc: BaseException, *, extra_lines: str = "") -> None:
    _print_mcp_stdio_spawn_help(
        exc, config=NAO_MCP_CLIENT, extra_lines=extra_lines
    )


__all__ = [
    "DEFAULT_SSE_MCP_URL",
    "MCP_SERVER_MODULE",
    "MCP_SERVER_NAME",
    "McpClientTransport",
    "NAO_MIC_SAMPLE_RATE_HZ",
    "NAO_MCP_CLIENT",
    "NAO_STT_CONF_ENV",
    "build_google_stt_conf",
    "mcp_sse_connection",
    "mcp_stdio_connection",
    "nao_mcp_session_log_dir",
    "print_mcp_sse_connection_help",
    "print_mcp_stdio_spawn_help",
    "require_robot_ip",
    "resolve_robot_ip",
]
