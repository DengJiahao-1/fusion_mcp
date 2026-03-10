"""
统一的日志系统模块。

支持多种日志输出方式：
- 文件日志（持久化）
- Fusion 360 UI 消息框（仅重要消息）
- 控制台输出（开发环境）
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# 尝试导入 Fusion 360 API
try:
    import adsk.core
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False


class Fusion360LogHandler(logging.Handler):
    """Fusion 360 UI 日志处理器，将重要消息显示在消息框中。"""
    
    def emit(self, record: logging.LogRecord) -> None:
        """发送日志记录到 Fusion 360 UI。"""
        # 只显示 WARNING 及以上级别的消息
        if record.levelno >= logging.WARNING:
            try:
                if FUSION_AVAILABLE:
                    app = adsk.core.Application.get()
                    ui = app.userInterface
                    if ui:
                        message = self.format(record)
                        ui.messageBox(message)
            except Exception:
                # 如果 Fusion 360 UI 不可用，忽略错误
                pass


def setup_logger(
    name: str = "Fusion360MCP",
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
    enable_ui_logging: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    设置并返回配置好的日志记录器。
    
    Args:
        name: 日志记录器名称
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志文件目录，如果为 None 则使用默认目录
        enable_file_logging: 是否启用文件日志
        enable_console_logging: 是否启用控制台日志
        enable_ui_logging: 是否启用 Fusion 360 UI 日志（仅 WARNING 及以上）
        max_bytes: 单个日志文件最大大小（字节）
        backup_count: 保留的备份文件数量
    
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    # 设置日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 创建格式化器
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    ui_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # 文件日志处理器
    if enable_file_logging:
        if log_dir is None:
            # 默认日志目录：用户目录下的 .fusion360_mcp_logs
            home_dir = Path.home()
            log_dir = home_dir / ".fusion360_mcp_logs"
        else:
            log_dir = Path(log_dir)
        
        # 确保日志目录存在
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # 控制台日志处理器
    if enable_console_logging:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # Fusion 360 UI 日志处理器（仅 WARNING 及以上）
    if enable_ui_logging and FUSION_AVAILABLE:
        ui_handler = Fusion360LogHandler()
        ui_handler.setLevel(logging.WARNING)  # 只显示警告和错误
        ui_handler.setFormatter(ui_formatter)
        logger.addHandler(ui_handler)
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志记录器实例。
    
    Args:
        name: 日志记录器名称，如果为 None 则使用默认名称
    
    Returns:
        日志记录器实例
    """
    if name is None:
        name = "Fusion360MCP"
    return logging.getLogger(name)


# 默认日志记录器
_default_logger: Optional[logging.Logger] = None


def get_default_logger() -> logging.Logger:
    """获取默认日志记录器，如果未初始化则自动初始化。"""
    global _default_logger
    if _default_logger is None:
        # 从环境变量读取配置
        log_level = os.getenv("FUSION360_LOG_LEVEL", "INFO")
        enable_file = os.getenv("FUSION360_ENABLE_FILE_LOG", "true").lower() == "true"
        enable_console = os.getenv("FUSION360_ENABLE_CONSOLE_LOG", "true").lower() == "true"
        enable_ui = os.getenv("FUSION360_ENABLE_UI_LOG", "true").lower() == "true"
        log_dir = os.getenv("FUSION360_LOG_DIR")
        
        _default_logger = setup_logger(
            name="Fusion360MCP",
            log_level=log_level,
            log_dir=log_dir,
            enable_file_logging=enable_file,
            enable_console_logging=enable_console,
            enable_ui_logging=enable_ui,
        )
    return _default_logger

