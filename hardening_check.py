"""Day 11 验收：工程化加固必须能"脱离模型"独立测出来。

这一天的五件事都来自"同类项目做得更好的地方"，但它们有一个共同点：
**全都是"该拦的拦住了、该保的保住了"这类否定性保证** ——
所以验收的重点也是"证明坏情况没发生"，而不是"证明好情况发生了"。

五个部分：
  ① 工作区边界：绕出去要拦住（含 **符号链接穿透** 和 **前缀陷阱** 两个经典绕过）
  ② 原子写：正常路径不留垃圾；失败路径不毁原对象
  ③ 压缩前归档：归档必须是"压缩之前"的完整历史；**归档失败就不许压缩**
  ④ 中断恢复：没走完的一轮要丢掉；**完整的历史一个字都不能动**
  ⑤ 差异预览：只读参数不碰文件；且真的传到了确认器

运行：python hardening_check.py
"""

from __future__ import annotations

import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.approval import AutoApprover                          # noqa: E402
from core.memory import Memory, drop_incomplete_round           # noqa: E402
from core.workspace import (                                    # noqa: E402
    WorkspaceError,
    ensure_inside,
    get_root,
    set_workspace,
)
from tools.builtins import edit_preview, get_builtin_tools, read_file, write_file  # noqa: E402


def section(title: str) -> None:
    print(f"\n--- {title} ---")


@contextmanager
def raises(exc_type):
    """一个极简的"断言这里会抛异常"的上下文管理器。

    为什么要自己写：脚本不想引入 pytest。原理就是 try/except + 没抛就报错。
    """
    try:
        yield
    except exc_type:
        return
    except Exception as other:                                   # noqa: BLE001
        raise AssertionError(f"期望 {exc_type.__name__}，实际抛了 {type(other).__name__}: {other}")
    raise AssertionError(f"期望抛出 {exc_type.__name__}，但什么都没抛")


@contextmanager
def workspace(path, allow_outside: bool | None = None):
    """临时把工作区切过去，结束时恢复 —— 测试之间不能互相污染。"""
    previous_root = get_root()
    set_workspace(path, allow_outside)
    try:
        yield
    finally:
        set_workspace(previous_root, allow_outside=False)


# ============================================================ ① 工作区边界


def check_workspace_boundary() -> None:
    section("① 工作区边界：绕出去要拦住")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "inside.txt").write_text("ok", encoding="utf-8")

        with workspace(root):
            # 正常：工作区内的相对路径
            assert read_file("inside.txt") == "ok"
            print("  ✓ 工作区内的相对路径正常读取")

            # ../ 往上绕
            with raises(WorkspaceError):
                read_file("../outside.txt")
            print("  ✓ ../ 绕出去 → WorkspaceError")

            # 绝对路径在工作区外
            with raises(WorkspaceError):
                write_file("/etc/xclaw_should_not_exist.txt", "x")
            print("  ✓ 工作区外的绝对路径 → WorkspaceError")

            # ★ 符号链接穿透：工作区里的软链指向外面
            # 这条证明"必须先 resolve 再判断"，只做字符串比较是拦不住的
            (root / "link.txt").symlink_to("/etc/hosts")
            with raises(WorkspaceError):
                read_file("link.txt")
            print("  ✓ 符号链接指向工作区外 → WorkspaceError（resolve 之后才判得出来）")

            # ★ 前缀陷阱：/tmp/xxx 和 /tmp/xxx_evil 不是同一个工作区
            # 这条证明"要用 parents 判断，不能用字符串前缀"
            evil = Path(str(root) + "_evil")
            try:
                evil.mkdir(parents=True, exist_ok=True)
                (evil / "a.txt").write_text("x", encoding="utf-8")
                with raises(WorkspaceError):
                    read_file(str(evil / "a.txt"))
                print("  ✓ 前缀相同的兄弟目录 → WorkspaceError（不是 startswith 判断）")
            finally:
                try:
                    (evil / "a.txt").unlink()
                    evil.rmdir()
                except OSError:
                    pass

            # ensure_inside 返回的是解析后的绝对路径
            resolved = ensure_inside("inside.txt")
            assert resolved.is_absolute() and resolved == (root / "inside.txt").resolve()
            print("  ✓ ensure_inside 返回已解析的绝对路径（检查的和使用的是同一个）")

        # 显式放行时，上面那条软链才读得到
        with workspace(root, allow_outside=True):
            assert read_file("link.txt")
            print("  ✓ allow_outside=True 时才放行工作区外的路径")


