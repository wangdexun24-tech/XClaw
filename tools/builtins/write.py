"""写入文件（覆盖）。"""

from __future__ import annotations

from core.workspace import atomic_write, ensure_inside


def write_file(path: str, content: str) -> str:
    """写入文件，父目录不存在时自动创建。"""
    file_path = ensure_inside(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 原子写：先写临时文件再改名，避免写一半把原文件弄坏
    atomic_write(file_path, content)

    line_count = content.count("\n") + 1
    return f"已写入 {path}（{len(content)} 字符，{line_count} 行）"
