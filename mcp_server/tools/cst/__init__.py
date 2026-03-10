"""
CST Studio Suite 工具模块。

通过 CST Bridge 控制电磁仿真：导入 STEP、赋材料、运行仿真、获取结果。
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from mcp_server.clients import CSTClient

__all__ = ["register"]


def register(app: FastMCP, client: CSTClient) -> None:
    """注册 CST 相关工具。"""

    @app.tool()
    async def cst_import_step(
        file_path: str,
        component_name: str = "ImportedComponent",
    ) -> str:
        """
        将 STEP/STP 文件导入 CST Studio Suite 项目。
        通常配合 Fusion 360 的 export_to_step 使用，形成 CAD→仿真闭环。

        Args:
            file_path: STEP 文件完整路径（如 C:\\\\Users\\\\xxx\\\\antenna.step）
            component_name: 导入后的组件名称，默认 ImportedComponent

        Returns:
            成功时返回消息，失败时返回错误信息

        [注意]
        - 需先启动 CST Bridge: python -m cst_bridge.run
        - 需安装 CST Studio Suite 并将 python_cst_libraries 加入 PYTHONPATH
        """
        try:
            result = await client.request(
                "/api/import/step",
                method="POST",
                data={"file_path": file_path, "component_name": component_name},
            )
            if result.get("success"):
                return result.get("message", "导入成功")
            return result.get("error", "导入失败")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def cst_assign_material(
        component_name: str,
        material_name: str = "Copper",
        solid_name: Optional[str] = None,
    ) -> str:
        """
        为 CST 中的组件指定材料。

        Args:
            component_name: 组件名称
            material_name: 材料名称，如 Copper, FR4, Vacuum
            solid_name: 可选，特定实体名称

        Returns:
            成功或失败信息
        """
        try:
            data = {"component_name": component_name, "material_name": material_name}
            if solid_name:
                data["solid_name"] = solid_name
            result = await client.request("/api/material/assign", method="POST", data=data)
            if result.get("success"):
                return result.get("message", "赋材料成功")
            return result.get("error", "赋材料失败")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def cst_set_frequency_range(f_min_hz: float, f_max_hz: float) -> str:
        """
        设置 CST 仿真的频率范围。

        Args:
            f_min_hz: 最低频率 (Hz)，如 5.15e9 表示 5.15 GHz
            f_max_hz: 最高频率 (Hz)，如 5.895e9 表示 5.895 GHz

        Returns:
            成功或失败信息
        """
        try:
            result = await client.request(
                "/api/solver/frequency",
                method="POST",
                data={"f_min_hz": f_min_hz, "f_max_hz": f_max_hz},
            )
            if result.get("success"):
                return result.get("message", "频率范围已设置")
            return result.get("error", "设置失败")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def cst_run_simulation() -> str:
        """
        在 CST Studio Suite 中运行当前项目的电磁仿真。

        Returns:
            成功或失败信息。仿真耗时可能较长。
        """
        try:
            result = await client.request("/api/solver/run", method="POST", data={})
            if result.get("success"):
                return result.get("message", "仿真完成")
            return result.get("error", "仿真失败")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def cst_get_simulation_results() -> str:
        """
        获取最近一次 CST 仿真的结果（S11、增益等）。

        Returns:
            仿真结果摘要，或错误信息
        """
        try:
            result = await client.request("/api/results", method="POST", data={})
            if result.get("success"):
                results = result.get("results", {})
                if not results:
                    return "仿真结果为空或尚未实现结果读取接口。"
                lines = ["=== CST 仿真结果 ==="]
                for k, v in results.items():
                    lines.append(f"{k}: {v}")
                return "\n".join(lines)
            return result.get("error", "获取结果失败")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    @app.tool()
    async def cst_new_project() -> str:
        """
        在 CST Studio Suite 中创建新项目。

        Returns:
            成功或失败信息
        """
        try:
            result = await client.request("/api/project/new", method="POST", data={})
            if result.get("success"):
                return result.get("message", "已创建新项目")
            return result.get("error", "创建失败")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
