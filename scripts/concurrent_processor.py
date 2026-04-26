"""
并发处理模块 - 支持多视频并发处理（使用 rich 美化进度条）
"""
import concurrent.futures
import sys
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any

# 确保 scripts 目录在 Python 路径中
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from logger_config import get_logger, RICH_AVAILABLE

logger = get_logger(__name__)

# 如果 rich 可用，导入 progress
if RICH_AVAILABLE:
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
    RICH_PROGRESS_AVAILABLE = True
else:
    RICH_PROGRESS_AVAILABLE = False

class ConcurrentProcessor:
    """并发处理器 - 使用 ThreadPoolExecutor 实现并发"""
    
    def __init__(self, max_workers: int = 3, show_progress: bool = True):
        """
        初始化并发处理器
        
        Args:
            max_workers: 最大并发线程数（默认3，避免过多请求被封）
            show_progress: 是否显示进度条
        """
        self.max_workers = max_workers
        self.show_progress = show_progress
        
    def process_urls(
        self, 
        urls: List[str], 
        processor_func: Callable[[str, Optional[Dict[str, Any]]], Any],
        func_kwargs: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        并发处理多个 URL
        
        Args:
            urls: URL 列表
            processor_func: 处理函数（接受 url 和 **kwargs）
            func_kwargs: 传递给处理函数的额外参数
            
        Returns:
            处理结果列表
        """
        if not urls:
            logger.warning("URL 列表为空，无需处理")
            return []
            
        func_kwargs = func_kwargs or {}
        results = []
        
        logger.info(f"开始并发处理 {len(urls)} 个 URL，最大并发数: {self.max_workers}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_url = {
                executor.submit(processor_func, url, **func_kwargs): url 
                for url in urls
            }
            
            # 使用 rich.Progress 或 tqdm 显示进度
            if self.show_progress and RICH_PROGRESS_AVAILABLE:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    task = progress.add_task("并发处理...", total=len(urls))
                    for future in concurrent.futures.as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            result = future.result()
                            results.append(result)
                            logger.debug(f"处理成功: {url}")
                        except Exception as e:
                            logger.error(f"处理失败 {url}: {e}")
                            results.append(None)
                        progress.update(task, advance=1)
            elif self.show_progress:
                # 降级到 tqdm
                from tqdm import tqdm
                with tqdm(total=len(urls), desc="并发处理", unit="个") as pbar:
                    for future in concurrent.futures.as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            result = future.result()
                            results.append(result)
                            logger.debug(f"处理成功: {url}")
                        except Exception as e:
                            logger.error(f"处理失败 {url}: {e}")
                            results.append(None)
                        pbar.update(1)
            else:
                # 不显示进度条
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.debug(f"处理成功: {url}")
                    except Exception as e:
                        logger.error(f"处理失败 {url}: {e}")
                        results.append(None)
        
        success_count = sum(1 for r in results if r is not None)
        logger.info(f"并发处理完成！成功: {success_count}/{len(urls)}")
        
        return results
    
    def process_entries(
        self,
        entries: List[Any],
        processor_func: Callable[[Any, Optional[Dict[str, Any]]], Any],
        func_kwargs: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        并发处理多个 VideoEntry 对象
        
        Args:
            entries: VideoEntry 对象列表
            processor_func: 处理函数
            func_kwargs: 传递给处理函数的额外参数
            
        Returns:
            处理结果列表
        """
        if not entries:
            logger.warning("Entry 列表为空，无需处理")
            return []
            
        func_kwargs = func_kwargs or {}
        results = []
        
        logger.info(f"开始并发处理 {len(entries)} 个视频，最大并发数: {self.max_workers}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_entry = {
                executor.submit(processor_func, entry, **func_kwargs): entry 
                for entry in entries
            }
            
            # 使用 rich.Progress 或 tqdm 显示进度
            if self.show_progress and RICH_PROGRESS_AVAILABLE:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    task = progress.add_task("并发处理...", total=len(entries))
                    for future in concurrent.futures.as_completed(future_to_entry):
                        entry = future_to_entry[future]
                        try:
                            result = future.result()
                            results.append(result)
                            logger.debug(f"处理成功: {entry.title if hasattr(entry, 'title') else entry}")
                        except Exception as e:
                            logger.error(f"处理失败 {entry.title if hasattr(entry, 'title') else entry}: {e}")
                            results.append(None)
                        progress.update(task, advance=1)
            elif self.show_progress:
                # 降级到 tqdm
                from tqdm import tqdm
                with tqdm(total=len(entries), desc="并发处理", unit="个") as pbar:
                    for future in concurrent.futures.as_completed(future_to_entry):
                        entry = future_to_entry[future]
                        try:
                            result = future.result()
                            results.append(result)
                            logger.debug(f"处理成功: {entry.title if hasattr(entry, 'title') else entry}")
                        except Exception as e:
                            logger.error(f"处理失败 {entry.title if hasattr(entry, 'title') else entry}: {e}")
                            results.append(None)
                        pbar.update(1)
            else:
                # 不显示进度条
                for future in concurrent.futures.as_completed(future_to_entry):
                    entry = future_to_entry[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.debug(f"处理成功: {entry.title if hasattr(entry, 'title') else entry}")
                    except Exception as e:
                        logger.error(f"处理失败 {entry.title if hasattr(entry, 'title') else entry}: {e}")
                        results.append(None)
        
        success_count = sum(1 for r in results if r is not None)
        logger.info(f"并发处理完成！成功: {success_count}/{len(entries)}")
        
        return results


def process_urls_concurrently(
    urls: List[str],
    processor_func: Callable[[str, Optional[Dict[str, Any]]], Any],
    max_workers: int = 3,
    show_progress: bool = True,
    func_kwargs: Optional[Dict[str, Any]] = None
) -> List[Any]:
    """
    便捷函数：并发处理多个 URL
    
    Args:
        urls: URL 列表
        processor_func: 处理函数
        max_workers: 最大并发线程数
        show_progress: 是否显示进度条
        func_kwargs: 传递给处理函数的额外参数
        
    Returns:
        处理结果列表
    """
    processor = ConcurrentProcessor(max_workers=max_workers, show_progress=show_progress)
    return processor.process_urls(urls, processor_func, func_kwargs)


def process_entries_concurrently(
    entries: List[Any],
    processor_func: Callable[[Any, Optional[Dict[str, Any]]], Any],
    max_workers: int = 3,
    show_progress: bool = True,
    func_kwargs: Optional[Dict[str, Any]] = None
) -> List[Any]:
    """
    便捷函数：并发处理多个 VideoEntry 对象
    
    Args:
        entries: VideoEntry 对象列表
        processor_func: 处理函数
        max_workers: 最大并发线程数
        show_progress: 是否显示进度条
        func_kwargs: 传递给处理函数的额外参数
        
    Returns:
        处理结果列表
    """
    processor = ConcurrentProcessor(max_workers=max_workers, show_progress=show_progress)
    return processor.process_entries(entries, processor_func, func_kwargs)


if __name__ == "__main__":
    # 测试代码
    import time
    
    def dummy_processor(url: str, delay: float = 1.0) -> str:
        """模拟处理函数"""
        time.sleep(delay)
        return f"Processed: {url}"
    
    # 测试并发处理
    test_urls = [f"http://example.com/{i}" for i in range(5)]
    
    print("测试并发处理 URL...")
    results = process_urls_concurrently(
        test_urls, 
        dummy_processor, 
        max_workers=3,
        func_kwargs={"delay": 0.5}
    )
    print(f"结果: {results}")
