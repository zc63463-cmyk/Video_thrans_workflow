"""
自定义异常类 - 统一的错误处理
"""
from typing import Optional


class VideoCollectorError(Exception):
    """基础异常类 - 所有自定义异常的父类"""
    pass


class ConfigurationError(VideoCollectorError):
    """配置错误 - 配置文件缺失或格式错误"""
    def __init__(self, message: str, config_path: Optional[str] = None):
        self.config_path = config_path
        super().__init__(f"配置错误: {message}")


class PlatformNotSupportedError(VideoCollectorError):
    """平台不支持 - 尝试处理不支持的平台"""
    def __init__(self, platform: str):
        self.platform = platform
        super().__init__(f"不支持的平台: {platform}")


class TranscriptionError(VideoCollectorError):
    """转录失败 - Whisper 转录过程出错"""
    def __init__(self, message: str, url: Optional[str] = None):
        self.url = url
        super().__init__(f"转录失败: {message}")


class FetchError(VideoCollectorError):
    """抓取失败 - 无法获取视频信息"""
    def __init__(self, message: str, url: Optional[str] = None, platform: Optional[str] = None):
        self.url = url
        self.platform = platform
        super().__init__(f"抓取失败: {message}")


class CookieError(VideoCollectorError):
    """Cookie 错误 - Cookie 文件缺失或无效"""
    def __init__(self, message: str, cookie_path: Optional[str] = None):
        self.cookie_path = cookie_path
        super().__init__(f"Cookie 错误: {message}")


class BundleExportError(VideoCollectorError):
    """Bundle 导出失败 - 无法导出 AI 输入包"""
    def __init__(self, message: str, output_dir: Optional[str] = None):
        self.output_dir = output_dir
        super().__init__(f"Bundle 导出失败: {message}")


class DatabaseError(VideoCollectorError):
    """数据库错误 - SQLite 操作失败"""
    def __init__(self, message: str, db_path: Optional[str] = None):
        self.db_path = db_path
        super().__init__(f"数据库错误: {message}")


def handle_exception(func):
    """
    装饰器：统一异常处理
    在关键函数上使用，自动捕获并记录异常
    """
    import functools
    from logger_config import get_logger
    
    logger = get_logger(func.__module__)
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except VideoCollectorError as e:
            logger.error(f"{func.__name__} 失败: {e}")
            raise
        except Exception as e:
            logger.error(f"{func.__name__} 未知错误: {e}")
            raise VideoCollectorError(f"未知错误: {e}") from e
    
    return wrapper
