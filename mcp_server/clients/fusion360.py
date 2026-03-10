"""
Fusion 360 HTTP 客户端封装。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from mcp_server.config import Fusion360Settings


class Fusion360ClientError(RuntimeError):
    """Fusion 360 客户端请求异常。"""


class Fusion360Client:
    """
    负责与 Fusion 360 插件 HTTP 服务进行通信。
    """

    def __init__(self, settings: Fusion360Settings) -> None:
        self._settings = settings

    async def request(
        self,
        endpoint: str,
        *,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发起 HTTP 请求并返回 JSON 结果。
        """
        url = f"{self._settings.server_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
                if method.upper() == "POST":
                    response = await client.post(url, json=data or {})
                elif method.upper() == "GET":
                    response = await client.get(url, params=data or {})
                else:
                    raise Fusion360ClientError(f"不支持的请求方法: {method}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as exc:
            raise Fusion360ClientError(f"无法连接到 Fusion 360 插件: {str(exc)}") from exc
        except Exception as exc:  # pragma: no cover - 容错兜底
            raise Fusion360ClientError(f"Fusion 360 API 调用失败: {str(exc)}") from exc

