"""在文件内容里搜索文本。"""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_LIMIT = 100
MAX_BYTES = 30 * 1024
MAX_LINE_CHARS = 500

# 递归搜索时跳过的目录（这些目录里没有"源码"，只有噪音）
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".idea", "node_modules"}

# 明显是二进制的扩展名，直接跳过
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".zip",
                 ".pdf", ".so", ".dylib", ".woff", ".woff2", ".lock"}


def grep(
    pattern: str,
    path: str = ".",
    limit: int = DEFAULT_LIMIT,
    ignore_case: bool = False,
    literal: bool = False,
) -> str:
    """搜索文件内容，返回 `相对路径:行号:行内容`。

    literal=True 时把 pattern 当普通文本（不当正则）。
    """
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"路径不存在：{path}")

    flags = re.IGNORECASE if ignore_case else 0
    if literal:
        pattern = re.escape(pattern)
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"正则表达式不合法：{exc}") from exc

    files = [target] if target.is_file() else list(_iter_files(target))

    matches: list[str] = []
    for file_path in files:
        if len(matches) >= limit:
            break
        matches.extend(_search_file(file_path, regex, limit - len(matches), target))

    if not matches:
        return f"没有找到匹配 {pattern!r} 的内容"

    text = "\n".join(matches)
    if len(matches) >= limit:
        text += f"\n\n[已达到 {limit} 条上限，可能还有更多匹配]"

    raw = text.encode("utf-8")
    if len(raw) > MAX_BYTES:
        text = raw[:MAX_BYTES].decode("utf-8", errors="ignore") + "\n\n[已按 30KB 截断]"

    return text


def _iter_files(root: Path):
    """递归遍历文件，跳过噪音目录。"""
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]   # 原地改，os.walk 才会跳过
        for name in filenames:
            if Path(name).suffix.lower() in SKIP_SUFFIXES:
                continue
            yield Path(current) / name


def _search_file(file_path: Path, regex, limit: int, root: Path) -> list[str]:
    """搜单个文件，返回若干条 `路径:行号:内容`。"""
    if limit <= 0:
        return []

    try:
        raw = file_path.read_bytes()
    except OSError:
        return []

    if b"\x00" in raw[:1024]:        # 含空字节 → 当成二进制，跳过
        return []

    try:
        shown_path = file_path.relative_to(root) if root.is_dir() else file_path.name
    except ValueError:
        shown_path = file_path.name

    results: list[str] = []
    text = raw.decode("utf-8", errors="replace")

    for number, line in enumerate(text.splitlines(), start=1):
        if not regex.search(line):
            continue

        display = line.rstrip()
        if len(display) > MAX_LINE_CHARS:
            display = display[:MAX_LINE_CHARS] + "…"

        results.append(f"{shown_path}:{number}:{display}")
        if len(results) >= limit:
            break

    return results