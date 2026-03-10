"""
MCP 应用构建入口。
"""

from __future__ import annotations

from typing import Tuple

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client
from mcp_server.config import ServerSettings, load_settings
from mcp_server.tools import register_tools


def create_app() -> Tuple[FastMCP, ServerSettings]:
    """
    创建并配置 FastMCP 应用实例。

    Returns:
        FastMCP 应用与服务器配置
    """

    server_settings, fusion_settings, cst_settings = load_settings()
    app = FastMCP(server_settings.name)

    fusion_client = Fusion360Client(fusion_settings)
    register_tools(app, fusion_client, cst_settings)

    return app, server_settings

