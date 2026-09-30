"""Import FastMCP across Python MCP SDK 1.x and 2.x.

SDK 2.0 removed ``mcp.server.fastmcp.FastMCP`` and renamed the class to
``mcp.server.mcpserver.MCPServer``.
"""
from __future__ import annotations

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as FastMCP

__all__ = ["FastMCP"]
