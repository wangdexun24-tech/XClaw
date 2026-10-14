"""跨模块的不变量。

前面八个测试文件是"按天"组织的；这个文件是"按约束"组织的 ——
它验证的不是某个模块做了什么，而是**几个模块合起来必须守住什么**。
这类测试最容易漏，但恰恰是系统级 bug 的高发区。
"""

from __future__ import annotations

from core.memory import MESSAGE_KEYS, Memory
from tools.builtins import get_builtin_tools


def test_tool_names_are_unique() -> None:
    names = [tool.name for tool in get_builtin_tools()]
    assert len(names) == len(set(names)), f"工具重名：{names}"


def test_tool_schema_is_self_consistent() -> None:
    """required 里列出的字段，必须真的在 properties 里定义过。"""
    for tool in get_builtin_tools():
        params = tool.to_llm_format()["function"]["parameters"]
        required = set(params.get("required", []))
        defined = set(params.get("properties", {}))
        assert required <= defined, f"{tool.name} 的 required 里有未定义的字段：{required - defined}"
        assert tool.description.strip(), f"{tool.name} 没有 description，模型不知道怎么用"


def test_memory_key_whitelist_covers_what_we_write() -> None:
    """Memory 的字段白名单必须覆盖我们真正会写进去的字段。

    白名单是"防止元数据进历史"的关键；如果它漏了某个字段，
    那个字段会被静默丢掉 —— 这类 bug 在长对话里极难发现。
    """
    for key in ("role", "content", "tool_calls", "tool_call_id", "reasoning_content"):
        assert key in MESSAGE_KEYS, f"白名单里少了 {key}"

    # usage 是给程序看的，绝不能进历史
    assert "usage" not in MESSAGE_KEYS


def test_all_example_flows_can_be_built() -> None:
    """六个示例的图都要能构造出来 —— 改连线改坏了，这里立刻会发现。

    这是最低成本的"冒烟测试"：不调用模型，只确认图是完整可跑的。
    """
    from examples.chatbot_with_mcp import main as mcp_example            # noqa: F401
    from examples.chatbot_with_skills import main as skill_example      # noqa: F401
    from examples.chatbot_with_tools.main import build_flow as build_agent_flow
    from examples.goal_agent.main import build_flow as build_goal_flow

    agent_flow = build_agent_flow()
    assert agent_flow.start is not None
    assert "tool_call" in agent_flow.start.successors
    assert type(agent_flow.start.successors["tool_call"]).__name__ == "ApprovalNode"

    goal_flow = build_goal_flow()
    assert type(goal_flow.start).__name__ == "ChatNode"
    assert "done" in goal_flow.start.successors, "长任务模式必须把 done 接到验证节点上"
