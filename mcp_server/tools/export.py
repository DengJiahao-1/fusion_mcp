"""
导出工具模块。

支持将 Fusion 360 设计导出为 STEP、IGES、STL 格式。
STEP/IGES 可导入 CST Studio Suite 进行电磁仿真。
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client, Fusion360ClientError

__all__ = ["register"]


def register(app: FastMCP, client: Fusion360Client) -> None:
    """注册导出相关工具。"""

    @app.tool()
    async def export_to_step(file_path: str, include_hidden: bool = False) -> str:
        """
        将当前 Fusion 360 设计导出为 STEP 格式。
        STEP 格式可导入 CST Studio Suite、ANSYS 等电磁仿真软件。

        Args:
            file_path: 导出文件完整路径，如 C:\\Users\\xxx\\antenna.step 或 /home/user/model.step
            include_hidden: 是否包含隐藏的实体，默认 False

        Returns:
            成功时返回导出路径，失败时返回错误信息

        [注意]
        - 需先在 Fusion 360 中打开设计文档
        - 目录必须已存在
        - 无扩展名时自动添加 .step
        """
        try:
            result = await client.request(
                "/api/export/step",
                method="POST",
                data={"file_path": file_path, "include_hidden": include_hidden},
            )
            if result.get("success"):
                return result.get("message", result.get("path", "导出成功"))
            return result.get("error", "导出失败")
        except Fusion360ClientError as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def export_to_iges(file_path: str, include_hidden: bool = False) -> str:
        """
        将当前 Fusion 360 设计导出为 IGES 格式。
        IGES 格式可导入 CST Studio Suite 等电磁仿真软件。

        Args:
            file_path: 导出文件完整路径
            include_hidden: 是否包含隐藏的实体，默认 False

        Returns:
            成功时返回导出路径，失败时返回错误信息
        """
        try:
            result = await client.request(
                "/api/export/iges",
                method="POST",
                data={"file_path": file_path, "include_hidden": include_hidden},
            )
            if result.get("success"):
                return result.get("message", result.get("path", "导出成功"))
            return result.get("error", "导出失败")
        except Fusion360ClientError as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def export_to_stl(
        file_path: str,
        include_hidden: bool = False,
        mesh_refinement: str = "medium",
    ) -> str:
        """
        将当前 Fusion 360 设计导出为 STL 格式（三角网格）。

        Args:
            file_path: 导出文件完整路径
            include_hidden: 是否包含隐藏的实体，默认 False
            mesh_refinement: 网格精度 "coarse"|"medium"|"fine"，默认 "medium"

        Returns:
            成功时返回导出路径，失败时返回错误信息
        """
        try:
            result = await client.request(
                "/api/export/stl",
                method="POST",
                data={
                    "file_path": file_path,
                    "include_hidden": include_hidden,
                    "mesh_refinement": mesh_refinement,
                },
            )
            if result.get("success"):
                return result.get("message", result.get("path", "导出成功"))
            return result.get("error", "导出失败")
        except Fusion360ClientError as exc:
            raise RuntimeError(str(exc)) from exc
