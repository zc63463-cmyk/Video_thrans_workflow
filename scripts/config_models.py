"""
配置验证模块 - 使用 Pydantic 验证配置文件
"""
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class WhisperConfig(BaseModel):
    """Whisper 配置"""
    provider: str = Field(default="auto", description="Whisper 实现: auto/faster-whisper/openai-whisper")
    model: str = Field(default="small", description="模型大小")
    language: Optional[str] = Field(default="zh", description="目标语言，None=自动检测")
    device: str = Field(default="cpu", description="运行设备: cpu/cuda")
    
    @field_validator('provider')
    def validate_provider(cls, v):
        valid = ['auto', 'faster-whisper', 'faster', 'openai-whisper', 'whisper', 'native']
        if v.lower() not in valid:
            raise ValueError(f"provider 必须是 {valid} 之一，当前: {v}")
        return v.lower()
    
    @field_validator('model')
    def validate_model(cls, v):
        valid = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3']
        if v.lower() not in valid:
            raise ValueError(f"model 必须是 {valid} 之一，当前: {v}")
        return v.lower()
    
    @field_validator('device')
    def validate_device(cls, v):
        valid = ['cpu', 'cuda']
        if v.lower() not in valid:
            raise ValueError(f"device 必须是 {valid} 之一，当前: {v}")
        return v.lower()


class PlatformConfig(BaseModel):
    """平台配置基类"""
    cookies_file: Optional[str] = Field(default=None, description="Cookies 文件路径")
    
    @field_validator('cookies_file')
    def validate_cookies_file(cls, v):
        if v is not None:
            path = Path(v)
            # 如果不是绝对路径，假设是相对于项目根目录
            if not path.is_absolute():
                # 这里不检查存在性，因为可能在其他环境不存在
                pass
        return v


class BilibiliConfig(PlatformConfig):
    """Bilibili 配置"""
    favorite_url: Optional[str] = Field(default=None, description="收藏夹 URL")


class YoutubeConfig(PlatformConfig):
    """YouTube 配置"""
    playlist_id: Optional[str] = Field(default=None, description="播放列表 ID")


class VideoCollectorConfig(BaseModel):
    """完整配置"""
    bilibili: Optional[BilibiliConfig] = Field(default=None)
    youtube: Optional[YoutubeConfig] = Field(default=None)
    whisper: Optional[WhisperConfig] = Field(default=None)
    
    @model_validator(mode='after')
    def validate_config(self) -> 'VideoCollectorConfig':
        """验证配置的一致性"""
        return self
    
    def get_whisper_config(self) -> dict:
        """获取 Whisper 配置字典"""
        if self.whisper:
            return self.whisper.model_dump(exclude_none=True)
        return {
            "provider": "auto",
            "model": "small",
            "language": "zh",
            "device": "cpu"
        }
    
    def get_platform_config(self, platform: str) -> dict:
        """获取平台配置字典"""
        platform_config = getattr(self, platform, None)
        if platform_config:
            return platform_config.model_dump(exclude_none=True)
        return {}


def load_and_validate_config(config_path: str) -> VideoCollectorConfig:
    """
    加载并验证配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        验证后的配置对象
        
    Raises:
        ConfigurationError: 配置无效
    """
    import sys
    from pathlib import Path as Path2
    
    # 确保 scripts 目录在 Python 路径中
    scripts_dir = Path2(__file__).parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    
    from logger_config import get_logger
    from exceptions import ConfigurationError
    
    logger = get_logger(__name__)
    
    path = Path2(config_path)
    if not path.exists():
        raise ConfigurationError(f"配置文件不存在: {config_path}", config_path=config_path)
    
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}
        
        # 尝试解析路径（将相对路径转为绝对路径）
        from main import resolve_config_paths
        raw_config = resolve_config_paths(raw_config)
        
        # 验证配置
        config = VideoCollectorConfig(**raw_config)
        logger.info(f"配置验证成功: {config_path}")
        return config
        
    except Exception as e:
        if isinstance(e, ConfigurationError):
            raise
        raise ConfigurationError(f"配置格式错误: {e}", config_path=config_path) from e


def validate_config_file(config_path: str) -> tuple[bool, str]:
    """
    验证配置文件，返回 (是否成功, 错误消息)
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        (success, message)
    """
    try:
        load_and_validate_config(config_path)
        return True, "配置验证成功"
    except Exception as e:
        return False, str(e)
