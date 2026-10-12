"""Day 7 验收：MCP 必须能"脱离模型"独立工作，并且**不破坏**原有工具。

验收逻辑（每一步都对应一个"如果错了会怎样"）：
  ① 能连上、能列出工具        —— 否则协议握手/传输有问题
  ② 能转成 Tool 且格式合法     —— 否则模型看不到这个工具
  ③ 能注册进 ToolExecutor      —— 否则主循环调用不到它
  ④ 能直接调用并拿到结果       —— 否则执行链路断了
  ⑤ 错误路径不崩、变 is_error  —— 否则一次失败就炸掉整个 agent
  ⑥ 本地 8 个工具依然正常      —— 否则"接入"变成了"替换"
  ⑦ 收尾干净：线程退出、连接关闭 —— 否则反复运行会堆一堆僵尸进程

运行：python mcp_check.py
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import ToolExecutor                        # noqa: E402
from tools.mcp import MCPClient, to_local_tools       # noqa: E402

SERVER = PROJECT_ROOT / "tools" / "mcp" / "server.py"


def fake_call(call_id: str, name: str, arguments: dict):
    """造一个假的 ToolCall（和 tools_check.py 里用的是同一招）。"""
    return type("C", (), {"id": call_id, "name": name, "arguments": arguments})()


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def main() -> None:
    client = MCPClient(command=sys.executable, args=[str(SERVER)], name="xclaw-tools")
    executor = ToolExecutor()          # 8 个内置工具
    builtin_count = len(executor.tools)

    try:
        # ---------- ① 连接 + 列工具 ----------
        section("① 连接 MCP 服务器并列出工具")
        client.start()
        names = client.tool_names()
        print(f"  ✓ 远程工具 {len(names)} 个：{names}")
        assert names, "服务器没有声明任何工具"
        assert "calc" in names, "缺少 calc 工具"

        # ---------- ② 转成 Tool ----------
        section("② 转成本地 Tool 并检查协议格式")
        remote_tools = to_local_tools(client)
        for tool in remote_tools:
            spec = tool.to_llm_format()
            assert spec["type"] == "function"
            assert spec["function"]["name"] == tool.name
            assert spec["function"]["parameters"]["type"] == "object"
            assert spec["function"]["description"].strip(), f"{tool.name} 没有 description"
            print(f"  ✓ {tool.name}: {tool.description.splitlines()[0][:40]}…")

        # ---------- ③ 注册进执行器 ----------
        section("③ 注册进 ToolExecutor")
        executor.register(remote_tools)
        llm_names = [t["function"]["name"] for t in executor.get_llm_tools()]
        print(f"  ✓ 工具总数 {builtin_count} → {len(executor.tools)}")
        assert len(executor.tools) == builtin_count + len(remote_tools)
        for name in names:
            assert name in llm_names, f"{name} 没进模型可见的工具列表"

        # ---------- ④ 直接调用（不经过模型） ----------
        section("④ 直接调用远程工具")
        calc = executor.execute(fake_call("c1", "calc", {"expression": "(128*3+45)/7"}))
        print(f"  ✓ calc: {calc.content}")
        assert not calc.is_error and calc.content.strip() == "61.285714285714285"

        notes = executor.execute(fake_call("c2", "query_notes", {"keyword": "值班"}))
        print(f"  ✓ query_notes: {notes.content[:50]}…")
        assert not notes.is_error and "值班" in notes.content

        info = executor.execute(fake_call("c3", "server_info", {}))
        payload = json.loads(info.content)
        print(f"  ✓ server_info: {payload}")
        # 最关键的一条断言：工具跑在**另一个进程**里
        import os
        assert payload["pid"] != os.getpid(), "MCP 工具居然跑在本进程里？"

        # ---------- ⑤ 错误路径 ----------
        section("⑤ 错误路径（都应 is_error=True，而不是崩）")
        cases = [
            fake_call("e1", "calc", {"expression": "import os"}),      # 远程工具内部抛 ValueError
            fake_call("e2", "no_such_remote_tool", {}),                # 远程工具不存在
            fake_call("e3", "calc", {}),                               # 少了必填参数
        ]
        for call in cases:
            result = executor.execute(call)
            assert result.is_error, f"应该报错：{call.name} {call.arguments}"
            print(f"  ✓ {call.name}({call.arguments}) → {result.content[:60]}")

        # ---------- ⑥ 本地工具没被破坏 ----------
        section("⑥ 本地工具依然正常")
        local = executor.execute(fake_call("l1", "bash", {"command": "echo local-ok"}))
        print(f"  ✓ bash: {local.content.strip().splitlines()[0]}")
        assert "local-ok" in local.content and not local.is_error
        assert "read" in executor.tool_map and "grep" in executor.tool_map

    finally:
        # ---------- ⑦ 收尾 ----------
        section("⑦ 关闭连接")
        threads_before = threading.active_count()
        client.stop()
        client.stop()                      # 幂等性：第二次调用不能报错
        threads_after = threading.active_count()
        print(f"  ✓ 线程数 {threads_before} → {threads_after}")
        assert threads_after <= threads_before, "后台线程没有被回收"

        closed = executor.execute(fake_call("x1", "calc", {"expression": "1+1"}))
        assert closed.is_error, "连接关闭后调用应该失败（并变成 is_error）"
        print(f"  ✓ 关闭后调用：{closed.content[:60]}")

    print("\n✅ Day 7 验收全部通过")


if __name__ == "__main__":
    main()
