"""Day 7 · MCP：把"跑在别的进程/别的机器上的工具"接进同一套 Tool 接口。

三个文件，各管一件事：
    server.py   MCP 服务器：把普通 Python 函数注册成"远程工具"
    client.py   MCP 客户端：负责连接、握手、调用、善后（把 async 包成 sync）
    adapter.py  适配器：把 MCP 工具翻译成本地的 Tool 对象
"""

from .adapter import to_local_tools
from .client import MCPClient

__all__ = ["MCPClient", "to_local_tools"]