# ============================================================ ② 原子写


def check_atomic_write() -> None:
    section("② 原子写：不留垃圾、不毁原对象")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        with workspace(root):
            # 覆盖已有文件
            write_file("a.txt", "第一版")
            write_file("a.txt", "第二版")
            assert (root / "a.txt").read_text(encoding="utf-8") == "第二版"
            assert not list(root.glob(".*.tmp")), "不该留下临时文件"
            print("  ✓ 覆盖写正常，且没有留下 .tmp 残骸")

            # 父目录自动创建
            write_file("deep/nested/b.txt", "x")
            assert (root / "deep" / "nested" / "b.txt").is_file()
            print("  ✓ 父目录不存在时自动创建")

            # 失败路径：目标是目录 → 报错，但目录本身必须还在
            (root / "adir").mkdir()
            with raises(OSError):
                write_file("adir", "x")
            assert (root / "adir").is_dir(), "写失败不能把目标弄没了"
            print("  ✓ 写失败时目标对象仍然完好")

        print("  · 说明：真正的原子性（断电、磁盘满）在单测里验不了，")
        print("    这里只验证'正常路径不留垃圾 + 失败路径不毁原对象'。")


# ============================================================ ③ 压缩前归档


def check_archive_before_compress() -> None:
    section("③ 压缩前归档：先存原始记录，再压")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = Memory(root / "mem")
        for index in range(20):
            memory.append({"role": "user", "content": f"第 {index} 条"})

        before_count = len(memory.messages)
        # 别真的调模型：把摘要函数换掉
        memory._summarize = lambda messages: "这是摘要"        # type: ignore[method-assign]

        assert memory.maybe_compress(10 ** 9) is True, "应该真的压缩了"

        archives = sorted((root / "mem" / "archive").glob("*.jsonl"))
        assert len(archives) == 1, archives
        lines = archives[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == before_count, (
            f"归档必须是**压缩之前**的完整历史：期望 {before_count} 行，实际 {len(lines)} 行"
        )
        assert "第 0 条" in lines[0], "归档里应该有那些即将被压掉的原始消息"
        assert len(memory.messages) < before_count, "压缩后内存里的消息应该变少"
        print(f"  ✓ 压缩 {before_count} 条 → {len(memory.messages)} 条，归档 {len(lines)} 条")

        # ★ 归档失败 → 必须放弃压缩，保留原始历史
        memory2 = Memory(root / "mem2")
        for index in range(20):
            memory2.append({"role": "user", "content": f"第 {index} 条"})
        (root / "mem2" / "archive").write_text("我是文件，不是目录", encoding="utf-8")
        memory2._summarize = lambda messages: "这是摘要"        # type: ignore[method-assign]

        snapshot = [dict(item) for item in memory2.messages]
        assert memory2.maybe_compress(10 ** 9) is False, "归档失败时必须返回 False"
        assert memory2.messages == snapshot, "归档失败时必须保留原始历史，一条都不能丢"
        print("  ✓ 归档失败 → 不压缩，原始历史原封不动")


# ============================================================ ④ 中断恢复


def check_interrupt_repair() -> None:
    section("④ 中断恢复：丢掉半截的一轮，别碰完整的历史")

    # 没走完的一轮 → 整轮丢掉（连它的 user 提问一起）
    broken = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "答"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "tool_calls": [{"id": "c1"}]},      # 断在这里
    ]
    assert drop_incomplete_round(broken) is True
    assert broken == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "答"},
    ], broken
    print("  ✓ 半截的一轮被丢掉（连它的 user 提问一起）")

    # 完整的一轮 → 一个字都不能动
    intact = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "r"},
        {"role": "assistant", "content": "答"},
    ]
    snapshot = [dict(item) for item in intact]
    assert drop_incomplete_round(intact) is False
    assert intact == snapshot, "完整的历史被改动了 —— 恢复逻辑写过头了"
    print("  ✓ 完整的历史一个字都没动")

    # 已知的保守行为：历史停在 tool 结果上时会被清掉
    tail_on_tool = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "r"},
    ]
    assert drop_incomplete_round(tail_on_tool) is True
    print("  ✓ 已知的保守行为：以 tool 结果结尾时也会被清掉（宁可多删，不发被拒的历史）")

    # 没有任何 tool_calls → 不用管
    plain = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    assert drop_incomplete_round(plain) is False
    print("  ✓ 普通对话不受影响")

    # Memory.repair 必须落盘
    with tempfile.TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir) / "mem3"
        memory = Memory(directory)
        memory.append({"role": "user", "content": "q"})
        memory.append({"role": "assistant", "tool_calls": [{"id": "c1"}]})

        assert memory.repair() is True
        assert memory.messages == []
        assert Memory(directory).messages == [], "修复结果必须落盘，否则重启后又会复发"
        print("  ✓ repair() 修完立刻落盘（重启读回来也是干净的）")

        # 幂等：没毛病时不该报告"修过"
        assert memory.repair() is False
        print("  ✓ 已经干净时 repair() 返回 False（幂等）")


