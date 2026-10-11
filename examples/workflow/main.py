"""Workflow 示例：三个节点串起来，让模型总结一个文件。

    QueryNode ──"collect"──▶ CollectNode ──"summarize"──▶ SummarizeNode

今天中间节点读**本地文件**（确定性、不依赖网络）；
Day 4 会把它换成真实的 search 工具。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))          # 支持直接运行本文件

from core.llm import call_llm_simple            # noqa: E402
from core.node import Flow, Node                # noqa: E402

MAX_PREVIEW_LINES = 60          # 只取前 60 行当素材，避免 prompt 过长

class QueryNode(Node):
    """整理输入：确认要分析哪个文件。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        target = str(payload).strip() or "core/node.py"
        print(f"  QueryNode: 目标文件 = {target}")
        return "collect", target

class CollectNode(Node):
    """取材：读文件的前 N 行。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        path = PROJECT_ROOT / str(payload)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()[:MAX_PREVIEW_LINES]
        print(f"  CollectNode: 读取 {path.name} 的前 {len(lines)} 行")
        return "summarize", "\n".join(lines)

class SummarizeNode(Node):
    """让模型总结素材（这里用 call_llm_simple，不需要维护对话历史）。
    如果维护对话历史的话，每次都会访问前一次的结果，会造成token的浪费
    """
    
    def exec(self, payload: Any) -> Tuple[str, Any]:
        prompt = f"请用三句话总结下面这段代码在做什么：\n\n{payload}"
        summary = call_llm_simple(prompt)
        return "default", summary

def main() -> None:
    query, collect, summarize = QueryNode(), CollectNode(), SummarizeNode()

    query - "collect" >> collect
    collect - "summarize" >> summarize

    _, result = Flow(query).run("core/node.py")

    print("\n" + "=" * 50)
    print("Workflow 输出：")
    print(result)


if __name__ == "__main__":
    main()
