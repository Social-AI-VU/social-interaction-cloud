"""
Pepper MCP server, client helpers, and expression catalog.
"""

from sic_framework.mcp.pepper.pepper_client import (
    DEFAULT_SSE_MCP_URL,
    MCP_SERVER_MODULE,
    MCP_SERVER_NAME,
    McpClientTransport,
    ROBOT_STT_CONF_ENV,
    PEPPER_MCP_CLIENT,
    PEPPER_MIC_SAMPLE_RATE_HZ,
    build_google_stt_conf,
    mcp_sse_connection,
    mcp_stdio_connection,
    pepper_mcp_session_log_dir,
    print_mcp_sse_connection_help,
    print_mcp_stdio_spawn_help,
    require_robot_ip,
    resolve_robot_ip,
)
from sic_framework.mcp.pepper.pepper_expressions import (
    CATALOG_VERSION,
    PEPPER_EXPRESSIONS,
    ROBOT_TYPE,
    get_expressions_json,
    play_pepper_expression,
)

__all__ = [
    "CATALOG_VERSION",
    "DEFAULT_SSE_MCP_URL",
    "MCP_SERVER_MODULE",
    "MCP_SERVER_NAME",
    "McpClientTransport",
    "ROBOT_STT_CONF_ENV",
    "PEPPER_EXPRESSIONS",
    "PEPPER_MCP_CLIENT",
    "PEPPER_MIC_SAMPLE_RATE_HZ",
    "ROBOT_TYPE",
    "build_google_stt_conf",
    "get_expressions_json",
    "mcp_sse_connection",
    "mcp_stdio_connection",
    "pepper_mcp_session_log_dir",
    "play_pepper_expression",
    "print_mcp_sse_connection_help",
    "print_mcp_stdio_spawn_help",
    "require_robot_ip",
    "resolve_robot_ip",
]


def __getattr__(name: str):
    if name in ("configure_mcp_server_log_dir", "main"):
        from sic_framework.mcp.pepper import pepper_mcp_server

        return getattr(pepper_mcp_server, name)
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
