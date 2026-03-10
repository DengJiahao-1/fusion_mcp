"""
Fusion 360 MCP Server

一个基于 FastMCP 的 Fusion 360 Model Context Protocol 服务器实现。
"""

__version__ = "0.1.0"

from .app import create_app

__all__ = ["create_app", "__version__"]
