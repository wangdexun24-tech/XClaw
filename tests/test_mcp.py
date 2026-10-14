"""Day 7：MCP 远端工具接入（连接 / 转换 / 注册 / 调用 / 错误路径 / 收尾）。"""

from __future__ import annotations

import mcp_check


def test_mcp_end_to_end() -> None:
    mcp_check.main()
