"""
迁移脚本：将 print 语句替换为 logger 调用
"""
import re
from pathlib import Path

def migrate_file(file_path: Path):
    """迁移单个文件：替换 print 为 logger"""
    content = file_path.read_text(encoding='utf-8')
    original_content = content
    
    # 添加 logger 导入（如果文件使用 print 但没有导入 logger）
    if 'print(' in content and 'logger' not in content:
        # 在文件开头的 import 之后添加 logger 导入
        lines = content.split('\n')
        insert_idx = 0
        
        # 找到最后一个 import 语句的位置
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_idx = i + 1
        
        # 插入 logger 导入
        lines.insert(insert_idx, 'from logger_config import get_logger')
        lines.insert(insert_idx + 1, '')
        lines.insert(insert_idx + 2, 'logger = get_logger(__name__)')
        lines.insert(insert_idx + 3, '')
        content = '\n'.join(lines)
    
    # 替换 print 语句
    # 简单的 print("xxx") -> logger.info("xxx")
    content = re.sub(
        r'print\(f"\[([A-Z]+)\]\s*(.+?)"\)',
        r'logger.info("[\1] \2")',
        content
    )
    content = re.sub(
        r'print\(f"(.+?)"\)',
        r'logger.info("\1")',
        content
    )
    content = re.sub(
        r'print\("(.+?)"\)',
        r'logger.info("\1")',
        content
    )
    
    # 更通用的替换
    content = re.sub(
        r'print\((.+?)\)',
        r'logger.info(\1)',
        content
    )
    
    if content != original_content:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ 已迁移: {file_path.name}")
        return True
    return False

def main():
    scripts_dir = Path(__file__).parent
    
    py_files = list(scripts_dir.glob('*.py'))
    # 排除自身和 logger_config
    py_files = [f for f in py_files if f.name not in ('migrate_to_logger.py', 'logger_config.py')]
    
    print(f"找到 {len(py_files)} 个 Python 文件")
    
    migrated = 0
    for py_file in py_files:
        if migrate_file(py_file):
            migrated += 1
    
    print(f"\n完成！迁移了 {migrated} 个文件")

if __name__ == '__main__':
    main()
