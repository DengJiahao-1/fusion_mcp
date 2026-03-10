"""
Fusion 360 插件入口点

这是 Fusion 360 插件的启动脚本，用于启动 HTTP 服务器。
"""

import sys
import os

# 添加插件路径到 Python 路径
addin_path = os.path.dirname(os.path.abspath(__file__))
if addin_path not in sys.path:
    sys.path.insert(0, addin_path)

from .server import start_server, stop_server
from .logger import get_default_logger

logger = get_default_logger()


# 全局变量
_server_thread = None


def run(context):
    """
    Fusion 360 插件启动函数
    
    Args:
        context: Fusion 360 插件上下文
    """
    global _server_thread
    
    try:
        # 入口提示（便于确认 run() 已被调用）
        logger.info("正在启动 Fusion 360 MCP 插件…")

        # 启动 HTTP 服务器
        _server_thread = start_server(port=9000)

        # 显示启动消息
        logger.info("Fusion 360 MCP 插件已启动，HTTP 服务器运行在 localhost:9000")

    except Exception as e:
        logger.error(f"启动插件失败: {str(e)}", exc_info=True)


def stop(context):
    """
    Fusion 360 插件停止函数
    
    Args:
        context: Fusion 360 插件上下文
    """
    global _server_thread
    
    try:
        # 停止 HTTP 服务器
        stop_server()
        
        # 显示停止消息
        logger.info("Fusion 360 MCP 插件已停止")
        
    except Exception as e:
        logger.error(f"停止插件失败: {str(e)}", exc_info=True)

