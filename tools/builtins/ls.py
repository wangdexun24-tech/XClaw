""" 列出目录出来给大模型看 """

from __future__ import annotations

from core.workspace import ensure_inside

DEFAULT_LIMIT = 500
MAX_BYTES = 30 * 1024

def ls(path:str=".",limit:int=DEFAULT_LIMIT):
    """列出目录下的**的直接子项**（不递归）
    目录名后加"/",让模型一眼区分目录还是文件
    """

    dir_path = ensure_inside(path)

    if not dir_path.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    if not dir_path.is_dir():
        raise ValueError(f"不是目录：{path}")

    entries = sorted(dir_path.iterdir(), key=lambda p: p.name.lower())

    lines = [entry.name + ("/" if entry.is_dir() else "") for entry in entries]

    if not lines:
        return "(空目录)"

    text = "\n".join(lines[:limit])
    if len(lines) > limit:
        text += f"\n\n[共 {len(lines)} 项，只显示前 {limit} 项；用 limit= 调大]"

    raw = text.encode("utf-8")
    if len(raw) > MAX_BYTES:
        text = raw[:MAX_BYTES].decode("utf-8", errors="ignore") + "\n\n[已按 30KB 截断]"

    return text
