"""读取文件。"""

from __future__ import annotations

from core.workspace import ensure_inside

DEFAULT_MAX_BYTES = 30 * 1024       # 30KB，防止一次读爆上下文


def read_file(path: str, offset: int = 1, limit: int | None = None) -> str:
    """读文件内容。offset 从 1 开始（和编辑器行号一致）。"""
    file_path = ensure_inside(path)

    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    if not file_path.is_file():
        raise ValueError(f"不是文件：{path}")

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)

    start = max(0, offset - 1)
    if start >= total:
        raise ValueError(f"offset={offset} 超出范围（文件共 {total} 行）")

    end = total if limit is None else min(start + limit, total)
    text = "\n".join(lines[start:end])

    raw = text.encode("utf-8")
    if len(raw) > DEFAULT_MAX_BYTES:
        text = raw[:DEFAULT_MAX_BYTES].decode("utf-8", errors="ignore")
        end = start + text.count("\n")
        text += (
            f"\n\n[已按 30KB 截断：显示第 {start + 1}-{end} 行，共 {total} 行；"
            f"用 offset={end + 1} 继续读]"
        )
    elif end < total:
        text += f"\n\n[还有 {total - end} 行；用 offset={end + 1} 继续读]"

    return text
