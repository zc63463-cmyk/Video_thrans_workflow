"""
日志配置模块 - 统一的日志记录（使用 rich 美化输出）
"""
import logging
import sys
from pathlib import Path

try:
    from rich.logging import RichHandler
    from rich.traceback import install as install_rich_traceback
    
    # 安装 rich 的 traceback 美化
    install_rich_traceback(show_locals=True)
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def setup_logger(
    name: str = "video_collector",
    log_file: str = "video_collector.log",
    level: int = logging.INFO,
    console: bool = True
) -> logging.Logger:
    """
    配置并返回 logger 实例（使用 rich 美化控制台输出）。
    
    Args:
        name: logger 名称
        log_file: 日志文件路径（相对于项目根目录）
        level: 日志级别
        console: 是否输出到控制台
    
    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件 handler
    project_root = Path(__file__).resolve().parent.parent
    log_path = project_root / log_file
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 控制台 handler（使用 rich 美化）
    if console:
        if RICH_AVAILABLE:
            # 使用 RichHandler 美化输出
            console_handler = RichHandler(
                level=level,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                markup=True,  # 支持 rich 标记语法
            )
            console_handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            # 降级到标准 StreamHandler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

# 创建默认 logger
default_logger = setup_logger()

def get_logger(name: str = None) -> logging.Logger:
    """
    获取 logger 实例。
    
    Args:
        name: logger 名称，如果为 None 则返回默认 logger
    
    Returns:
        Logger 实例
    """
    if name is None:
        return default_logger
    return setup_logger(name)
