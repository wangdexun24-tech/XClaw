"""Day 9：长任务模式（加载校验 / 判据 / 重试证据 / 预算 / 内环重置）。"""

from __future__ import annotations

import goal_check


def test_loading_and_validation() -> None:
    goal_check.check_loading()


def test_frontmatter_list_syntax() -> None:
    goal_check.check_frontmatter()


def test_run_checks() -> None:
    goal_check.check_run_checks()


def test_retry_message_carries_evidence() -> None:
    goal_check.check_retry_message()


def test_gives_up_when_budget_exhausted() -> None:
    """预算护栏：不许无限重试。"""
    goal_check.check_give_up()


def test_stops_right_after_passing() -> None:
    """判据通过就立刻结束，不再多烧一次模型调用。"""
    goal_check.check_passed()


def test_inner_budget_is_reset_between_attempts() -> None:
    """重试时必须给内环重新发牌，否则内外环会空转。"""
    goal_check.check_inner_budget_reset()
