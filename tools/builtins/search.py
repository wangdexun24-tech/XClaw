"""联网搜索（DuckDuckGo）。"""

from __future__ import annotations

from ddgs import DDGS

DEFAULT_RESULTS = 5
BODY_PREVIEW = 200


def search(query: str, max_results: int = DEFAULT_RESULTS) -> str:
    """联网搜索，返回编号 + 标题 + 摘要 + 链接。"""
    try:
        with DDGS() as client:
            results = list(client.text(query, max_results=max_results))
    except Exception as exc:
        # 联网失败要给清晰原因（模型看到错误才知道"这条路走不通"）
        raise RuntimeError(f"搜索失败（可能是网络问题）：{type(exc).__name__}: {exc}") from exc

    if not results:
        return f"没有搜索到 {query!r} 的结果"

    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        title = item.get("title", "")
        body = (item.get("body") or "")[:BODY_PREVIEW]
        href = item.get("href", "")
        lines.append(f"{index}. {title}\n   {body}\n   {href}")

    return "\n".join(lines)