"""Day 1：图编排 —— 线性 / 分支 / 循环三件事。

对应的验收脚本是 day1_check.py。这里除了收编它，还补了两条它没覆盖的边界。
"""

from __future__ import annotations

import pytest

import day1_check
from core.node import Flow, Node, shared


# ---------- 收编 day1_check 的三个演示（它们自己带断言） ----------


def test_linear() -> None:
    day1_check.demo_linear()


def test_branch() -> None:
    day1_check.demo_branch()


def test_loop() -> None:
    day1_check.demo_loop()


# ---------- 补的边界：脚本里没覆盖，但框架必须保证 ----------


def test_missing_successor_ends_flow() -> None:
    """返回了一个没注册过的 action → 流程结束，而不是报错卡住。"""
    class WeirdNode(Node):
        def exec(self, payload):
            return "这个 action 没人接", payload

    action, payload = Flow(WeirdNode()).run("x")
    assert (action, payload) == ("这个 action 没人接", "x")


def test_runaway_loop_is_caught() -> None:
    """自己连自己且永远不停 → 框架必须兜底，不能真的转到天荒地老。"""

    class ForeverNode(Node):
        def exec(self, payload):
            return "again", payload + 1

    forever = ForeverNode()
    forever - "again" >> forever

    with pytest.raises(RuntimeError, match="死循环"):
        Flow(forever).run(0)


def test_action_is_reset_after_wiring() -> None:
    """连线用过的 action 必须被重置，否则会污染下一次连线。

    这是 `Node.__rshift__` 里那一行 `self._action = "default"` 的意义：
    没有它，`a - "x" >> b` 之后再写 `a >> c`，c 会被挂到 "x" 上。
    """
    class Leaf(Node):
        def exec(self, payload):
            return "done", payload

    a, b, c = Leaf(), Leaf(), Leaf()
    a - "x" >> b
    a >> c                      # 不指定 action，应该挂到 "default"

    assert set(a.successors) == {"x", "default"}
    assert a.successors["x"] is b
    assert a.successors["default"] is c


def test_shared_is_a_plain_dict() -> None:
    """shared 就是个全局字典 —— 知道它是刻意简化，才不会误以为是依赖注入。"""
    shared.clear()
    shared["k"] = 1
    assert shared["k"] == 1
    shared.clear()
