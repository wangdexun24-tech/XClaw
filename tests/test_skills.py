"""Day 8：Skill 渐进式加载（扫描 / 容错 / 幂等 / 接入）。"""

from __future__ import annotations

import skill_check


def test_scan() -> None:
    loader = skill_check.check_scan()
    assert len(loader.skills) == 3


def test_progressive_disclosure() -> None:
    """正文（哨兵）不能被提前加载进索引或工具描述 —— 这是这一天存在的理由。"""
    loader = skill_check.check_scan()
    skill_check.check_progressive(loader)


def test_frontmatter_parser_and_tolerance() -> None:
    skill_check.check_frontmatter_parser()


def test_load_and_idempotent() -> None:
    loader = skill_check.check_scan()
    skill_check.check_load_and_idempotent(loader)


def test_tool_contract_and_registry() -> None:
    loader = skill_check.check_scan()
    skill_check.check_tool_contract(loader)
