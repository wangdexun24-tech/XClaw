"""Day 7 示例：让 agent 同时拥有"本地工具"和"MCP 远程工具"。

和 Day 5 的 chatbot_with_tools 相比，本文件只多了 4 行有效代码：
    启动 MCP 客户端 → 把远程工具转成本地 Tool → 注册进执行器 → 用完关掉连接

这正说明 MCP 的接入成本有多低 —— 主循环、执行器、模型调用全都没动。

运行：
    python -m examples.chatbot_with_mcp.main
可以试着问：
    这个远程服务器跑在什么目录下？
    帮我算一下 (128*3+45)/7
    团队知识库里关于值班的约定是什么？
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from examples.chatbot_with_tools.main import run_chat   # noqa: E402
from tools.mcp import MCPClient, to_local_tools         # noqa: E402


def main() -> None:
    server = PROJECT_ROOT / "tools" / "mcp" / "server.py"

    # 用 sys.executable 而不是写死 "python"：保证子进程和当前虚拟环境是同一个解释器
    with MCPClient(command=sys.executable, args=[str(server)], name="xclaw-tools") as client:
        # requires_approval=False：这是我们自己写的本地 demo server，工具都是只读的。
        # 接**第三方** MCP 服务器时请保持默认（True）—— 那里的代码不是我们控制的。
        remote_tools = to_local_tools(client, requires_approval=False)
        print(f"[mcp] 已连接 MCP 服务器，拿到 {len(remote_tools)} 个远程工具："
              f"{', '.join(client.tool_names())}")
        # 远程工具从 extra_tools 这个口子进去，和 8 个本地工具平起平坐
        run_chat(extra_tools=remote_tools)
        # with 退出时自动 client.stop()：子进程被回收，不留孤儿


if __name__ == "__main__":
    main()
