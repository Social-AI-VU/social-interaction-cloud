"""
Robot-agnostic LangChain MCP client helpers (connections, env IP, CLI errors).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional, Sequence

from sic_framework.core.utils import format_exception_message

McpClientTransport = Literal["stdio", "sse"]
DEFAULT_SSE_MCP_URL = "http://127.0.0.1:8000/sse"
PRIMARY_ROBOT_IP_ENV = "ROBOT_IP"
# Voice clients pass Google STT settings to the stdio MCP subprocess via this env var.
ROBOT_STT_CONF_ENV = "SIC_ROBOT_STT_CONF"


@dataclass(frozen=True)
class McpRobotClientConfig:
    """
    Per-robot settings for MCP LangChain client connections and CLI messages.

    ``server_name`` is the key in MultiServerMCPClient connection dicts and the
    argument to ``MultiServerMCPClient.session(...)``.
    """

    server_name: str
    mcp_server_module: str
    robot_display_name: str
    run_server_command: str
    extra_ip_env_vars: tuple[str, ...] = ()
    stdio_extra_env: Mapping[str, str] = field(default_factory=dict)


def resolve_robot_ip(
    robot_ip: Optional[str] = None,
    *,
    extra_ip_env_vars: Sequence[str] = (),
) -> Optional[str]:
    """
    Resolve robot IP from an explicit value, ``ROBOT_IP``, then optional env keys.

    Returns None if no IP is configured.
    """
    if robot_ip and str(robot_ip).strip():
        return str(robot_ip).strip()
    for key in (PRIMARY_ROBOT_IP_ENV,) + tuple(extra_ip_env_vars):
        env_ip = os.getenv(key, "").strip()
        if env_ip:
            return env_ip
    return None


def require_robot_ip(
    robot_ip: Optional[str] = None,
    *,
    extra_ip_env_vars: Sequence[str] = (),
    robot_display_name: str = "robot",
) -> str:
    """Like :func:`resolve_robot_ip`, but raises if no IP is available."""
    ip = resolve_robot_ip(robot_ip, extra_ip_env_vars=extra_ip_env_vars)
    if not ip:
        env_hint = PRIMARY_ROBOT_IP_ENV
        if extra_ip_env_vars:
            env_hint = "{}, or {}".format(
                PRIMARY_ROBOT_IP_ENV, " / ".join(extra_ip_env_vars)
            )
        raise RuntimeError(
            "No {robot} IP provided. Pass robot_ip or set {env}.".format(
                robot=robot_display_name, env=env_hint
            )
        )
    return ip


def mcp_sse_connection(*, server_name: str, url: str) -> dict[str, dict[str, Any]]:
    # Use when the MCP server is already running (e.g. run-nao-mcp --transport sse in another terminal).
    return {server_name: {"transport": "sse", "url": url}}


def mcp_stdio_connection(
    *,
    config: McpRobotClientConfig,
    robot_ip: Optional[str],
    server_stub: bool,
    extra_server_args: list[str],
    log_dir: Optional[str] = None,
    stt_conf: Optional[dict] = None,
) -> dict[str, dict[str, Any]]:
    server_args = ["-m", config.mcp_server_module]
    if server_stub:
        server_args.append("--stub")
    if robot_ip and robot_ip.strip():
        server_args.extend(["--robot-ip", robot_ip.strip()])
    if log_dir and str(log_dir).strip():
        server_args.extend(["--log-dir", os.path.abspath(str(log_dir).strip())])
    server_args.extend(extra_server_args)
    env = {**os.environ, **dict(config.stdio_extra_env)}
    if stt_conf is not None:
        # Server reads this JSON in main() so mic+STT live in one process (not the LangChain client).
        env[ROBOT_STT_CONF_ENV] = json.dumps(stt_conf)
    return {
        config.server_name: {
            # LangChain spawns the server module as a child process with these args/env.
            "transport": "stdio",
            "command": sys.executable,
            "args": server_args,
            "env": env,
        }
    }


def print_mcp_sse_connection_help(
    *,
    config: McpRobotClientConfig,
    url: str,
    exc: BaseException,
    user_supplied_url: bool,
    extra_hint: str = "",
) -> None:
    robot = config.robot_display_name
    print(
        "Could not connect to the {robot} MCP server (sse {url}).\n"
        "Reason: {reason}\n".format(
            robot=robot, url=url, reason=format_exception_message(exc)
        ),
        file=sys.stderr,
    )
    if user_supplied_url:
        print(
            "Check that the server is running at that URL and uses the SSE transport.\n",
            file=sys.stderr,
        )
    else:
        print(
            "No server was reachable on localhost. Either:\n"
            "  - Start one: {cmd} --transport sse --robot-ip <IP>\n"
            "  - Or pass the real URL: --mcp-url <url>  (tried {url!r})\n".format(
                cmd=config.run_server_command,
                url=url,
            ),
            file=sys.stderr,
        )
    if extra_hint:
        print(extra_hint, file=sys.stderr)


def print_mcp_stdio_spawn_help(
    exc: BaseException,
    *,
    config: McpRobotClientConfig,
    extra_lines: str = "",
) -> None:
    robot = config.robot_display_name
    print(
        "Could not start or talk to the {robot} MCP server subprocess (stdio).\n"
        "Reason: {reason}\n".format(
            robot=robot, reason=format_exception_message(exc)
        ),
        file=sys.stderr,
    )
    print(
        "Common fixes:\n"
        "  - Redis running on this machine (run-redis or local Redis on port 6379).\n"
        "  - Robot reachable: --robot-ip <IP> or test with --mcp-server-stub.\n"
        "  - Or use SSE in another tab: {cmd} --transport sse --robot-ip <IP>\n"
        "    then pass --transport sse on this client.\n"
        "  - Verify the server module: {exe} -m {mod} --help\n"
        "{extra}".format(
            cmd=config.run_server_command,
            exe=sys.executable,
            mod=config.mcp_server_module,
            extra=extra_lines,
        ),
        file=sys.stderr,
    )
