"""Day 10 · 操作确认：把"是否允许执行"变成图上一个可插拔的节点。

## 为什么需要它
Day 4 起，bash 用 shell=True 执行任意命令而没有拦截，README 的"已知限制"一直挂着这条。

## 为什么做成节点，而不是往 ChatNode 里加 if
参考同类项目（ZipClaw）的教训：它把确认逻辑和循环逻辑放在同一个类里，
结果主循环涨到 788 行。在"控制流是数据"的图里，确认是一段独立的控制流，
所以它应该是一个节点 —— 节点只负责**决定**，执行仍然是 ToolCallNode 的活。

## 三条设计原则
1. fail-safe 默认值：Tool.requires_approval 默认 True；没配置 approver 时默认拒绝；
   未知工具也要求确认。忘记声明的后果必须是"多问一句"，不能是"默默放行"。
2. 拒绝也要回一条 tool 消息 —— 消息配对是铁律（Day 3/5）。
3. 危险检测只提示人，不做决定。正则永远会漏，所以它只能提高注意力，
   不能代替人的判断。
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from core.node import Node, shared

# 只用于**提示**的危险模式，不参与放行/拒绝的判断
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\b", "删除文件（rm）"),
    (r"\bsudo\b", "提权执行（sudo）"),
    (r"\bchmod\b|\bchown\b", "修改文件权限"),
    (r"git\s+push", "推送到远端仓库"),
    (r"git\s+reset\s+--hard|git\s+clean", "丢弃本地改动"),
    (r"\|\s*(ba)?sh\b", "把管道内容直接交给 shell 执行"),
    (r"\b(pkill|killall|kill)\b", "结束进程"),
    (r"(^|\s)>\s*\S", "重定向覆盖文件"),
]

def scan_command(command: str) -> list[str]:
    """扫一遍命令，返回"值得提醒人"的说明列表。

    ⚠️ 这只是提示。它的输出**不参与**任何放行/拒绝的判断 ——
    因为正则永远会漏（find -delete、python -c "shutil.rmtree(...)"），
    它的作用是让人多看一眼，不是替人做决定。
    """
    hits: list[str] = []
    for pattern, label in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            hits.append(label)
    return hits

class Approver(Protocol):
    """确认器的接口。返回 True 表示允许执行。"""

    def confirm(self, tool_name: str, arguments: dict, notes: list[str]) -> bool:
        ...

class ConsoleApprover:
    """终端交互式确认。

    为什么把 input/print 做成参数（而不是直接用内置函数）？
    因为 input() 会阻塞，测试里没法用。注入之后，测试可以传一个假的 input，
    **"会阻塞人"的东西就变得可测了**。
    """

    def __init__(self, input_fn=input, print_fn=print) -> None:
        self._input = input_fn
        self._print = print_fn

    def confirm(self, tool_name: str, arguments: dict, notes: list[str]) -> bool:
        self._print("\n" + "─" * 60)
        self._print(f"[需要确认] {tool_name}")
        self._print("完整参数（不截断 —— 人要据此做决定）：")
        self._print(json.dumps(arguments, ensure_ascii=False, indent=2))
        for note in notes:
            self._print(f"  ⚠️ {note}")
        self._print("─" * 60)

        try:
            answer = self._input("允许执行吗？输入 y 同意，其它一律拒绝 [y/N]：")
        except (EOFError, KeyboardInterrupt):
            # 读不到输入、或者用户在确认时按了 Ctrl+C —— 都不能算同意
            self._print("（未获得确认，按拒绝处理）")
            return False
        return answer.strip().lower() in {"y", "yes"}

class AutoApprover:
    """全部放行 / 全部拒绝。**只用于离线验收和自动跑的长任务**。

    calls 记下每一次被问到的（工具名，参数），测试要断言"问了哪些、问了几次"。
    """

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[tuple[str, dict]] = []

    def confirm(self, tool_name: str, arguments: dict, notes: list[str]) -> bool:
        self.calls.append((tool_name, arguments))
        return self.allow

DENIED_TEMPLATE = (
    "本次工具调用未获得用户确认，未执行任何操作。"
    "请向用户说明情况，不要自行重试，也不要改用其它工具去完成同一件被拒绝的事。"
)

class ApprovalNode(Node):
    """决定每个工具调用是否放行；结果写进 shared["denied"]。"""

    def exec(self, payload: Any) -> tuple[str, Any]:
        executor = shared["tool_executor"]
        approver = shared.get("approver")
        denied: dict[str, str] = {}

        for call in executor.parse_tool_calls(payload):
            # 纯读工具直接放行 —— 不打扰用户
            if not executor.needs_approval(call.name):
                continue

            # fail-safe：没有配置确认器就拒绝，而不是默默放行
            if approver is None:
                denied[call.id] = (
                    "没有配置操作确认器（shared['approver']），出于安全本次调用被拒绝。"
                )
                continue

            # 有 command 参数的工具扫一遍危险模式（对 bash 和未来任何带 command 的工具都生效）
            command = call.arguments.get("command")
            notes = scan_command(str(command)) if command else []

            if not approver.confirm(call.name, call.arguments, notes):
                denied[call.id] = DENIED_TEMPLATE

        shared["denied"] = denied
        return "proceed", payload