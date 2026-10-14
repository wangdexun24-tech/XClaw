"""精确编辑：替换文件里唯一出现的一处文本。"""

from __future__ import annotations

import difflib

from core.workspace import atomic_write, ensure_inside

def edit_file(path: str, old_text: str, new_text: str) -> str:
    """把唯一的 old_text 替换成 new_text。

    为什么要求"唯一"：模型给出的片段若不唯一，改哪一处就是猜。
    宁可拒绝、让它给更长的片段，也不要猜错。
    """
    file_path = ensure_inside(path)
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
    atomic_write(file_path, updated)

    return f"已修改 {path}（替换 1 处）"


def edit_preview(arguments: dict) -> str | None:
    """根据 edit 的参数生成差异预览。

    ⚠️ **只读参数，不读文件、不写文件。**
    只预览"要被替换的那一段"，而不是整个文件的差异 ——
    读整个文件既慢，又会在"预览"和"真正执行"之间产生时间差。
    片段是否唯一匹配，留到执行时再检查（那时才有权威答案）。

    为什么这个函数放在工具这一层，而不是放在确认器或节点里：
    只有工具自己知道 old_text / new_text 是什么意思。
    确认器要保持通用（它还要服务 MCP 工具），节点也不该认识 edit 的语义。
    """
    old = arguments.get("old_text")
    new = arguments.get("new_text")
    if not isinstance(old, str) or not isinstance(new, str) or not old:
        return None

    lines = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile="原文",
        tofile="修改后",
        lineterm="",
        n=2,
    )
    text = "\n".join(lines)
    if not text:
        return "(替换前后内容相同)"
    if len(text) > 2000:
        text = text[:2000] + "\n…[预览已截断]"
    return text
