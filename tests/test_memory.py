"""Day 6 + Day 11：记忆 —— 落盘 / 恢复 / 压缩 / 归档 / 自愈。"""

from __future__ import annotations

import memory_check


def test_field_filtering() -> None:
    memory_check.check_field_filtering()


def test_crash_recovery() -> None:
    memory_check.check_crash_recovery()


def test_compression_boundary() -> None:
    memory_check.check_compression_boundary()


def test_long_term_memory() -> None:
    memory_check.check_long_term_memory()


# ---------- 补：Day 11 的归档与自愈 ----------


def test_archive_is_written_before_compression() -> None:
    """归档必须是**压缩之前**的完整历史。"""
    import tempfile
    from pathlib import Path

    from core.memory import Memory

    directory = Path(tempfile.mkdtemp()) / "mem"
    memory = Memory(directory)
    for index in range(20):
        memory.append({"role": "user", "content": f"第 {index} 条"})
    before = len(memory.messages)

    memory._summarize = lambda messages: "摘要"      # type: ignore[method-assign]
    assert memory.maybe_compress(10 ** 9) is True

    archives = sorted((directory / "archive").glob("*.jsonl"))
    assert len(archives) == 1
    lines = archives[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == before
    assert "第 0 条" in lines[0]


def test_archive_failure_keeps_history_intact() -> None:
    """归档失败就放弃压缩 —— 宁可多占上下文，也不丢原始记录。"""
    import tempfile
    from pathlib import Path

    from core.memory import Memory

    directory = Path(tempfile.mkdtemp()) / "mem"
    memory = Memory(directory)
    for index in range(20):
        memory.append({"role": "user", "content": f"第 {index} 条"})

    (directory / "archive").write_text("我是文件，不是目录", encoding="utf-8")
    memory._summarize = lambda messages: "摘要"      # type: ignore[method-assign]

    snapshot = [dict(item) for item in memory.messages]
    assert memory.maybe_compress(10 ** 9) is False
    assert memory.messages == snapshot


def test_repair_drops_incomplete_round_and_persists() -> None:
    """Ctrl+C 打断后的修复：内存和磁盘都要干净。"""
    import tempfile
    from pathlib import Path

    from core.memory import Memory

    directory = Path(tempfile.mkdtemp()) / "mem"
    memory = Memory(directory)
    memory.append({"role": "user", "content": "q"})
    memory.append({"role": "assistant", "tool_calls": [{"id": "c1"}]})

    assert memory.repair() is True
    assert memory.messages == []
    assert Memory(directory).messages == []
    assert memory.repair() is False          # 幂等
