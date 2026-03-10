"""
CST Studio Suite Bridge HTTP 客户端封装。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from mcp_server.config import CSTSettings


class CSTClientError(RuntimeError):
    """CST Bridge 客户端请求异常。"""


class CSTClient:
    """
    负责与 CST Bridge HTTP 服务通信。
    """

    def __init__(self, settings: CSTSettings) -> None:
        self._settings = settings

    async def request(
        self,
        endpoint: str,
        *,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发起 HTTP 请求并返回 JSON 结果。"""
        url = f"{self._settings.server_url.rstrip('/')}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
                if method.upper() == "POST":
                    response = await client.post(url, json=data or {})
                elif method.upper() == "GET":
                    response = await client.get(url, params=data or {})
                else:
                    raise CSTClientError(f"不支持的请求方法: {method}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as exc:
            raise CSTClientError(f"无法连接到 CST Bridge: {str(exc)}") from exc
        except Exception as exc:
            raise CSTClientError(f"CST Bridge 调用失败: {str(exc)}") from exc
