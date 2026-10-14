"""Day 4 验收：工具必须能脱离模型独立工作。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tools import ToolExecutor
from tools.builtins import get_builtin_tools


def check_tool_specs() -> None:
    """① 每个工具都符合 LLM 协议格式。"""
    tools = get_builtin_tools()
    print(f"共 {len(tools)} 个工具：{[t.name for t in tools]}\n")

    for tool in tools:
        spec = tool.to_llm_format()
        assert spec["type"] == "function"
        assert {"name", "description", "parameters"} <= set(spec["function"])
        assert spec["function"]["parameters"]["type"] == "object"
        print(f"  ✓ {tool.name}: {tool.description[:40]}…")


def check_direct_execution() -> None:
    """② 直接调用（不经过模型）。"""
    executor = ToolExecutor()
    print("\n--- 直接执行 ---")
    print("ls     :", executor.execute(
        type("C", (), {"id": "c1", "name": "ls", "arguments": {"path": "tools"}})()
    ).content[:80])

    print("read   :", executor.execute(
        type("C", (), {"id": "c2", "name": "read", "arguments": {"path": "core/node.py", "limit": 3}})()
    ).content[:80])

    print("bash   :", executor.execute(
        type("C", (), {"id": "c3", "name": "bash", "arguments": {"command": "echo hello"}})()
    ).content)


def check_error_paths() -> None:
    """③ 错误路径：工具不存在 / 参数缺失 / 文件不存在 —— 都应返回 is_error。"""
    executor = ToolExecutor()
    print("\n--- 错误路径（都应返回 is_error=True，而不是崩）---")
    for call in [
        {"id": "e1", "name": "no_such_tool", "arguments": {}},
        {"id": "e2", "name": "read", "arguments": {}},                      # 缺 path
        {"id": "e3", "name": "read", "arguments": {"path": "nope.txt"}},    # 文件不存在
    ]:
        result = executor.execute(type("C", (), call)())
        assert result.is_error, f"应该报错：{call}"
        print(f"  ✓ {call['name']}: {result.content[:60]}")


def check_parse_and_execute() -> None:
    """④ 模拟模型返回的 tool_calls（arguments 是 JSON 字符串）。"""
    executor = ToolExecutor()
    fake_assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "ls", "arguments": '{"path": "tools"}'}},
            {"id": "call_2", "type": "function",
             "function": {"name": "bash", "arguments": '{"command": "echo 1+1"}'}},
        ],
    }
    calls = executor.parse_tool_calls(fake_assistant)
    results = executor.execute_all(calls)
    print(f"\n--- 解析并执行 {len(calls)} 条模拟调用 ---")
    for result in results:
        print(f"  {result.tool_call_id} → {json.loads(json.dumps(result.to_message(), ensure_ascii=False))['role']}")
        assert result.to_message()["role"] == "tool"
        assert result.to_message()["tool_call_id"].startswith("call_")


def main() -> None:
    check_tool_specs()
    check_direct_execution()
    check_error_paths()
    check_parse_and_execute()


if __name__ == "__main__":
    main()
