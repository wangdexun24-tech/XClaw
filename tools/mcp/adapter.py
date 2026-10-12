"""Day 7 · 适配器：把"MCP 工具"翻译成"我们的 Tool"。

## 为什么这一个文件就够了
Day 4 我们给工具定下的契约只有四样东西：
    Tool(name, description, parameters, fn)
而 MCP 的 `tools/list` 恰好能给出前三样：
    MCP 的 name          → Tool.name
    MCP 的 description   → Tool.description
    MCP 的 inputSchema   → Tool.parameters   （本来就是 JSON Schema，格式一样）
于是只差最后一样：fn。而 fn 要干的事就一句话 ——
    "把参数转发给远端，等结果，把结果变成字符串"。

**这就是接口定型的回报**：写完这个文件，
ToolExecutor、ChatNode、ToolCallNode、call_llm 全都一行不用改。
对执行器来说，远程工具和本地 read/bash 没有任何区别。

## 两处容易踩的细节
1. 闭包绑定：`fn` 必须把"工具名"固化在自己身上，
   否则循环里所有工具会共用最后一个名字（经典 Python 闭包坑）。
2. 结果形态：MCP 返回的是**内容块列表**（文本/图片/资源），
   而我们的 ToolResult.content 是**字符串**，需要在这里拍平。
"""

from __future__ import annotations

import json
from typing import Any, Callable

from tools.builtins.tool_def import Tool

from .client import MCPClient


def to_local_tools(client: MCPClient, prefix: str = "") -> list[Tool]:
    """把一条 MCP 连接上的所有远程工具，包装成本地 Tool 列表。

    prefix 用来避免和本地工具重名（例如 prefix="mcp_" → "mcp_calc"）。
    默认不加前缀：先让模型看到干净的名字，重名时再处理。
    """
    return [_to_local_tool(client, raw, prefix) for raw in client.list_tools()]


def _to_local_tool(client: MCPClient, raw: Any, prefix: str) -> Tool:
    remote_name = getattr(raw, "name", "")
    description = (getattr(raw, "description", None) or "").strip()
    return Tool(
        name=f"{prefix}{remote_name}",
        description=description or f"远程工具 {remote_name}",
        parameters=_clean_schema(getattr(raw, "input_schema", None)),
        fn=_make_fn(client, remote_name),
    )


def _make_fn(client: MCPClient, remote_name: str) -> Callable[..., str]:
    """造出 fn：**参数名绑定在闭包上**，这样每个工具各调各的。"""

    def call(**arguments: Any) -> str:
        result = client.call_tool(remote_name, arguments)
        text = result_to_text(result)
        if getattr(result, "is_error", False):
            # 抛异常，交给 ToolExecutor 统一转成 ToolResult(is_error=True)。
            # 不要在这里返回错误字符串 —— 那样模型看不出"这是失败了"。
            raise RuntimeError(text)
        return text

    call.__name__ = f"mcp_{remote_name}"       # 便于调试时看栈
    return call


def result_to_text(result: Any) -> str:
    """把 MCP 的 CallToolResult 拍平成字符串。"""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    if parts:
        return "\n".join(parts)

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False)
    return "(远程工具没有返回任何内容)"


def _clean_schema(schema: Any) -> dict:
    """MCP 的 inputSchema 本来就是 JSON Schema，直接用；只做个空值兜底。"""
    if not isinstance(schema, dict) or not schema:
        return {"type": "object", "properties": {}}
    return schema
