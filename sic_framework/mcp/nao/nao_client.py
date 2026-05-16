"""
NAO-specific MCP LangChain client configuration and helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from sic_framework.mcp.mcp_client import (
    DEFAULT_SSE_MCP_URL,
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
    stdio_extra_env={"SIC_NAO_REUSE_REMOTE_SIC": "1"},
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
) -> dict[str, dict[str, Any]]:
    return _mcp_stdio_connection(
        config=NAO_MCP_CLIENT,
        robot_ip=robot_ip,
        server_stub=server_stub,
        extra_server_args=extra_server_args,
        log_dir=log_dir,
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
    "NAO_MCP_CLIENT",
    "mcp_sse_connection",
    "mcp_stdio_connection",
    "nao_mcp_session_log_dir",
    "print_mcp_sse_connection_help",
    "print_mcp_stdio_spawn_help",
    "require_robot_ip",
    "resolve_robot_ip",
]
