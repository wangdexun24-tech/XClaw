"""Chatbot 示例：把 workflow 包进循环，并累积对话历史。

    ChatNode ──"output"──▶ OutputNode

和 workflow 的唯一区别：**多了一份共享的对话历史**（shared["messages"]）。
每轮把"用户消息"和"助手回复"都追加进去——这就是"记得上一轮"的全部秘密。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.llm import call_llm            # noqa: E402
from core.node import Flow, Node, shared  # noqa: E402

SYSTEM_PROMPT = (
    "你是一个友好的对话助手。回答要简洁；"
    "如果用户问你之前说过什么，请根据对话历史如实回答。"
)

class ChatNode(Node):
    """调模型：把整段历史发过去，并把模型的回复也追加进历史。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        messages = shared["messages"]
        assistant_message = call_llm(messages=messages, system_prompt=SYSTEM_PROMPT)
        messages.append(assistant_message)          # ← 关键：助手回复也要记下来
        return "output", assistant_message

class OutputNode(Node):
    """只负责显示。以后换流式输出，只改这一个节点。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        content = payload.get("content", "")
        usage = payload.get("usage") or {}
        print(f"\n🤖 助手：{content}")
        if usage:
            print(
                f"   [tokens] 本轮上下文 {usage.get('total_tokens')} "
                f"(prompt {usage.get('prompt_tokens')} + completion {usage.get('completion_tokens')})\n"
            )
        return "default", None

def build_flow() -> Flow:
    """构建图 —— 只做一次（呼应昨天 Q2：构建和执行分离）。"""
    chat, output = ChatNode(), OutputNode()
    chat - "output" >> output
    return Flow(chat)

def run_chat() -> None:
    print("=" * 60)
    print("🤖 XClaw Chatbot")
    print("=" * 60)
    print("输入 exit / quit 退出，/clear 清空对话历史\n")

    shared.clear()                      # ← 每个示例开头都要清，避免和别的示例串味
    shared["messages"] = []

    flow = build_flow()                 # 图只构建一次，循环里反复 run

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
            print("[已清空对话历史]")
            print("[下一句话它会忘记之前的一切——这正好能验证记忆来自哪里]\n")
            continue

        if not user_input:
            continue

        shared["messages"].append({"role": "user", "content": user_input})
        flow.run(None)


def main() -> None:
    run_chat()


if __name__ == "__main__":
    main()

