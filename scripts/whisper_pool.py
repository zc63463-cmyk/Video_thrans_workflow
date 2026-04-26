"""
Whisper 模型池化模块 - 避免重复加载模型
"""
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger

logger = get_logger(__name__)

# 全局模型池
_model_pool: Dict[str, Any] = {}


def get_model_key(model_name: str, device: str, model_type: str = "faster-whisper") -> str:
    """
    生成模型键
    
    Args:
        model_name: 模型名称（tiny/base/small/medium/large-v3）
        device: 设备（cpu/cuda）
        model_type: 模型类型（faster-whisper/openai-whisper）
        
    Returns:
        模型键字符串
    """
    return f"{model_type}_{model_name}_{device}"


def get_whisper_model(
    model_name: str = "small",
    device: str = "cpu",
    model_type: str = "faster-whisper",
    **kwargs
) -> Any:
    """
    获取 Whisper 模型（从池中获取或加载新模型）
    
    Args:
        model_name: 模型名称
        device: 设备
        model_type: 模型类型（faster-whisper/openai-whisper）
        **kwargs: 传递给模型构造函数的额外参数
        
    Returns:
        Whisper 模型实例
    """
    global _model_pool
    
    model_key = get_model_key(model_name, device, model_type)
    
    # 检查模型是否已在池中
    if model_key in _model_pool:
        logger.debug(f"从模型池获取模型: {model_key}")
        return _model_pool[model_key]
    
    # 加载新模型
    logger.info(f"加载 Whisper 模型: {model_name} on {device} (type: {model_type})")
    
    model = None
    
    if model_type == "faster-whisper":
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(model_name, device=device, **kwargs)
        except ImportError:
            logger.warning("faster-whisper 未安装，尝试使用 openai-whisper")
            model_type = "openai-whisper"
    
    if model_type == "openai-whisper":
        try:
            import whisper
            model = whisper.load_model(model_name, device=device, **kwargs)
        except ImportError:
            logger.error("openai-whisper 未安装")
            return None
    
    if model is not None:
        _model_pool[model_key] = model
        logger.debug(f"模型已添加到池: {model_key}")
    
    return model


def clear_model_pool():
    """清空模型池"""
    global _model_pool
    _model_pool.clear()
    logger.info("模型池已清空")


def remove_model_from_pool(
    model_name: str = "small",
    device: str = "cpu",
    model_type: str = "faster-whisper"
):
    """从池中移除指定模型"""
    global _model_pool
    
    model_key = get_model_key(model_name, device, model_type)
    
    if model_key in _model_pool:
        del _model_pool[model_key]
        logger.debug(f"模型已从池移除: {model_key}")


if __name__ == "__main__":
    # 测试代码
    print("测试 Whisper 模型池...")
    
    # 测试获取模型
    model1 = get_whisper_model(model_name="tiny", device="cpu", model_type="faster-whisper")
    print(f"第一次获取模型: {type(model1)}")
    
    # 再次获取相同模型（应该从池中返回）
    model2 = get_whisper_model(model_name="tiny", device="cpu", model_type="faster-whisper")
    print(f"第二次获取模型（应该从池中返回）: {type(model2)}")
    print(f"是否是同一个对象: {model1 is model2}")
    
    # 获取不同模型
    model3 = get_whisper_model(model_name="base", device="cpu", model_type="faster-whisper")
    print(f"获取不同模型: {type(model3)}")
    
    # 清空模型池
    clear_model_pool()
    print("模型池已清空")
    
    print("测试完成！")
