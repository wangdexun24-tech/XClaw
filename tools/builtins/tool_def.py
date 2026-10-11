"""工具的定义：把"一个普通函数"包装成"模型能调用的工具"。

一个工具需要四样东西：
    name        工具名（模型用它来调用）
    description 给模型看的说明（决定它会不会正确使用）
    parameters  JSON Schema 格式的参数描述
    fn          真正干活的函数
"""

from __future__ import annotations

from typing import Any, Callable, List

class Tool:
    def __init__(self, name: str, description: str, parameters: dict, fn: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.fn = fn

    def to_llm_format(self) -> dict:
        """转成 LLM API 要求的格式（OpenAI / Anthropic 通用）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs) -> Any:
        """真正执行（参数由模型给出）。"""
        return self.fn(**kwargs)

def get_builtin_tools() -> List[Tool]:
    """返回全部内置工具。"""
    from . import bash, edit_file, find, grep, ls, read_file, search, write_file

    return [
        Tool(
            name="read",
            description=(
                "读取文件内容。适合查看源码、配置、文档。"
                "内容过长时会按 30KB 截断，并提示用 offset 继续读。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "description": "起始行号（从 1 开始）"},
                    "limit": {"type": "integer", "description": "最多读多少行"},
                },
                "required": ["path"],
            },
            fn=read_file,
        ),
        Tool(
            name="write",
            description="写入文件（会覆盖已有内容）。适合创建脚本、文档。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "完整文件内容"},
                },
                "required": ["path", "content"],
            },
            fn=write_file,
        ),
        Tool(
            name="edit",
            description=(
                "精确编辑：把文件里唯一出现的一段文本替换成新文本。"
                "要求 old_text 在文件中恰好出现一次，否则会被拒绝。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_text": {"type": "string", "description": "要被替换的原文（含缩进）"},
                    "new_text": {"type": "string", "description": "替换后的新内容"},
                },
                "required": ["path", "old_text", "new_text"],
            },
            fn=edit_file,
        ),
        Tool(
            name="bash",
            description=(
                "在工作目录执行命令，返回 stdout/stderr/退出码。"
                "适合运行脚本、跑测试、查看版本。支持管道与重定向。"
                "退出码非 0 也会正常返回结果。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
                },
                "required": ["command"],
            },
            fn=bash,
        ),
        Tool(
            name="ls",
            description=(
                "列出目录下的直接子项（不递归）。目录名会带 / 后缀。"
                "用于了解项目结构、确认某个文件或目录是否存在。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，默认当前目录"},
                    "limit": {"type": "integer", "description": "最多返回多少项，默认 500"},
                },
            },
            fn=ls,
        ),
        Tool(
            name="grep",
            description=(
                "在文件内容里搜索文本，返回 相对路径:行号:行内容。"
                "用于定位某个函数、变量或配置出现在哪个文件。"
                "默认按正则匹配；literal=true 时按普通文本匹配。"
                "会自动跳过 .git / .venv / __pycache__ 等目录。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "要搜索的内容（默认按正则）"},
                    "path": {"type": "string", "description": "搜索目录或文件，默认当前目录"},
                    "limit": {"type": "integer", "description": "最多返回多少条，默认 100"},
                    "ignore_case": {"type": "boolean", "description": "是否忽略大小写"},
                    "literal": {"type": "boolean", "description": "true 表示按普通文本而非正则匹配"},
                },
                "required": ["pattern"],
            },
            fn=grep,
        ),
        Tool(
            name="find",
            description=(
                '按通配符查找文件，例如 "*.py"、"test_*.py"。'
                "只返回文件，路径相对搜索起点。会自动跳过 .git / .venv 等目录。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "通配符，如 *.py"},
                    "path": {"type": "string", "description": "搜索目录，默认当前目录"},
                    "limit": {"type": "integer", "description": "最多返回多少个文件，默认 200"},
                },
                "required": ["pattern"],
            },
            fn=find,
        ),
        Tool(
            name="search",
            description=(
                "联网搜索网页，返回标题、摘要和链接。"
                "适合查询最新信息、第三方库用法、报错原因。"
                "注意：需要外网可用，网络不通时会返回错误。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "返回多少条结果，默认 5"},
                },
                "required": ["query"],
            },
            fn=search,
        ),
    ]