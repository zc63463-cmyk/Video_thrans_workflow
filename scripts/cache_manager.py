"""
缓存管理模块 - 使用文件系统缓存 API 响应和转录结果
"""
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Optional

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger

logger = get_logger(__name__)

# 缓存根目录
CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"

# 默认缓存过期时间（秒）
DEFAULT_TTL = 7 * 24 * 3600  # 7 天


class CacheManager:
    """缓存管理器 - 使用文件系统存储缓存"""
    
    def __init__(self, cache_dir: str = None, ttl: int = DEFAULT_TTL):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录（默认: project_root/cache）
            ttl: 缓存过期时间（秒，默认: 7天）
        """
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_ROOT
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        logger.debug(f"缓存目录: {self.cache_dir}")
    
    def _get_cache_key(self, key: str) -> str:
        """
        生成缓存键（使用 MD5 哈希）
        
        Args:
            key: 原始键（如 URL）
            
        Returns:
            哈希后的键
        """
        return hashlib.md5(key.encode("utf-8")).hexdigest()
    
    def _get_cache_path(self, key: str, suffix: str = ".pkl") -> Path:
        """
        获取缓存文件路径
        
        Args:
            key: 缓存键
            suffix: 文件后缀
            
        Returns:
            缓存文件路径
        """
        hashed_key = self._get_cache_key(key)
        return self.cache_dir / f"{hashed_key}{suffix}"
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存
        
        Args:
            key: 缓存键
            default: 默认值（如果缓存不存在或已过期）
            
        Returns:
            缓存的值，或默认值
        """
        cache_path = self._get_cache_path(key)
        
        if not cache_path.exists():
            logger.debug(f"缓存未命中: {key[:50]}...")
            return default
        
        # 检查是否过期
        if self.ttl > 0:
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime > self.ttl:
                logger.debug(f"缓存已过期: {key[:50]}...")
                return default
        
        # 读取缓存
        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)
            logger.debug(f"缓存命中: {key[:50]}...")
            return data
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
            return default
    
    def set(self, key: str, value: Any) -> bool:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            
        Returns:
            是否成功
        """
        cache_path = self._get_cache_path(key)
        
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(value, f)
            logger.debug(f"缓存已保存: {key[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功
        """
        cache_path = self._get_cache_path(key)
        
        if not cache_path.exists():
            return True
        
        try:
            cache_path.unlink()
            logger.debug(f"缓存已删除: {key[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"删除缓存失败: {e}")
            return False
    
    def clear(self) -> int:
        """
        清空所有缓存
        
        Returns:
            删除的文件数
        """
        count = 0
        for cache_file in self.cache_dir.glob("*"):
            try:
                cache_file.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"删除缓存文件失败 {cache_file}: {e}")
        
        logger.info(f"已清空缓存，删除 {count} 个文件")
        return count
    
    def clear_expired(self) -> int:
        """
        清空过期缓存
        
        Returns:
            删除的文件数
        """
        if self.ttl <= 0:
            return 0
        
        count = 0
        current_time = time.time()
        
        for cache_file in self.cache_dir.glob("*"):
            try:
                mtime = cache_file.stat().st_mtime
                if current_time - mtime > self.ttl:
                    cache_file.unlink()
                    count += 1
            except Exception as e:
                logger.warning(f"删除过期缓存文件失败 {cache_file}: {e}")
        
        if count > 0:
            logger.info(f"已清空过期缓存，删除 {count} 个文件")
        
        return count


# 全局缓存管理器实例（默认）
_default_cache = None

def get_default_cache() -> CacheManager:
    """获取默认缓存管理器实例"""
    global _default_cache
    if _default_cache is None:
        _default_cache = CacheManager()
    return _default_cache


def cached(
    key_func: callable = None,
    ttl: int = DEFAULT_TTL,
    cache: CacheManager = None
):
    """
    缓存装饰器
    
    Args:
        key_func: 生成缓存键的函数（接受原函数参数，返回字符串）
        ttl: 缓存过期时间（秒）
        cache: 缓存管理器实例（默认使用全局实例）
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 获取缓存管理器
            _cache = cache or get_default_cache()
            
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认键：函数名 + 参数哈希
                key_parts = [func.__name__]
                key_parts.extend([str(arg) for arg in args])
                key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                cache_key = "|".join(key_parts)
            
            # 尝试从缓存获取
            cached_result = _cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 缓存未命中，调用原函数
            result = func(*args, **kwargs)
            
            # 保存结果到缓存
            _cache.set(cache_key, result)
            
            return result
        return wrapper
    return decorator


if __name__ == "__main__":
    # 测试代码
    import time
    
    # 测试基本功能
    cache = CacheManager()
    
    # 测试 set/get
    print("测试 set/get...")
    cache.set("test_key", {"data": "test_value"})
    result = cache.get("test_key")
    print(f"  结果: {result}")
    
    # 测试缓存未命中
    print("测试缓存未命中...")
    result = cache.get("non_existent_key", default="default_value")
    print(f"  结果: {result}")
    
    # 测试装饰器
    print("测试装饰器...")
    call_count = 0
    
    @cached()
    def expensive_function(x: int) -> int:
        global call_count
        call_count += 1
        time.sleep(0.1)  # 模拟耗时操作
        return x * 2
    
    # 第一次调用
    result1 = expensive_function(5)
    print(f"  第一次调用: result={result1}, call_count={call_count}")
    
    # 第二次调用（应该使用缓存）
    result2 = expensive_function(5)
    print(f"  第二次调用: result={result2}, call_count={call_count}")
    
    # 不同的参数（应该重新计算）
    result3 = expensive_function(10)
    print(f"  不同参数: result={result3}, call_count={call_count}")
    
    # 测试清空缓存
    print("测试清空缓存...")
    count = cache.clear()
    print(f"  删除了 {count} 个缓存文件")
    
    print("测试完成！")
