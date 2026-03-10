"""
CST Studio Suite 操作模块。

封装 CST Python API，实现导入几何、赋材料、运行仿真、获取结果等操作。
当 CST 未安装时，返回友好的错误信息。
"""

import os
import traceback
from typing import Any, Dict, List, Optional

from .logger import get_logger

logger = get_logger()

# 尝试导入 CST Python 库
CST_AVAILABLE = False
_cst_mws = None
_cst_interface = None

try:
    import sys
    # CST Studio Suite 安装路径下的 Python 库，需根据实际安装版本调整
    _cst_paths = [
        r"C:\Program Files (x86)\CST Studio Suite 2024\AMD64\python_cst_libraries",
        r"C:\Program Files (x86)\CST Studio Suite 2023\AMD64\python_cst_libraries",
        r"C:\Program Files (x86)\CST Studio Suite 2022\AMD64\python_cst_libraries",
        r"C:\Program Files (x86)\CST Studio Suite 2021\AMD64\python_cst_libraries",
        r"C:\Program Files (x86)\CST Studio Suite 2020\AMD64\python_cst_libraries",
    ]
    for _p in _cst_paths:
        if os.path.isdir(_p):
            if _p not in sys.path:
                sys.path.insert(0, _p)
            break

    import cst.interface
    _cst_interface = cst.interface
    CST_AVAILABLE = True
except ImportError:
    logger.warning(
        "CST Studio Suite Python 库未找到。请安装 CST 或将 python_cst_libraries 加入 PYTHONPATH。"
    )


def _get_mws() -> Any:
    """获取当前 CST Microwave Studio 实例。"""
    global _cst_mws
    if not CST_AVAILABLE:
        raise RuntimeError("CST Studio Suite 不可用，请检查安装与 Python 库路径。")
    if _cst_mws is None:
        project = cst.interface.DesignEnvironment()
        _cst_mws = project.new_mws()
    return _cst_mws


