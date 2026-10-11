"""模型接入：把"调用大模型"收敛到一个文件。

两个函数，对应两种使用场景：
    call_llm_simple(prompt) -> str                      纯文本生成（不需要工具）
    call_llm(messages, tools, system_prompt) -> dict    完整对话（返回原始 message）
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()                    # 自动读项目根目录的 .env

_client: OpenAI | None = None

def _get_client() -> OpenAI:
    """复用同一个客户端（单例）—— 每次新建会浪费连接和握手。"""
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，请在项目根目录的 .env 里配置")
        _client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    return _client

def _model() -> str:
    return os.environ.get("OPENAI_MODEL_ID", "deepseek-v4-flash")

def call_llm_simple(prompt: str) -> str:
    """纯文本生成：给一句话，返回字符串。"""
    response = _get_client().chat.completions.create(
        model=_model(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""

def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """完整对话：返回**原始的 assistant message 字典**。

    注意：不修改调用方传进来的 messages —— 要加 system prompt 时，
    拼一条新的放在最前面。
    """
    payload: list[dict[str, Any]] = list(messages)
    if system_prompt:
        payload = [{"role": "system", "content": system_prompt}, *payload]

    kwargs: dict[str, Any] = {"model": _model(), "messages": payload}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = _get_client().chat.completions.create(**kwargs)
    message = response.choices[0].message

    # 手工构造返回字典（白名单），而不是 message.model_dump()
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }

    if response.usage:
        result["usage"] = {
            "total_tokens": response.usage.total_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:                       # 推理模型才会有这个字段
        result["reasoning_content"] = reasoning

    if message.tool_calls:              # 模型决定调工具
        result["tool_calls"] = [call.model_dump() for call in message.tool_calls]

    return result

if __name__ == "__main__":
    print(call_llm_simple("用一句话解释什么是 Agent。"))