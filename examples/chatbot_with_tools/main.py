"""Agent 示例：把工具接进对话循环。

    ChatNode ──"tool_call"──▶ ToolCallNode
        ▲                          │
        └──────────"chat"──────────┘

ChatNode 调模型：有 tool_calls 就走到 ToolCallNode；没有就结束。
ToolCallNode 执行工具后回到 ChatNode —— 形成 agent 主循环。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.llm import call_llm              # noqa: E402
from core.node import Flow, Node, shared   # noqa: E402
from tools import ToolExecutor             # noqa: E402

MAX_TOOL_ROUNDS = 8          # 一轮提问里，最多允许"模型↔工具"循环几次
TOOL_PREVIEW = 300           # 打印工具结果时的截断长度

SYSTEM_PROMPT = """你是一个会使用工具的助手。

## 工具使用原则
1. 涉及本项目里的文件、代码、配置时，必须**先调用工具查看**，不要凭猜测回答。
2. 不了解项目结构时先用 ls；定位"某个函数/变量在哪个文件"时用 grep。
3. **修改已有文件前，必须先用 read 读取原文**（edit 要求原文逐字符一致）。
4. 需要运行脚本、跑测试、查看环境时用 bash。
5. 涉及外部最新信息、第三方库用法、报错原因时可以用 search。

## 回答要求
- 用简洁的中文回答；说明你调用了哪些工具、看到了什么。
- 一轮回复里可以同时给出文字和 tool_calls。
"""

class ChatNode(Node):
    """调模型，并根据是否返回 tool_calls 决定下一步。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        messages = shared["messages"]

        assistant_message = call_llm(
            messages=messages,
            tools=shared["tools"],
            system_prompt=SYSTEM_PROMPT,
        )
        # ⚠️ 关键：先把 assistant 消息写进历史（含 tool_calls），再去执行工具
        messages.append(assistant_message)

        content = assistant_message.get("content") or ""
        if content:
            print(f"\n🤖 助手：{content}")

        tool_calls = assistant_message.get("tool_calls")
        if not tool_calls:
            return "done", assistant_message        # 没有后继 → Flow 结束

        # 防止模型无限调工具
        round_index = shared.get("tool_round", 0) + 1
        shared["tool_round"] = round_index
        if round_index > MAX_TOOL_ROUNDS:
            print(f"\n⚠️ 已达到最大工具轮数 {MAX_TOOL_ROUNDS}，停止调用工具")
            return "done", assistant_message

        return "tool_call", assistant_message       # 有工具要执行 → 走另一条边

class ToolCallNode(Node):
    """执行模型请求的工具，并把结果作为 tool 消息写回历史。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        assistant_message = payload
        messages = shared["messages"]
        executor: ToolExecutor = shared["tool_executor"]

        tool_calls = executor.parse_tool_calls(assistant_message)
        results = executor.execute_all(tool_calls)

        for call, result in zip(tool_calls, results):
            preview = result.content[:TOOL_PREVIEW].replace("\n", " ")
            mark = "✗" if result.is_error else "✓"
            print(f"  [工具 {mark}] {call.name}({call.arguments})")
            print(f"           → {preview}")

            # 每条 tool_call 对应一条 tool 消息，靠 tool_call_id 配对
            messages.append(result.to_message())

        return "chat", None        # ← 回到 ChatNode，这就是"环"

def build_flow() -> Flow:
    """构建图（只做一次）。"""
    chat, tool_call = ChatNode(), ToolCallNode()

    chat - "tool_call" >> tool_call     # 有工具要执行 → 去执行
    tool_call - "chat" >> chat          # 执行完 → 回到模型 ← 环在这里闭合

    return Flow(chat)


def run_chat() -> None:
    print("=" * 60)
    print("🤖 XClaw Agent（带工具的对话）")
    print("=" * 60)
    print("输入 exit / quit 退出，/clear 清空对话历史\n")

    # 初始化共享状态（每个示例开头都要做的事）
    shared.clear()
    shared["messages"] = []
    executor = ToolExecutor()
    shared["tool_executor"] = executor
    shared["tools"] = executor.get_llm_tools()      # 8 个工具的协议描述

    tool_names = [t["function"]["name"] for t in shared["tools"]]
    print(f"可用工具：{', '.join(tool_names)}")

    flow = build_flow()                             # 图只构建一次

    while True:
        try:
            user_input = input("👤 你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if user_input.lower() in {"exit", "quit"}:
            print("再见！")
            break
        if user_input == "/clear":
            shared["messages"] = []
            print("[已清空对话历史]\n")
            continue
        if not user_input:
            continue

        shared["messages"].append({"role": "user", "content": user_input})
        shared["tool_round"] = 0            # ← 每轮提问重置计数器（重要）
        flow.run(None)                      # 一环一环跑到没有后继


def main() -> None:
    run_chat()


if __name__ == "__main__":
    main()