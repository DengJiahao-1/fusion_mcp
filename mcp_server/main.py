"""
Fusion 360 MCP Server 主入口。
"""

from __future__ import annotations

from mcp_server import create_app


def main() -> None:
    """
    启动 MCP 服务器。
    """

    app, settings = create_app()

    if settings.transport in {"http", "streamable-http", "sse"}:
        app.run(transport=settings.transport, host=settings.host, port=settings.port)
    else:
        app.run(transport=settings.transport)


if __name__ == "__main__":
    main()
