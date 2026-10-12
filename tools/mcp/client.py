"""Day 7 · MCP 客户端：把"异步的 MCP"包装成同步的普通函数。

## 为什么需要一个包装类
MCP 官方客户端是 `async` 的（`async with` / `await`），
而我们的 agent（Day 5/6 的主循环）是**同步**的。
不解决这个错配，Day 4 定下的 `Tool.fn(**kwargs)` 契约就没法接 MCP 工具。

## 三个必须处理的现实问题
1. **异步 ↔ 同步**：需要一座桥（后台线程 + 事件循环）。
2. **连接要复用**：`tools/list` 只取一次，`tools/call` 调用很多次。
   如果每次调用都重启子进程，一次对话会慢好几秒。
   → 所以连接**长驻**：start() 时连上，stop() 时才断开。
3. **退出要干净**：子进程 + 事件循环 + anyio 的 cancel scope，
   **enter 和 exit 必须在同一个任务（task）里**，否则退出时会抛
   `RuntimeError: Attempted to exit cancel scope in a different task`。
   → 所以下面 `_serve()` 是"自己开、自己关"的一个长驻任务，
     外部只通过 asyncio.run_coroutine_threadsafe 把调用"投递"进去。

## 一张图
    主线程（同步）                          后台线程（一个 event loop）
    ─────────────                          ──────────────────────────
    client.start()  ──── 启动 ─────▶  _serve(): 连服务器 → list_tools → 等 stop()
    client.call_tool(...) ─ 投递 ──▶  await session.call_tool(...)
    client.stop()   ─── 通知 ─────▶  _serve() 走出 async with，子进程被关掉
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Sequence

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

START_TIMEOUT = 30.0      # 启动 + 握手最多等多久
CALL_TIMEOUT = 60.0       # 单次工具调用最多等多久


class MCPClient:
    """一条可复用的 MCP 连接（同步 API）。

    用法：
        with MCPClient(command="python", args=["tools/mcp/server.py"]) as client:
            tools = client.list_tools()                     # [mcp.types.Tool, ...]
            result = client.call_tool("calc", {"expression": "1+1"})
    """

    def __init__(
        self,
        command: str,
        args: Sequence[str] = (),
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        name: str = "mcp",
        show_server_log: bool = False,
    ) -> None:
        self.name = name
        # 服务器进程的 stderr（比如 fastmcp 的启动横幅和它自己的报错）。
        # 默认丢掉：它会把 CLI 的输出冲得乱七八糟。调试协议问题时打开它。
        self.show_server_log = show_server_log
        # StdioServerParameters 描述"怎么把服务器拉起来"。
        # env 要基于当前环境再叠加，否则子进程可能找不到 PATH 之类的东西。
        merged_env = {**os.environ, **(env or {})}
        self.server = StdioServerParameters(
            command=command,
            args=[str(item) for item in args],
            env=merged_env or None,
            cwd=str(cwd) if cwd else None,
        )

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._session: ClientSession | None = None
        self._raw_tools: list[Any] = []
        self._ready = threading.Event()
        self._error: BaseException | None = None

    # ---------- 生命周期 ----------

    def start(self) -> "MCPClient":
        """连接服务器并取回工具列表。失败会抛异常（而不是默默装死）。"""
        if self._thread is not None:
            return self

        self._thread = threading.Thread(
            target=self._run_loop, name=f"mcp-{self.name}", daemon=True
        )
        self._thread.start()

        if not self._ready.wait(START_TIMEOUT):
            raise TimeoutError(f"MCP 服务器 {self.name} 启动超时（{START_TIMEOUT}s）")
        if self._error is not None:
            raise RuntimeError(
                f"MCP 服务器 {self.name} 启动失败：{self._error!r}"
            ) from self._error
        return self

    def stop(self) -> None:
        """关闭连接、结束子进程、回收线程。幂等：调两次也没事。"""
        loop, thread, event = self._loop, self._thread, self._stop_event
        if loop is not None and event is not None:
            try:
                # 只是"通知"事件循环去设置事件，实际执行仍在那个任务里 —— 保持同任务语义
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass
        if thread is not None:
            thread.join(timeout=START_TIMEOUT)
            if thread.is_alive():
                print(f"[mcp] 警告：{self.name} 后台线程没有按时退出")

        self._thread = None
        self._loop = None
        self._stop_event = None
        self._session = None

    def __enter__(self) -> "MCPClient":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    # ---------- 后台线程：跑一个 event loop ----------

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            # 注意用的是 run_until_complete(_serve())：整条生命线都在**同一个任务**里，
            # 这样 async with 的进入和退出天然配对（第 3 个现实问题就靠这一行解决）
            loop.run_until_complete(self._serve())
        except BaseException as exc:          # noqa: BLE001 —— 桥接线程里必须兜住一切
            self._error = self._error or exc
            self._ready.set()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    async def _serve(self) -> None:
        """长驻任务：连接 → 握手 → 取工具列表 → 挂起等 stop() → 退出连接。"""
        try:
            async with AsyncExitStack() as stack:
                # stdio_client 负责"拉起子进程 + 把标准输入输出当成传输通道"
                errlog = sys.stderr if self.show_server_log else subprocess.DEVNULL
                read, write = await stack.enter_async_context(
                    stdio_client(self.server, errlog=errlog)  # type: ignore[arg-type]
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()          # 协议握手（交换版本/能力）
                listed = await session.list_tools()  # 这就是 tools/list 请求

                self._session = session
                self._raw_tools = list(listed.tools)
                self._stop_event = asyncio.Event()
                self._ready.set()                    # 告诉主线程：可以用了

                await self._stop_event.wait()        # 一直挂着，直到 stop()
            # 走出 async with：子进程被关掉，连接被清理
        except BaseException as exc:                 # noqa: BLE001
            self._error = self._error or exc
            self._ready.set()

    # ---------- 同步 API ----------

    def list_tools(self) -> list[Any]:
        """返回服务器声明的工具列表（mcp.types.Tool 对象）。"""
        if self._session is None:
            raise RuntimeError("MCP 连接未启动，请先调用 start()")
        return list(self._raw_tools)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用一个远程工具，返回原始 CallToolResult（翻译成字符串是 adapter 的活）。"""
        if self._loop is None or self._session is None:
            raise RuntimeError("MCP 连接未启动，请先调用 start()")
        # 把协程投递到后台 loop 执行，再阻塞等结果 —— 这就是"异步转同步"的全部
        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments or {}), self._loop
        )
        return future.result(timeout=CALL_TIMEOUT)

    def tool_names(self) -> list[str]:
        """方便打印的辅助方法。"""
        return [getattr(tool, "name", "?") for tool in self.list_tools()]
