"""Day 11：工程化加固（工作区边界 / 原子写 / 归档 / 中断恢复 / 差异预览）。"""

from __future__ import annotations

import hardening_check


def test_workspace_boundary() -> None:
    """含两个经典绕过：符号链接穿透、前缀相同的兄弟目录。"""
    hardening_check.check_workspace_boundary()


def test_atomic_write() -> None:
    hardening_check.check_atomic_write()


def test_archive_before_compress() -> None:
    hardening_check.check_archive_before_compress()


def test_interrupt_repair() -> None:
    """丢掉半截的一轮，但完整的历史一个字都不能动。"""
    hardening_check.check_interrupt_repair()


def test_diff_preview() -> None:
    hardening_check.check_preview()
