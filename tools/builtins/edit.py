"""精确编辑：替换文件里唯一出现的一处文本。"""

from __future__ import annotations

from pathlib import Path


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """把唯一的 old_text 替换成 new_text。

    为什么要求"唯一"：模型给出的片段若不唯一，改哪一处就是猜。
    宁可拒绝、让它给更长的片段，也不要猜错。
    """
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")

    original = file_path.read_text(encoding="utf-8", errors="replace")

    count = original.count(old_text)
    if count == 0:
        raise ValueError("没找到要替换的文本（缩进和换行必须完全一致）")
    if count > 1:
        raise ValueError(f"要替换的文本出现了 {count} 次，请给出更长、更独特的片段")

    updated = original.replace(old_text, new_text, 1)

    # 原子写：先写临时文件再改名，避免写一半把原文件弄坏
    tmp = file_path.with_name("." + file_path.name + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(file_path)

    return f"已修改 {path}（替换 1 处）"