# ============================================================ ⑤ 差异预览


def check_preview() -> None:
    section("⑤ 差异预览：只读参数，且真的传到了确认器")

    preview = edit_preview({"old_text": "a\nb", "new_text": "a\nc"})
    assert preview and "-b" in preview and "+c" in preview, preview
    print("  ✓ 生成的 diff 里有被删的行和新增的行")

    # 参数不合法 → None（预览是尽力而为，不能挡住确认流程）
    assert edit_preview({"old_text": "", "new_text": "x"}) is None
    assert edit_preview({"old_text": "a"}) is None
    assert edit_preview({"old_text": 123, "new_text": "x"}) is None
    print("  ✓ 参数不合法时返回 None，不抛异常")

    # ★ 预览不碰文件：给一个根本不存在的路径，照样能算出 diff
    preview = edit_preview(
        {"path": "/根本不存在的/文件.txt", "old_text": "a", "new_text": "b"}
    )
    assert preview, "预览只读参数，不该去读文件"
    print("  ✓ 路径不存在也能生成预览 → 证明它没有读文件")

    # 没有 preview 的工具 → None
    tools = {tool.name: tool for tool in get_builtin_tools()}
    assert tools["bash"].build_preview({"command": "ls"}) is None
    assert tools["read"].build_preview({"path": "x"}) is None
    assert tools["edit"].build_preview({"old_text": "a", "new_text": "b"}) is not None
    print("  ✓ 只有 edit 有预览，其它工具返回 None")

    # ★ 预览真的传到了确认器（不是只生成了却没人用）
    import examples.chatbot_with_tools.main as chat_module
    from core.memory import Memory as Mem
    from core.node import shared
    from tools import ToolExecutor

    class Recording:
        def __init__(self):
            self.calls = []

        def confirm(self, tool_name, arguments, notes, preview=None):
            self.calls.append({"tool": tool_name, "preview": preview})
            return False        # 拒绝，避免真的改文件

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "target.txt").write_text("a\nb\n", encoding="utf-8")

        # 只演一轮：先请求一次 edit，然后就说"结束"。
        # （如果一直返回 tool_calls，会一路跑到 MAX_TOOL_ROUNDS 才停，输出很难看）
        script = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "edit",
                            "arguments": '{"path": "target.txt", "old_text": "a", "new_text": "z"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "结束了"},
        ]

        def fake(**kwargs):
            return script.pop(0) if script else {"role": "assistant", "content": "结束了"}
        original = chat_module.call_llm
        chat_module.call_llm = fake
        recorder = Recording()
        try:
            with workspace(root):
                shared.clear()
                executor = ToolExecutor()
                shared["tool_executor"] = executor
                shared["tools"] = executor.get_llm_tools()
                shared["memory"] = Mem(root / "mem")
                shared["approver"] = recorder
                shared["tool_round"] = 0
                shared["memory"].append({"role": "user", "content": "改一下"})
                chat_module.build_flow().run(None)
        finally:
            chat_module.call_llm = original

        assert recorder.calls, "确认器根本没被调用"
        assert recorder.calls[0]["preview"], "预览生成出来了，但没有传给确认器"
        assert (root / "target.txt").read_text(encoding="utf-8") == "a\nb\n"
        print("  ✓ 预览确实传到了确认器，且被拒绝后文件没被改")


def main() -> None:
    check_workspace_boundary()
    check_atomic_write()
    check_archive_before_compress()
    check_interrupt_repair()
    check_preview()

    print("\n✅ Day 11 验收全部通过")
    print("\n思考题：")
    print("  1. 为什么用 parents 判断而不是字符串前缀？举一个 startswith 会误判的例子。")
    print("  2. 为什么预览失败要 return None 而不是抛异常？")
    print("  3. Day 6 的崩溃恢复为什么当时只在读文件时用，现在内存里也要用？")


if __name__ == "__main__":
    main()
