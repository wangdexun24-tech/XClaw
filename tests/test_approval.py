"""Day 10：操作确认（默认值 / 分类 / 拒绝配对 / 危险检测不越权）。"""

from __future__ import annotations

import approval_check


def test_tool_flags_defaults() -> None:
    approval_check.check_tool_flags()


def test_danger_scan_is_advisory_only() -> None:
    """危险模式扫描只提示、不做决定 —— 这是"没有越权"的证明。"""
    approval_check.check_scan_command()


def test_missing_approver_denies_by_default() -> None:
    """fail-safe：没配置确认器时默认拒绝，而不是默默放行。"""
    approval_check.check_missing_approver()


def test_denied_calls_still_pair_with_tool_messages() -> None:
    """协议铁律：被拒绝的调用也必须产生 tool 消息，否则历史非法。"""
    approval_check.check_pairing_and_execution()


def test_danger_detection_does_not_block_execution() -> None:
    approval_check.check_not_a_permission_system()


def test_approval_is_a_graph_node() -> None:
    """确认是图上的一个节点，不是塞在 ChatNode 里的 if。"""
    approval_check.check_real_flow_wiring()
