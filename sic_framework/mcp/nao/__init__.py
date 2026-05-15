"""
NAO MCP server, client helpers, and expression catalog.
"""

from sic_framework.mcp.nao.nao_client import (
    DEFAULT_SSE_MCP_URL,
    MCP_SERVER_MODULE,
    MCP_SERVER_NAME,
    McpClientTransport,
    NAO_MCP_CLIENT,
    mcp_sse_connection,
    mcp_stdio_connection,
    nao_mcp_session_log_dir,
    print_mcp_sse_connection_help,
    print_mcp_stdio_spawn_help,
    require_robot_ip,
    resolve_robot_ip,
)
from sic_framework.mcp.nao.nao_expressions import (
    CATALOG_VERSION,
    NAO_EXPRESSIONS,
    ROBOT_TYPE,
    get_expressions_json,
    play_nao_expression,
)

__all__ = [
    "CATALOG_VERSION",
    "DEFAULT_SSE_MCP_URL",
    "MCP_SERVER_MODULE",
    "MCP_SERVER_NAME",
    "McpClientTransport",
    "NAO_EXPRESSIONS",
    "NAO_MCP_CLIENT",
    "ROBOT_TYPE",
    "get_expressions_json",
    "mcp_sse_connection",
    "mcp_stdio_connection",
    "nao_mcp_session_log_dir",
    "play_nao_expression",
    "print_mcp_sse_connection_help",
    "print_mcp_stdio_spawn_help",
    "require_robot_ip",
    "resolve_robot_ip",
]


def __getattr__(name: str):
    if name in ("configure_mcp_server_log_dir", "main"):
        from sic_framework.mcp.nao import nao_mcp_server

        return getattr(nao_mcp_server, name)
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
