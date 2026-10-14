"""Day 4 + Day 10 + Day 11：工具层。

收编 tools_check.py，并补上"每个工具都必须声明确认策略"这条不变量。
"""

from __future__ import annotations

import tools_check
from tools.builtins import get_builtin_tools

READ_ONLY_TOOLS = {"read", "ls", "grep", "find"}
WRITE_TOOLS = {"write", "edit", "bash", "search"}


def test_tool_specs() -> None:
    tools_check.check_tool_specs()


def test_direct_execution() -> None:
    tools_check.check_direct_execution()


def test_error_paths() -> None:
    tools_check.check_error_paths()


def test_parse_and_execute() -> None:
    tools_check.check_parse_and_execute()


# ---------- 补的不变量 ----------


def test_every_tool_declares_approval_policy() -> None:
    """Day 10 之后：每个工具都必须显式表明"要不要问用户"，且分类正确。"""
    tools = {tool.name: tool for tool in get_builtin_tools()}
    assert set(tools) == READ_ONLY_TOOLS | WRITE_TOOLS

    for name in READ_ONLY_TOOLS:
        assert tools[name].requires_approval is False, f"{name} 是纯读工具，不该打扰用户"
    for name in WRITE_TOOLS:
        assert tools[name].requires_approval is True, f"{name} 会改状态，必须确认"


def test_tool_requires_approval_defaults_to_true() -> None:
    """fail-safe：忘了声明的工具，默认要多问一句。"""
    from tools.builtins import Tool

    bare = Tool(name="t", description="d", parameters={"type": "object"}, fn=lambda: "x")
    assert bare.requires_approval is True


def test_only_edit_provides_preview() -> None:
    """Day 11：预览由工具自己提供，目前只有 edit 有。"""
    tools = {tool.name: tool for tool in get_builtin_tools()}
    assert tools["edit"].build_preview({"old_text": "a", "new_text": "b"}) is not None
    assert tools["bash"].build_preview({"command": "ls"}) is None
    assert tools["read"].build_preview({"path": "x"}) is None
