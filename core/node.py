"""轻框架核心：节点 + 编排。

一句话：Node 负责"做什么"，successors 负责"下一步去哪"。

用法：
    class MyNode(Node):
        def exec(self, payload):
            ...
            return "action_name", next_payload

    a - "action_name" >> b     # a 返回这个 action 时，转向 b
    Flow(a).run(初始输入)      # 从 a 开始，沿连线一直跑到没有后继
"""

from __future__ import annotations

import time
from typing import Any

# 全局状态：**教学简化**，方便示例之间共享 messages / tools
# 生产项目里应该用依赖注入或显式传参（README 里要诚实标注这一点）
shared: dict[str, Any] = {}

class Node:
    """一个处理单元。

    子类只需要实现 exec(payload) -> (action, 下一份 payload)；
    重试这类通用逻辑由基类统一处理。
    """

    def __init__(self, max_retries: int = 1, wait: float = 0) -> None:  #每个节点不等待不重试
        self.successors: dict[str, "Node"] = {}      # action -> 下一个节点
        self._action: str = "default"                # 下一次连线用哪个 action
        self.max_retries = max_retries
        self.wait = wait

    #payload:输入数据
    def exec(self, payload: Any) -> tuple[str, Any]:
        """子类实现：处理输入，返回 (下一步的 action, 传给下一步的数据)。"""
        raise NotImplementedError

    def _exec(self, payload: Any) -> tuple[str, Any]:
        """带重试的执行入口（Flow 调用的就是它）。"""
        for attempt in range(self.max_retries):
            try:
                return self.exec(payload)
            except Exception:
                if attempt == self.max_retries - 1:
                    raise
                if self.wait > 0:
                    time.sleep(self.wait)
        raise RuntimeError("unreachable")

    def __rshift__(self, other: "Node") -> "Node":
        """a >> b：把 a 当前 action 的后继设为 b，并返回 b（支持链式 a >> b >> c）。"""
        self.successors[self._action] = other
        self._action = "default"        # 用完重置，否则会污染下一次连线
        return other

    def __sub__(self, action: str) -> "Node":
        """a - "search" >> b：指定这次连线用哪个 action。"""
        if not isinstance(action, str):
            raise TypeError("action 必须是字符串")
        self._action = action or "default"
        return self

class Flow:
    """编排器：从 start 开始，按节点返回的 action 决定下一步。"""

    def __init__(self, start: Node | None = None) -> None:
        self.start = start

    def run(self, payload: Any = None) -> tuple[str | None, Any]:
        current = self.start
        action: str | None = "default"
        steps = 0

        while current is not None:
            steps += 1
            if steps > 1000:          # 死循环兜底（画错连线时会救你一命）
                raise RuntimeError("Flow 步数超过 1000，可能连成了死循环")

            print(f"[flow] 第 {steps} 步：{type(current).__name__}  输入={payload!r}")
            action, payload = current._exec(payload)
            print(f"[flow]          → action={action!r}")

            current = current.successors.get(action)

        return action, payload