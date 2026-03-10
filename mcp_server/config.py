"""
MCP 服务器配置。

集中管理环境变量读取，便于后续扩展与测试。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv

# 提前加载 .env，避免重复调用
load_dotenv()


TransportType = Literal["http", "streamable-http", "sse", "stdio", "websocket"]


@dataclass(frozen=True)
class ServerSettings:
    """MCP 服务器运行时配置。"""

    name: str = "Fusion360MCP"
    transport: TransportType = "http"
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True)
class Fusion360Settings:
    """Fusion 360 插件服务配置。"""

    server_url: str = "http://localhost:9000"
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class CSTSettings:
    """CST Studio Suite Bridge 服务配置。"""

    server_url: str = "http://localhost:9001"
    timeout_seconds: float = 60.0  # 仿真可能较长
    enabled: bool = True  # 是否启用 CST 工具


@lru_cache(maxsize=1)
def load_settings() -> tuple[ServerSettings, Fusion360Settings, CSTSettings]:
    """
    读取环境变量并返回配置元组。

    Returns:
        (ServerSettings, Fusion360Settings, CSTSettings)
    """

    server = ServerSettings(
        name=os.getenv("MCP_SERVER_NAME", "Fusion360MCP"),
        transport=os.getenv("MCP_TRANSPORT", "http"),  # type: ignore[arg-type]
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8765")),
    )

    fusion360 = Fusion360Settings(
        server_url=os.getenv("FUSION360_SERVER_URL", "http://localhost:9000"),
        timeout_seconds=float(os.getenv("FUSION360_TIMEOUT", "30.0")),
    )

    cst = CSTSettings(
        server_url=os.getenv("CST_SERVER_URL", "http://localhost:9001"),
        timeout_seconds=float(os.getenv("CST_TIMEOUT", "60.0")),
        enabled=os.getenv("CST_ENABLED", "true").lower() in ("true", "1", "yes"),
    )

    return server, fusion360, cst

