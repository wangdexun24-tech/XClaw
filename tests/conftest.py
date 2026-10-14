"""pytest 的公共配置。

做三件事：
1. 把仓库根目录加进 sys.path —— 测试要能 `import core / tools / examples`
2. 每个测试都在仓库根目录下跑 —— 有些验收逻辑依赖相对路径（比如 `ls tools`）
3. 把工作区重置回仓库根目录 —— 防止上一个用例改过工作区后污染下一个

⚠️ 第 3 条是 Day 11 之后**必须**有的：文件工具有了工作区边界，
测试之间如果不把信任上下文还原，就会出现"单独跑通过、一起跑失败"的幽灵问题。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.workspace import set_workspace   # noqa: E402


@pytest.fixture(autouse=True)
def _sandbox(monkeypatch):
    """每个测试：回到仓库根目录 + 工作区也指向仓库根目录。"""
    monkeypatch.chdir(ROOT)
    set_workspace(ROOT, allow_outside=False)
    yield
    set_workspace(ROOT, allow_outside=False)
