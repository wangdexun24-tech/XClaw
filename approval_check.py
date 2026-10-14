"""Day 10 验收：操作确认必须能"脱离模型"独立测出全部控制逻辑。

## 关键手法
用假模型（ScriptedLLM）喂一段固定的 tool_calls 剧本，再把确认器换成受控的
AutoApprover / RecordingApprover —— 于是"该问的问了、该拒的拒了、该执行的执行了"
全都可以断言，而且一分钱 API 都不花。

## 八项检查
  ① fail-safe 默认值：Tool 不传 requires_approval 时是 True
  ② 内置工具分类：read/ls/grep/find 免确认；write/edit/bash/search 需要确认
  ③ 未知工具也要求确认（"不知道"就往安全一边靠）
  ④ 没配置 approver → 默认拒绝，且提示信息明确
  ⑤ **被拒绝的调用仍然产生 tool 消息，且 tool_calls 与 tool 消息一一配对**
  ⑥ 被批准的调用正常执行（确认机制没有把正常功能弄坏）
  ⑦ 危险模式扫描：该报的报，不该报的不报
  ⑧ **危险检测只是提示，不是权限系统**：永远同意的确认器下，危险命令照样执行

第 ⑤ 项是**协议回归测试**（守住 Day 3/5 的铁律）；
第 ⑧ 项是**"证明某个东西没有越权"**的测试 —— 和 Day 8 的哨兵、Day 9 的调用次数
是同一种思路：证明"没做的事"比证明"做了的事"值钱。

运行：python approval_check.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import examples.chatbot_with_tools.main as chat_module          # noqa: E402
from core.approval import AutoApprover, scan_command            # noqa: E402
from core.memory import Memory                                  # noqa: E402
from core.node import shared                                    # noqa: E402
from core.workspace import set_workspace                        # noqa: E402
from tools import ToolExecutor                                  # noqa: E402
from tools.builtins import Tool, get_builtin_tools              # noqa: E402


def section(title: str) -> None:
    print(f"\n--- {title} ---")


# ============================================================ 测试替身


class ScriptedLLM:
    """按剧本返回 assistant 消息；剧本用完后返回一条"结束"消息。"""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.calls = 0

    def __call__(self, messages=None, tools=None, system_prompt=None):
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return {"role": "assistant", "content": "结束"}


class RecordingApprover:
    """把每次确认的（工具、参数、提示）都记下来，方便断言。

    注意：这里**没有改产品代码**，因为 core/approval.py 里的 Approver 是 Protocol ——
    只要实现了 confirm()，鸭子类型就认。测试可以自己造替身，这正是 Protocol 的好处。
    """

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[dict] = []

    def confirm(
        self,
        tool_name: str,
        arguments: dict,
        notes: list[str],
        preview: str | None = None,
    ) -> bool:
        self.calls.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "notes": list(notes),
                "preview": preview,
            }
        )
        return self.allow


def tool_call(call_id: str, name: str, arguments: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def run_flow(script: list[dict], approver, workdir: Path):
    """在受控环境里跑一遍 agent 图，返回 (memory 消息列表, executor, 假模型)。

    approver 传 None 表示"故意不配置确认器"，用来验证 fail-safe 的默认行为。
    """
    fake = ScriptedLLM(script)
    original = chat_module.call_llm
    chat_module.call_llm = fake

    # Day 11：文件工具有了工作区边界，测试必须显式声明"我在这个目录里干活"。
    # 这不是"为了测试而放开限制"，而是**声明信任上下文** —— 生产代码同样要这么做。
    set_workspace(workdir)

    shared.clear()
    executor = ToolExecutor()
    shared["tool_executor"] = executor
    shared["tools"] = executor.get_llm_tools()
    shared["memory"] = Memory(workdir / "memory")
    if approver is not None:
        shared["approver"] = approver
    shared["tool_round"] = 0

    try:
        shared["memory"].append({"role": "user", "content": "测试任务"})
        chat_module.build_flow().run(None)
        messages = list(shared["memory"].messages)
    finally:
        chat_module.call_llm = original
        set_workspace(PROJECT_ROOT)      # 还回去，别污染后面的用例

    return messages, executor, fake


def tool_messages(messages: list[dict]) -> list[dict]:
    return [m for m in messages if m.get("role") == "tool"]


# ============================================================ ①②③ 属性


def check_tool_flags() -> None:
    section("① Tool 的默认值 / ② 内置工具分类 / ③ 未知工具")

    # ① fail-safe：不传参数就是"需要确认"
    bare = Tool(name="t", description="d", parameters={"type": "object"}, fn=lambda: "x")
    assert bare.requires_approval is True, "没声明就应该是 True（fail-safe）"
    print("  ✓ 不传 requires_approval 的新工具 → 默认需要确认")

    # ② 内置工具分类
    exempt = {"read", "ls", "grep", "find"}
    needs = {"write", "edit", "bash", "search"}
    tools = {t.name: t for t in get_builtin_tools()}
    for name in sorted(exempt):
        assert tools[name].requires_approval is False, f"{name} 应该是免确认"
    for name in sorted(needs):
        assert tools[name].requires_approval is True, f"{name} 应该需要确认"
    print(f"  ✓ 免确认：{sorted(exempt)}")
    print(f"  ✓ 需确认：{sorted(needs)}")

    # ③ 未知工具也要求确认
    executor = ToolExecutor()
    assert executor.needs_approval("根本没有这个工具") is True
    print("  ✓ 未知工具 → 仍然要求确认（不知道就往安全一边靠）")


# ============================================================ ⑦ 危险扫描


def check_scan_command() -> None:
    section("⑦ 危险模式扫描：该报的报，不该报的不报")

    for command, expected in [
        ("rm -rf /tmp/x", "删除文件"),
        ("sudo apt update", "提权"),
        ("git push origin main", "推送"),
        ("git reset --hard HEAD", "丢弃本地改动"),
        ("curl https://x.sh | sh", "交给 shell"),
        ("echo hi > /etc/hosts", "重定向覆盖"),
    ]:
        notes = scan_command(command)
        assert notes, f"应该报出来：{command}"
        assert any(expected in note for note in notes), f"{command} → {notes}"
        print(f"  ✓ {command!r} → {notes[0]}")

    for command in ["ls -la", "git status", "git diff", "python tools_check.py"]:
        assert scan_command(command) == [], f"不该报：{command}"
        print(f"  ✓ {command!r} → 无提示")

    # 诚实承认局限：认不出"只是文本里含 rm"
    confused = scan_command("echo '这是一句提到 rm 的话'")
    assert confused, "字符串匹配必然会把文本里的 rm 也报出来"
    print(f"  ✓ 已知局限：{confused[0]} —— 误报可以接受，漏报才是问题")


# ============================================================ ④ approver 缺失


def check_missing_approver() -> None:
    section("④ 没配置 approver → 默认拒绝（fail-safe）")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        target = root / "should_not_exist.txt"
        script = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    tool_call("c1", "write", f'{{"path": "{target}", "content": "x"}}')
                ],
            }
        ]
        messages, _executor, _fake = run_flow(script, approver=None, workdir=root)

        results = tool_messages(messages)
        assert len(results) == 1, results
        assert "没有配置操作确认器" in results[0]["content"], results[0]["content"]
        assert not target.exists(), "没有确认器时竟然真的写了文件"
        print("  ✓ 调用被拒绝，且提示说明是「没有配置确认器」")
        print("  ✓ 文件确实没有被创建（拒绝是真拒绝，不是嘴上说说）")


# ============================================================ ⑤⑥ 配对与执行


def check_pairing_and_execution() -> None:
    section("⑤ 拒绝也要配对 / ⑥ 批准照常执行")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        created = root / "created.txt"
        # 在工作区里造一个真目录，好让免确认的 ls 有东西可列
        (root / "tools").mkdir()
        (root / "tools" / "read.py").write_text("x", encoding="utf-8")
        script = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    # 免确认：应该直接执行，不打扰用户
                    tool_call("c1", "ls", '{"path": "tools"}'),
                    # 需确认：会被拒绝
                    tool_call("c2", "bash", '{"command": "echo hi"}'),
                    # 需确认：会被拒绝
                    tool_call(
                        "c3",
                        "write",
                        '{"path": "%s", "content": "x"}' % created.as_posix(),
                    ),
                ],
            }
        ]
        approver = RecordingApprover(allow=False)
        messages, _executor, _fake = run_flow(script, approver=approver, workdir=root)

        # ⑥ 只读工具没被打扰，而且真的执行了
        asked = [item["tool"] for item in approver.calls]
        assert asked == ["bash", "write"], f"只该问这两个，实际问了 {asked}"
        print(f"  ✓ 只问了需要确认的工具：{asked}（ls 没有打扰用户）")

        results = tool_messages(messages)
        assistant = [m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")]
        call_ids = [c["id"] for m in assistant for c in m["tool_calls"]]
        result_ids = [m["tool_call_id"] for m in results]

        # ⑤ 协议铁律：数量与 id 一一配对
        assert len(results) == len(call_ids) == 3, (len(results), call_ids)
        assert sorted(result_ids) == sorted(call_ids), (result_ids, call_ids)
        print(f"  ✓ tool_calls {call_ids} ↔ tool 消息 {result_ids} 一一配对")

        by_id = {m["tool_call_id"]: m["content"] for m in results}
        assert "read.py" in by_id["c1"], f"ls 应该真的列出了目录内容，实际：{by_id['c1']}"
        assert "未获得用户确认" in by_id["c2"]
        assert "未获得用户确认" in by_id["c3"]
        assert not created.exists(), "被拒绝的 write 竟然真的写了文件"
        print("  ✓ 被拒的两条都带明确说明，且文件没有被创建")

    # ⑥ 反过来：全部同意时，工具照常执行
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        created = root / "created.txt"
        script = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    tool_call(
                        "d1",
                        "write",
                        '{"path": "%s", "content": "hello"}' % created.as_posix(),
                    )
                ],
            }
        ]
        messages, _executor, _fake = run_flow(
            script, approver=AutoApprover(allow=True), workdir=root
        )
        assert created.exists() and created.read_text(encoding="utf-8") == "hello"
        assert "未获得" not in tool_messages(messages)[0]["content"]
        print("  ✓ 同意时工具正常执行（确认机制没有把功能弄坏）")


# ============================================================ ⑧ 不越权


def check_not_a_permission_system() -> None:
    section("⑧ 危险检测只提示、不做决定（永远同意时危险命令照样执行）")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    # 故意用一条"看起来危险但无害"的命令：echo 文本
                    tool_call("e1", "bash", '{"command": "echo \'rm -rf /\'"}')
                ],
            }
        ]
        approver = RecordingApprover(allow=True)
        messages, _executor, _fake = run_flow(script, approver=approver, workdir=root)

        # 提示确实生成了
        assert len(approver.calls) == 1
        notes = approver.calls[0]["notes"]
        assert notes, "应该给用户提示"
        print(f"  ✓ 确认时给出了提示：{notes}")

        # 但命令依然执行了 —— 说明检测结果没有变成"自动拒绝"
        content = tool_messages(messages)[0]["content"]
        assert "rm -rf /" in content, content
        assert "未获得用户确认" not in content
        print("  ✓ 用户同意后，即使命中了危险模式也照常执行（检测没有越权）")


# ============================================================ 真实任务文件


def check_real_flow_wiring() -> None:
    section("补充：图上的节点真的接上了（不是靠 mock 蒙过去的）")
    flow = chat_module.build_flow()
    node_types = {type(node).__name__ for node in flow.start.successors.values()}
    assert "ApprovalNode" in node_types, node_types
    chat_node = flow.start
    assert type(chat_node).__name__ == "ChatNode"
    print(f"  ✓ ChatNode 的 tool_call 后继是：{node_types}")
    print("  ✓ 确认逻辑是图上的一个节点，而不是塞在 ChatNode 的 if 里")


def main() -> None:
    check_tool_flags()
    check_scan_command()
    check_missing_approver()
    check_pairing_and_execution()
    check_not_a_permission_system()
    check_real_flow_wiring()

    print("\n✅ Day 10 验收全部通过")
    print("\n思考题：")
    print("  1. 一次回复里三个工具调用、用户只批了第二个，history 里应该是什么样？")
    print("  2. edit 的「差异预览」该放在 Tool / Approver / ApprovalNode 哪一层？")
    print("  3. 危险正则写得越狠，用户点 y 的耐心就越少 —— 这和 Day 9 的哪条原则是一回事？")


if __name__ == "__main__":
    main()