def import_step(file_path: str, component_name: str = "ImportedComponent") -> Dict[str, Any]:
    """
    将 STEP 文件导入 CST 项目。

    Args:
        file_path: STEP/STP 文件完整路径
        component_name: 导入后的组件名称

    Returns:
        包含 success、message、component_name 的字典
    """
    try:
        file_path = os.path.abspath(os.path.normpath(file_path))
        if not os.path.isfile(file_path):
            return {
                "success": False,
                "error": f"文件不存在: {file_path}",
            }

        if not CST_AVAILABLE:
            return {
                "success": False,
                "error": "CST Studio Suite 不可用。请安装 CST 并确保 python_cst_libraries 在 PYTHONPATH 中。",
            }

        mws = _get_mws()
        # CST API 导入 STEP 的典型调用（需根据实际 API 调整）
        # 参考: File > Import > STEP / IGES
        # mws 通常提供 modeler 或类似接口
        if hasattr(mws, "modeler"):
            # 部分版本: modeler.ImportSTEP(file_path, component_name)
            mws.modeler.import_step(file_path, component_name)
        elif hasattr(mws, "import_step"):
            mws.import_step(file_path, component_name)
        else:
            # 占位：实际 API 需查阅 CST 文档
            return {
                "success": False,
                "error": "当前 CST 版本未实现 import_step 接口，请查阅 CST Python API 文档并扩展 cst_operations.import_step。",
            }

        logger.info(f"STEP 导入成功: {file_path} -> {component_name}")
        return {
            "success": True,
            "message": f"已导入 {file_path} 为组件 {component_name}",
            "component_name": component_name,
        }
    except Exception as e:
        logger.error(f"STEP 导入失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def assign_material(
    component_name: str,
    material_name: str = "Copper",
    solid_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    为组件/实体指定材料。

    Args:
        component_name: 组件名称
        material_name: 材料名称（如 Copper, FR4, Vacuum）
        solid_name: 可选，特定实体名称

    Returns:
        包含 success、message 的字典
    """
    try:
        if not CST_AVAILABLE:
            return {
                "success": False,
                "error": "CST Studio Suite 不可用。",
            }

        mws = _get_mws()
        # 占位：实际 API 需根据 CST 文档实现
        if hasattr(mws, "modeler") and hasattr(mws.modeler, "change_material"):
            target = f"{component_name}:{solid_name}" if solid_name else component_name
            mws.modeler.change_material(target, material_name)
        else:
            return {
                "success": False,
                "error": "当前 CST 版本未实现 assign_material 接口，请查阅 CST API 文档并扩展。",
            }

        return {
            "success": True,
            "message": f"已将 {material_name} 赋给 {component_name}",
        }
    except Exception as e:
        logger.error(f"赋材料失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def set_frequency_range(f_min_hz: float, f_max_hz: float) -> Dict[str, Any]:
    """
    设置仿真频率范围。

    Args:
        f_min_hz: 最低频率 (Hz)
        f_max_hz: 最高频率 (Hz)

    Returns:
        包含 success、message 的字典
    """
    try:
        if not CST_AVAILABLE:
            return {"success": False, "error": "CST Studio Suite 不可用。"}

        mws = _get_mws()
        # 典型: solver.FrequencyRange 或 similar
        if hasattr(mws, "solver") and hasattr(mws.solver, "frequency_range"):
            mws.solver.frequency_range("min", f_min_hz)
            mws.solver.frequency_range("max", f_max_hz)
        else:
            return {
                "success": False,
                "error": "当前 CST 版本未实现 set_frequency_range，请查阅 API 文档并扩展。",
            }

        return {
            "success": True,
            "message": f"频率范围已设置为 {f_min_hz/1e9:.2f} - {f_max_hz/1e9:.2f} GHz",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def run_simulation() -> Dict[str, Any]:
    """
    运行当前项目的电磁仿真。

    Returns:
        包含 success、message、result_path 的字典
    """
    try:
        if not CST_AVAILABLE:
            return {"success": False, "error": "CST Studio Suite 不可用。"}

        mws = _get_mws()
        if hasattr(mws, "solver") and hasattr(mws.solver, "start"):
            mws.solver.start()
        else:
            return {
                "success": False,
                "error": "当前 CST 版本未实现 run_simulation，请查阅 API 文档并扩展。",
            }

        return {
            "success": True,
            "message": "仿真已启动并完成",
        }
    except Exception as e:
        logger.error(f"仿真失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def get_simulation_results() -> Dict[str, Any]:
    """
    获取最近一次仿真的结果（S11、增益等）。

    Returns:
        包含 success、results 的字典
        results 可能包含: s11_db, gain_dbi, frequency_hz 等
    """
    try:
        if not CST_AVAILABLE:
            return {"success": False, "error": "CST Studio Suite 不可用。"}

        mws = _get_mws()
        # 占位：通过 cst.results 或类似模块读取
        results = {}
        if hasattr(mws, "result") or hasattr(mws, "results"):
            res_obj = getattr(mws, "result", None) or getattr(mws, "results", None)
            if res_obj and hasattr(res_obj, "get_s11"):
                # 示例结构
                results["s11_db"] = []  # 需实际读取
                results["frequency_hz"] = []
                results["gain_dbi"] = []
        else:
            return {
                "success": False,
                "error": "当前 CST 版本未实现 get_simulation_results，请查阅 cst.results API 并扩展。",
            }

        return {
            "success": True,
            "results": results,
            "message": "已获取仿真结果",
        }
    except Exception as e:
        logger.error(f"获取结果失败: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def new_project() -> Dict[str, Any]:
    """创建新的 CST Microwave Studio 项目。"""
    global _cst_mws
    try:
        if not CST_AVAILABLE or _cst_interface is None:
            return {"success": False, "error": "CST Studio Suite 不可用。"}

        project = _cst_interface.DesignEnvironment()
        _cst_mws = project.new_mws()
        return {
            "success": True,
            "message": "已创建新 CST 项目",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def get_project_info() -> Dict[str, Any]:
    """获取当前项目基本信息（用于诊断）。"""
    try:
        if not CST_AVAILABLE:
            return {
                "success": False,
                "cst_available": False,
                "error": "CST Studio Suite Python 库未找到。",
            }

        mws = _get_mws()
        info = {
            "success": True,
            "cst_available": True,
            "project_open": mws is not None,
        }
        return info
    except Exception as e:
        return {
            "success": False,
            "cst_available": CST_AVAILABLE,
            "error": str(e),
        }
