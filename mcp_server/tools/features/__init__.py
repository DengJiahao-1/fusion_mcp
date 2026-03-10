"""
特征工具模块。

将原来的 features.py 拆分为多个子模块以提高可维护性。
"""

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client

from . import primitives, operations, modifications, other, queries

__all__ = ["register"]


def register(app: FastMCP, client: Fusion360Client) -> None:
    """
    注册所有特征相关工具。
    
    Args:
        app: FastMCP 应用实例
        client: Fusion 360 HTTP 客户端
    """
    primitives.register(app, client)
    operations.register(app, client)
    modifications.register(app, client)
    other.register(app, client)
    queries.register(app, client)

