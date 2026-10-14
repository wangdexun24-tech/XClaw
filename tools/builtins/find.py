"""按通配符查找文件。"""

from __future__ import annotations

import os
from pathlib import Path

from core.workspace import ensure_inside

DEFAULT_LIMIT = 200
MAX_BYTES = 30 * 1024

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".idea", "node_modules"}


def find(pattern: str, path: str = ".", limit: int = DEFAULT_LIMIT) -> str:
    """按通配符查找文件，如 "*.py"、"test_*.py"。

    只返回**文件**（不返回目录），路径相对搜索起点。
    """
    root = ensure_inside(path)

    if not root.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    if not root.is_dir():
        raise ValueError(f"不是目录：{path}")

    matches: list[str] = []

    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for name in filenames:
            if not Path(name).match(pattern):        # fnmatch 语义
                continue
            matches.append(str((Path(current) / name).relative_to(root)))
            if len(matches) >= limit:
                break

        if len(matches) >= limit:
            break

    if not matches:
        return f"没有找到匹配 {pattern!r} 的文件"

    matches.sort()
    text = "\n".join(matches)

    if len(matches) >= limit:
        text += f"\n\n[已达到 {limit} 条上限，可能还有更多]"

    raw = text.encode("utf-8")
    if len(raw) > MAX_BYTES:
        text = raw[:MAX_BYTES].decode("utf-8", errors="ignore") + "\n\n[已按 30KB 截断]"

    return text
