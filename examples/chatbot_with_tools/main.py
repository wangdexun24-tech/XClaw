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

from core.memory import Memory
from core.llm import call_llm              # noqa: E402
from core.node import Flow, Node, shared   # noqa: E402
from tools import ToolExecutor             # noqa: E402
from tools.builtins import Tool            # noqa: E402

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
        memory: Memory = shared["memory"]

        assistant_message = call_llm(
            messages=memory.build_context(SYSTEM_PROMPT),   # ← system + 长期记忆 + 历史
            tools=shared["tools"],
        )
        # usage 要在 append 之前取：append 会把它过滤掉（它是给程序看的元数据）
        usage = assistant_message.get("usage") or {}
        saved = memory.append(assistant_message)             # ← 落盘 + 字段过滤

        content = saved.get("content") or ""
        if content:
            print(f"\n🤖 助手：{content}")

        tool_calls = saved.get("tool_calls")
        if not tool_calls:
            # 一轮结束了：这时才检查要不要压缩（在工具轮中间压缩会拆散配对）
            memory.maybe_compress(usage.get("total_tokens", 0))
            return "done", saved                    # 没有后继 → Flow 结束

        # 防止模型无限调工具
        round_index = shared.get("tool_round", 0) + 1
        shared["tool_round"] = round_index
        if round_index > MAX_TOOL_ROUNDS:
            print(f"\n⚠️ 已达到最大工具轮数 {MAX_TOOL_ROUNDS}，停止调用工具")
            return "done", saved

        return "tool_call", saved                   # 有工具要执行 → 走另一条边

class ToolCallNode(Node):
    """执行模型请求的工具，并把结果作为 tool 消息写回历史。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        assistant_message = payload
        memory: Memory = shared["memory"]
        executor: ToolExecutor = shared["tool_executor"]

        tool_calls = executor.parse_tool_calls(assistant_message)
        results = executor.execute_all(tool_calls)

        for call, result in zip(tool_calls, results):
            preview = result.content[:TOOL_PREVIEW].replace("\n", " ")
            mark = "✗" if result.is_error else "✓"
            print(f"  [工具 {mark}] {call.name}({call.arguments})")
            print(f"           → {preview}")

            # 每条 tool_call 对应一条 tool 消息，靠 tool_call_id 配对
            memory.append(result.to_message())          # ← 落盘

        return "chat", None        # ← 回到 ChatNode，这就是"环"

def build_flow() -> Flow:
    """构建图（只做一次）。"""
    chat, tool_call = ChatNode(), ToolCallNode()

    chat - "tool_call" >> tool_call     # 有工具要执行 → 去执行
    tool_call - "chat" >> chat          # 执行完 → 回到模型 ← 环在这里闭合

    return Flow(chat)


def run_chat(extra_tools: list[Tool] | None = None) -> None:
    """启动对话。

    extra_tools：额外注册的工具（Day 7 的 MCP 远程工具就从这个口子进来）。
    —— 注意主循环（ChatNode / ToolCallNode / build_flow）这三块**一行都没改**。
    """
    print("=" * 60)
    print("🤖 XClaw Agent（带工具的对话）")
    print("=" * 60)
    print("输入 exit / quit 退出；/clear 清空对话记忆；/remember <内容> 记住一件事\n")

    # 初始化共享状态（每个示例开头都要做的事）
    shared.clear()
    executor = ToolExecutor()
    if extra_tools:
        names = executor.register(extra_tools)
        print(f"[外部工具] 已注册 {len(names)} 个：{', '.join(names)}")
    shared["tool_executor"] = executor
    shared["tools"] = executor.get_llm_tools()      # 所有工具的协议描述

    # 记忆：会自动读回上次的对话
    memory = Memory(PROJECT_ROOT / "chat_memory")
    shared["memory"] = memory
    if memory.messages:
        print(f"[memory] 已恢复上次对话：{len(memory.messages)} 条消息")
    else:
        print("[memory] 这是新的对话")

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
            shared["memory"].clear()
            print("[已清空对话记忆（长期记忆保留）]\n")
            continue
        if user_input.startswith("/remember "):
            fact = user_input[len("/remember "):]
            shared["memory"].remember(fact)
            print(f"[已记住] {fact.strip()}\n")
            continue
        if not user_input:
            continue

        shared["memory"].append({"role": "user", "content": user_input})
        shared["tool_round"] = 0            # ← 每轮提问重置计数器（重要）
        flow.run(None)                      # 一环一环跑到没有后继


def main() -> None:
    run_chat()


if __name__ == "__main__":
    main()
