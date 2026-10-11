"""执行器：解析模型返回的 tool_calls，执行并把结果规范化为 tool 消息。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .builtins import get_builtin_tools


@dataclass
class ToolCall:
    """一条工具调用（从模型的 assistant message 里解析出来）。"""

    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_openai_item(cls, item: dict[str, Any]) -> "ToolCall":
        function = item.get("function", {}) or {}
        arguments = function.get("arguments", {})

        # ⚠️ 协议里 arguments 是 **JSON 字符串**，要自己解析，且必须容错
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        return cls(id=item.get("id", ""), name=function.get("name", ""), arguments=arguments)


@dataclass
class ToolResult:
    """一条工具执行结果。"""

    tool_call_id: str
    content: str
    is_error: bool = False

    def to_message(self) -> dict[str, str]:
        """转成标准的 tool 消息（role=tool + tool_call_id，Day 3 Q1 讲的规则）。"""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


class ToolExecutor:
    """解析 + 执行。"""

    def __init__(self) -> None:
        self.tools = get_builtin_tools()
        self.tool_map = {tool.name: tool for tool in self.tools}

    def get_llm_tools(self) -> list[dict]:
        """给 call_llm 用的工具列表。"""
        return [tool.to_llm_format() for tool in self.tools]

    def parse_tool_calls(self, assistant_message: dict[str, Any]) -> list[ToolCall]:
        """从 assistant message 里解析所有 tool_calls。"""
        raw_calls = assistant_message.get("tool_calls")
        if not isinstance(raw_calls, list):
            return []
        return [ToolCall.from_openai_item(item) for item in raw_calls]

    def execute(self, call: ToolCall) -> ToolResult:
        """执行一条调用。**永远不抛异常**——失败也变成 ToolResult(is_error=True)。"""
        tool = self.tool_map.get(call.name)
        if tool is None:
            available = "、".join(self.tool_map)
            return ToolResult(
                tool_call_id=call.id,
                content=f"[工具不存在] 没有 {call.name}。可用工具：{available}",
                is_error=True,
            )

        try:
            raw = tool.execute(**call.arguments)
        except Exception as exc:
            return ToolResult(
                tool_call_id=call.id,
                content=f"[工具失败] {call.name}: {type(exc).__name__}: {exc}",
                is_error=True,
            )

        return ToolResult(tool_call_id=call.id, content=_stringify(raw), is_error=False)

    def execute_all(self, calls: list[ToolCall]) -> list[ToolResult]:
        """按顺序执行多条调用（模型可能一次给好几个）。"""
        return [self.execute(call) for call in calls]


def _stringify(value: Any) -> str:
    """统一转成字符串：dict/list 走 JSON，其他直接 str。"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)