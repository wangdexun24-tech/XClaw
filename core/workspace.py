"""Day 11 · 工作区边界：文件工具只能碰工作区里的路径。

## 为什么需要它
Day 4 起，read/write/edit/ls/grep/find 都接受**任意路径**。
模型完全可以说"帮我看看 ~/.ssh/id_rsa"，或者用 `../../etc/passwd` 绕出去，
而没有任何拦截。同类的 ZipClaw 在这一点上做得更严：它的文件工具会检查工作区边界。

## 它是怎么起作用的
工具的签名是 `fn(**kwargs)`，参数**完全由模型决定** —— 所以边界不能从参数里来，
只能从"进程当前的信任上下文"里来。这里用一个模块级的全局工作区根目录。

## 为什么要把路径 resolve() 之后再判断
    工作区 .                      传给工具的路径
      ├── src/app.py              a.py                → 在工作区内 ✓
      └── link -> /etc/passwd     ../../etc/passwd    → 解析后跑出去了 ✗
                                  link                → 解析后是 /etc/passwd ✗

`Path.resolve()` 会展开 `..` 和**符号链接**，所以上面两种绕法都拦得住。
只做字符串前缀比较（`str(path).startswith(root)`）既挡不住 symlink，
又会把 `/tmp/ws_evil` 误判成 `/tmp/ws` 的子路径。

## 诚实的局限
1. 这是"防手滑"，不是"防恶意"。模型有 `bash`，`cat /etc/passwd` 照样能读 ——
   真正的隔离要靠容器/沙箱，不是靠路径判断。路径边界和 bash 是**两件事**，
   后者归 Day 10 的操作确认管。
2. 用的是全局状态，不如显式依赖注入优雅。和 `shared` 一样，
   这是为了教学可读性做的取舍（生产里应该由调用方显式传入）。
"""

from __future__ import annotations

import os
from pathlib import Path

ALLOW_OUTSIDE_ENV = "XCLAW_ALLOW_OUTSIDE"


class WorkspaceError(ValueError):
    """访问了工作区之外的路径。

    刻意用一个专门的异常类型（而不是裸的 ValueError），
    这样 Executor 的异常分支能把它和"参数写错了"区分开，
    也能给出"怎么解开这个限制"的提示。
    """


class _Workspace:
    """当前的信任上下文。"""

    def __init__(self, root: Path, allow_outside: bool) -> None:
        self.root = root
        self.allow_outside = allow_outside


_WORKSPACE = _Workspace(
    root=Path.cwd().resolve(),
    # 需要完全访问时用环境变量显式打开；默认关闭
    allow_outside=os.environ.get(ALLOW_OUTSIDE_ENV) == "1",
)


def get_root() -> Path:
    """当前工作区根目录。"""
    return _WORKSPACE.root


def allows_outside() -> bool:
    return _WORKSPACE.allow_outside


def set_workspace(root: str | Path, allow_outside: bool | None = None) -> None:
    """切换工作区。示例入口、长任务、以及测试都会调用它。

    allow_outside 传 None 表示"不改动当前的开关"。
    """
    _WORKSPACE.root = Path(root).resolve()
    if allow_outside is not None:
        _WORKSPACE.allow_outside = allow_outside


def ensure_inside(path: str | Path) -> Path:
    """把相对路径按工作区解析，并确认它没有跑到工作区外面去。

    返回**已解析的绝对路径** —— 工具直接拿它用，不要再 resolve 一次，
    否则可能出现"检查的是 A、使用的是 B"这种 TOCTOU 式的问题。
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _WORKSPACE.root / candidate

    resolved = candidate.resolve()

    if _WORKSPACE.allow_outside:
        return resolved

    # 用 parents 判断"是不是子路径"，比字符串前缀可靠得多：
    #   root=/a/b   resolved=/a/bc/d  → 字符串前缀会说"是"，parents 会说"不是"
    if resolved == _WORKSPACE.root or _WORKSPACE.root in resolved.parents:
        return resolved

    raise WorkspaceError(
        f"路径在工作区之外，已拒绝：{path}\n"
        f"工作区：{_WORKSPACE.root}\n"
        f"确实需要访问工作区外时，设置环境变量 {ALLOW_OUTSIDE_ENV}=1，"
        f"或调用 set_workspace(..., allow_outside=True)。"
    )


def atomic_write(path: Path, text: str) -> None:
    """原子写：先写同目录的临时文件，再改名覆盖。

    为什么不能直接 `path.write_text(text)`：写到一半崩了（磁盘满、进程被杀），
    原文件就变成半截 —— 而"改坏一个文件"比"没改成"严重得多。
    先写临时文件则保证"要么全成、要么原文件一点没动"。

    用 `replace` 而不是 `rename`：Windows 上 rename 不能覆盖已存在的目标。

    （这个函数是从 write.py 和 edit.py 里重复的那两段提上来的 ——
     同一份逻辑出现在第二个地方，就该提取。）
    """
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
