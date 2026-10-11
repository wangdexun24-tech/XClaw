"""Day 1 验收：证明这套编排能做 线性 / 分支 / 循环 三件事。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.node import Flow, Node


class DoubleNode(Node):
    """把数字翻倍。"""

    def exec(self, payload):
        result = payload * 2
        print(f"  DoubleNode: {payload} -> {result}")
        return "default", result


class AddNode(Node):
    """加上一个固定值。"""

    def __init__(self, amount: int, **kwargs):
        super().__init__(**kwargs)
        self.amount = amount

    def exec(self, payload):
        result = payload + self.amount
        print(f"  AddNode: {payload} + {self.amount} -> {result}")
        return "default", result


class PrintNode(Node):
    """打印结果并结束（没有后继节点，Flow 自然停止）。"""

    def exec(self, payload):
        print(f"  PrintNode 输出: {payload}")
        return "done", payload


class BranchNode(Node):
    """按数值大小选路 —— 这就是"分支"。"""

    def exec(self, payload):
        action = "big" if payload >= 10 else "small"
        print(f"  BranchNode: {payload} -> 走 {action}")
        return action, payload


class CountNode(Node):
    """自增并回环 —— 这就是"循环"，也是 agent 主循环的雏形。"""

    def exec(self, payload):
        payload += 1
        print(f"  CountNode: 计数 {payload}")
        return ("continue" if payload < 3 else "stop"), payload


def demo_linear() -> None:
    print("\n=== ① 线性：Double -> Add(3) -> Print ===")
    double, add, show = DoubleNode(), AddNode(3), PrintNode()
    double >> add >> show           # 链式连接
    Flow(double).run(5)


def demo_branch() -> None:
    print("\n=== ② 分支：Branch 按数值选路 ===")
    branch, big, small = BranchNode(), PrintNode(), PrintNode()
    branch - "big" >> big
    branch - "small" >> small

    Flow(branch).run(12)
    Flow(branch).run(3)


def demo_loop() -> None:
    print("\n=== ③ 循环：Count 自增到 3 才停 ===")
    count, finish = CountNode(), PrintNode()
    count - "continue" >> count      # 环回自己
    count - "stop" >> finish
    Flow(count).run(0)


if __name__ == "__main__":
    demo_linear()
    demo_branch()
    demo_loop()