"""
Export operations module.

Fusion 360 API for exporting design to STEP, IGES, STL formats.
Supports import into CST Studio Suite (STEP, IGES).
"""

import os
import traceback
from typing import Optional

from .logger import get_default_logger

logger = get_default_logger()

try:
    import adsk.core
    import adsk.fusion
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


def _get_design() -> "adsk.fusion.Design":
    if not FUSION_AVAILABLE:
        raise RuntimeError("Fusion 360 API not available")
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise Exception("没有活动的 Fusion 360 文档")
    return design


def _ensure_extension(file_path: str, expected_ext: str) -> str:
    """确保文件路径具有正确的扩展名。"""
    path_lower = file_path.lower()
    if not path_lower.endswith(expected_ext.lower()):
        if not file_path.endswith("."):
            file_path = file_path.rstrip(".")
        file_path = f"{file_path}.{expected_ext}"
    return file_path


def export_to_step(file_path: str, include_hidden: bool = False) -> dict:
    """
    将当前设计导出为 STEP 格式。
    STEP 格式兼容 CST Studio Suite 等电磁仿真软件。

    Args:
        file_path: 导出文件完整路径（如 C:\\Users\\xxx\\model.step）
        include_hidden: 是否包含隐藏的实体

    Returns:
        包含 success、message、path 的字典
    """
    try:
        design = _get_design()
        export_mgr = design.exportManager
        file_path = _ensure_extension(file_path, "step")
        file_path = os.path.abspath(os.path.normpath(file_path))

        dir_path = os.path.dirname(file_path)
        if not os.path.isdir(dir_path):
            raise Exception(f"目录不存在: {dir_path}")

        step_options = export_mgr.createSTEPExportOptions(file_path)
        if step_options is None:
            raise Exception("创建 STEP 导出选项失败")

        if hasattr(step_options, "includeHidden") and include_hidden:
            step_options.includeHidden = True

        result = export_mgr.execute(step_options)
        if result:
            logger.info(f"STEP 导出成功: {file_path}")
            return {
                "success": True,
                "message": f"已导出到 {file_path}",
                "path": file_path,
            }
        raise Exception("STEP 导出执行失败")
    except Exception as e:
        logger.error(f"STEP 导出失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def export_to_iges(file_path: str, include_hidden: bool = False) -> dict:
    """
    将当前设计导出为 IGES 格式。
    IGES 格式兼容 CST Studio Suite 等电磁仿真软件。

    Args:
        file_path: 导出文件完整路径（如 C:\\Users\\xxx\\model.iges）
        include_hidden: 是否包含隐藏的实体

    Returns:
        包含 success、message、path 的字典
    """
    try:
        design = _get_design()
        export_mgr = design.exportManager
        file_path = _ensure_extension(file_path, "iges")
        file_path = os.path.abspath(os.path.normpath(file_path))

        dir_path = os.path.dirname(file_path)
        if not os.path.isdir(dir_path):
            raise Exception(f"目录不存在: {dir_path}")

        iges_options = export_mgr.createIGESExportOptions(file_path)
        if iges_options is None:
            raise Exception("创建 IGES 导出选项失败")

        if hasattr(iges_options, "includeHidden") and include_hidden:
            iges_options.includeHidden = True

        result = export_mgr.execute(iges_options)
        if result:
            logger.info(f"IGES 导出成功: {file_path}")
            return {
                "success": True,
                "message": f"已导出到 {file_path}",
                "path": file_path,
            }
        raise Exception("IGES 导出执行失败")
    except Exception as e:
        logger.error(f"IGES 导出失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def export_to_stl(
    file_path: str,
    include_hidden: bool = False,
    mesh_refinement: Optional[str] = None,
) -> dict:
    """
    将当前设计导出为 STL 格式（三角网格）。

    Args:
        file_path: 导出文件完整路径
        include_hidden: 是否包含隐藏的实体
        mesh_refinement: 网格精度 "coarse"|"medium"|"fine"，默认 "medium"

    Returns:
        包含 success、message、path 的字典
    """
    try:
        design = _get_design()
        export_mgr = design.exportManager
        file_path = _ensure_extension(file_path, "stl")
        file_path = os.path.abspath(os.path.normpath(file_path))

        dir_path = os.path.dirname(file_path)
        if not os.path.isdir(dir_path):
            raise Exception(f"目录不存在: {dir_path}")

        stl_options = export_mgr.createSTLExportOptions(file_path)
        if stl_options is None:
            raise Exception("创建 STL 导出选项失败")

        if hasattr(stl_options, "includeHidden") and include_hidden:
            stl_options.includeHidden = True

        if mesh_refinement and hasattr(stl_options, "meshRefinement") and FUSION_AVAILABLE:
            refinement_map = {
                "coarse": adsk.fusion.MeshRefinement.MeshRefinementCoarse,
                "medium": adsk.fusion.MeshRefinement.MeshRefinementMedium,
                "fine": adsk.fusion.MeshRefinement.MeshRefinementFine,
            }
            ref = refinement_map.get((mesh_refinement or "").lower())
            if ref is not None:
                stl_options.meshRefinement = ref

        result = export_mgr.execute(stl_options)
        if result:
            logger.info(f"STL 导出成功: {file_path}")
            return {
                "success": True,
                "message": f"已导出到 {file_path}",
                "path": file_path,
            }
        raise Exception("STL 导出执行失败")
    except Exception as e:
        logger.error(f"STL 导出失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
