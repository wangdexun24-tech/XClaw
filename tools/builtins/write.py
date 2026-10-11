"""写入文件（覆盖）。"""

from __future__ import annotations

from pathlib import Path


def write_file(path: str, content: str) -> str:
    """写入文件，父目录不存在时自动创建。"""
    file_path = Path(path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    line_count = content.count("\n") + 1
    return f"已写入 {path}（{len(content)} 字符，{line_count} 行）"