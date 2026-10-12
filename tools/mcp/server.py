"""Day 7 · 一个最小的 MCP 服务器：把"工具"放到独立进程里跑。

## 为什么要有 MCP
Day 4 的工具都是**函数调用**：read/bash 就在本进程里。
但现实中的工具常常不在本进程里：
    - 另一个进程（用 stdio 通信，就是本文件）
    - 另一台机器 / 另一个服务（用 HTTP / SSE 通信）
如果每接一个外部工具都要改 agent 的代码，agent 就没法扩展了。
MCP（Model Context Protocol）就是给这件事定的**标准协议**。

## 协议本身只有两件事
1. **说什么**：JSON-RPC 2.0。客户端发 {"method": "tools/list"}，服务器回工具列表；
   客户端发 {"method": "tools/call", "params": {"name": ..., "arguments": ...}}，
   服务器回结果。
2. **怎么运**：transport。stdio（本文件）就是把 JSON 一行一行写进子进程的标准输入。

两者是解耦的 —— 换成 HTTP 时，"说什么"完全不变，这就是协议的价值。

## 这个文件只干一件事
把普通 Python 函数注册成 MCP 工具：
    @mcp.tool()  ← 装饰器会读函数的 **函数名 + 类型注解 + docstring**，
                    自动生成 JSON Schema。
这跟我们 Day 4 手写的 Tool(name, description, parameters, fn) 是同一回事，
只是这次 Schema 由框架自动推导。

## ⚠️ 一条容易被忽视的铁律
stdio 模式下，**stdout 是 RPC 通道**，只能用来传协议 JSON。
任何 print() 都会污染协议、让客户端解析失败。
要打日志请用 print(..., file=sys.stderr)。
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("xclaw-tools")

# 假装这是一个"外部系统"里的数据 —— 它不在 agent 的工作目录里，
# agent 用 read/grep 是找不到它的，只能通过 MCP 工具访问。
NOTES: dict[str, str] = {
    "deploy": "发布流程：先跑 pytest，再打 tag，最后 push tag 触发流水线。",
    "oncall": "值班轮换：每周一早 10 点交接；报警先看 Grafana 再看日志。",
    "style": "代码规范：函数不超过 50 行；提交信息用 feat/fix/docs 前缀。",
    "db": "数据库：测试库每天 03:00 重置；不要在生产库上跑 UPDATE。",
}


@mcp.tool()
def server_info() -> dict:
    """返回 MCP 服务器自身的信息（Python 版本、操作系统、工作目录、进程号）。

    用它来验证一件事：**这个工具是跑在另一个进程里的**。
    """
    return {
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "cwd": str(Path.cwd()),
        "pid": __import__("os").getpid(),
    }


@mcp.tool()
def calc(expression: str) -> str:
    """计算一个数学表达式，例如 "12 * (3 + 4)"。

    只允许数字和 + - * / ( ) . 空格，不允许变量或函数调用。
    """
    allowed = set("0123456789+-*/(). ")
    if not expression or set(expression) - allowed:
        raise ValueError(f"表达式只允许数字和 + - * / ( ) . ：{expression!r}")
    # ⚠️ eval 很危险，所以先做了字符白名单。
    # （真实项目里更稳妥的做法是用 ast 解析后只放行算术节点）
    return str(eval(expression, {"__builtins__": {}}, {}))


@mcp.tool()
def query_notes(keyword: str) -> str:
    """在团队知识库里按关键词查询（模拟一个 agent 访问不到的外部数据源）。

    关键词支持中文/英文，会做子串匹配；没命中时返回所有条目的标题。
    """
    keyword = (keyword or "").strip().lower()
    hits = [
        f"[{key}] {value}"
        for key, value in NOTES.items()
        if not keyword or keyword in key or keyword in value.lower()
    ]
    if hits:
        return "\n".join(hits)
    return "没有命中，可选条目：" + "、".join(NOTES)


if __name__ == "__main__":
    # transport="stdio"：用标准输入/输出跟客户端说话。
    # 换成 mcp.run(transport="http", port=8000) 就能变成网络服务，
    # 客户端的代码几乎不用改 —— 这就是 transport 解耦的收益。
    mcp.run(transport="stdio")
