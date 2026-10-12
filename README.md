# XClaw

> 从零手写的编程智能体（coding agent）。不依赖 LangChain / LangGraph。

用约 90 行实现了一套图编排框架，把「模型 → 工具 → 模型」的循环表达成**图里的一个环**；
在此之上逐层叠加出 workflow、chatbot 和带工具的 agent。

**当前进度**：轻框架 → 模型接入 → 多轮对话 → 工具系统 → agent 主循环，已完成并可运行。
记忆、MCP、Skill、长任务模式在路线图中（见文末）。

---

## 亮点

- **手写图编排框架**（`core/node.py`，约 90 行）：用 `a - "action" >> b` 在代码里画出流程；
  agent 主循环不是写在循环体里，而是**图里的一个环**（`ChatNode ⇄ ToolCallNode`）
- **完整的工具系统**（8 个工具 + 统一执行器）：Pydantic 定义参数并自动生成给模型的工具说明；
  参数以 JSON 传递（解析容错）；工具异常统一规范化为 `tool` 消息，而不是让循环崩掉
- **协议层正确性**：严格遵循 `assistant(tool_calls)` ↔ `tool(tool_call_id)` 的配对规则，
  支持一次回复中的多个工具调用，且保证消息数量与顺序合法
- **渐进式示例**：`workflow → chatbot → chatbot_with_tools`，每层只引入一个新概念，**每个都能独立运行**
- **可离线验证**：工具层与核心循环都能脱离真实模型测试（脚本化假模型 + 断言），验证时不消耗 API 额度

---

## 快速开始

### 环境要求

- Python 3.11+
- 任意 OpenAI 兼容的模型服务（DeepSeek / Kimi / 智谱 / 本地 Ollama 均可）

### 安装与运行

```bash
git clone https://github.com/wangdexun24-tech/XClaw.git
cd XClaw

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # 然后填入下面的配置
```

`.env` 配置（`.env.example` 里有模板）：

```
OPENAI_API_KEY=你的key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL_ID=deepseek-chat
```

### 三个示例，按难度递增运行

```bash
# ① workflow：三个节点串联，让模型总结一个文件
python -m examples.workflow.main

# ② chatbot：多轮对话，记住上下文（/clear 清空历史）
python -m examples.chatbot.main

# ③ agent：能读代码、改文件、跑命令（项目核心）
python -m examples.chatbot_with_tools.main
```

---

## 它能做什么

在 agent 示例（③）里输入自然语言任务，它会自己选择工具、执行、再根据结果继续：

| 输入 | 它做的事 |
|---|---|
| `当前目录下有哪些文件？` | 调用 `ls`，然后归纳目录结构 |
| `看一下 core/node.py 是干什么的，用三句话总结` | `read` 读取文件 → 总结（`[flow]` 日志会显示循环走了 3 步） |
| `在 tmp_demo 目录下创建一个 hello.py，内容是打印 hello xclaw，然后运行它` | `write` 创建文件 → `bash` 执行 → 回报输出 |
| `哪个文件定义了 call_llm 这个函数？` | `grep` 搜索 → 返回 `core/llm.py:44` |

运行时会打印每步的工具调用与结果：

```
[flow] 第 1 步：ChatNode         → action='tool_call'
[flow] 第 2 步：ToolCallNode
  [工具 ✓] write({'path': 'tmp_demo/hello.py', 'content': 'print("hello xclaw")\n'})
           → 已写入 tmp_demo/hello.py（21 字符，1 行）
[flow]          → action='chat'
[flow] 第 3 步：ChatNode
  [工具 ✓] bash({'command': 'python tmp_demo/hello.py'})
           → {"stdout": "hello xclaw\n", "stderr": "", "exit_code": 0}
[flow]          → action='chat'
[flow] 第 4 步：ChatNode         → action='done'
```

---

## 架构

### 分层

```
                   用户
                    │
        examples/chatbot_with_tools/main.py       ← 交互入口 + 两个节点
                    │
        core/node.py  (Node / Flow / shared)      ← 图编排：决定"下一步去哪"
                    │
        core/llm.py   (call_llm / call_llm_simple)← 唯一调用模型的地方
                    │
        tools/executor.py (ToolExecutor)          ← 解析 tool_calls、执行、规范化结果
                    │
        tools/builtins/ (8 个工具)                 ← 真正干活：读写文件、跑命令、搜索
```

**依赖是单向的**：示例依赖 `core` 和 `tools`，反过来不依赖；`core` 不知道 `tools` 的存在。

### agent 主循环 = 图里的一个环

```
        ┌────────────────────────────────┐
        │                                │
        ▼                                │
   ChatNode ──"tool_call"──▶ ToolCallNode
        │
        └──"done"──▶ 结束
```

- `ChatNode` 调用模型：返回了 `tool_calls` 就走 `"tool_call"`，没有就走 `"done"` 结束
- `ToolCallNode` 执行工具、写回结果，然后走 `"chat"` **回到模型**
- 两条边构成环，循环次数由 `MAX_TOOL_ROUNDS` 限制

### 一次工具调用的消息序列

这是协议要求的严格顺序，也是整个项目最容易出错的地方：

```
1. user        {role: "user", content: "看看 core/node.py"}
2. assistant   {role: "assistant", tool_calls: [{id: "call_1", name: "read", ...}]}
3. tool        {role: "tool", tool_call_id: "call_1", content: "…文件内容…"}
4. assistant   {role: "assistant", content: "这个文件实现了一个节点编排框架…"}
```

**规则**：第 2 条必须先于第 3 条；第 3 条的数量与 `tool_call_id` 必须和第 2 条的 `tool_calls` 一一对应。
违反任何一条，API 都会直接拒绝请求。

---

## 关键设计决策

| 决策 | 为什么这样做 | 代价 / 取舍 |
|---|---|---|
| **不用 LangChain 等框架，手写图编排** | 学习项目要看清机制：框架的抽象会掩盖"数据到底怎么流动" | 要多维护一层抽象（`Node`/`Flow`/action）；换来的是流程可读、可画、可复用 |
| `Node.exec()` 返回 **`(action, payload)` 二元组** | 让"分支"变成**数据**，节点不需要知道下一步去哪；同一个节点能接任意后继 | 多一个返回值；换来节点解耦 + 流程可独立改写 |
| 用 `>>` / `-` **运算符**表达连线 | 让图在代码里**读起来像图**：`chat - "tool_call" >> tool_call` | 需要调用者理解这套 DSL；换来极高的可读性 |
| 用 **`shared` 字典**放 `messages` / `tools` | 多个节点（ChatNode、ToolCallNode）需要读写同一份对话历史 | 全局状态不易测试；这是刻意的教学简化（生产应该用依赖注入） |
| `call_llm()` 返回**原始 message 字典** | 模型决定调工具时返回里会多 `tool_calls`，必须**原样回填**历史；解析成自定义对象再转回去最容易丢字段 | 调用方要自己认识 dict 结构；换来"零转换回填" + 顺手拿到 `usage` |
| 手工构造返回字典（白名单） | 只保留 `role/content/tool_calls/reasoning_content/usage`，不把 SDK 内部字段写进历史 | 少写几行 `model_dump()`；换来历史干净、token 不浪费、兼容性更好 |
| **工具失败返回文本，不抛异常** | 模型只能看到返回值；抛出去等于让模型"瞎掉"，它就没机会改正参数 | 调用方需要自己判断 `is_error`；换来 agent 能自我纠错 |
| 工具分成**三层**（纯函数 / `Tool` 定义 / Executor） | 换 LLM 协议只改 `to_llm_format()`；换执行策略只改 Executor；工具函数可单独测试 | 文件多一些；换来关注点分离 |
| 命令执行返回 **`{stdout, stderr, exit_code}`**，非零退出码不算失败 | "命令跑起来了但结果失败"是**正常结果**，模型需要看到错误信息才能修 | 调用方要处理 dict；换来可区分"没跑起来"和"跑了但失败" |
| **只维护 3 个示例，而不是一个大程序** | 每个示例只引入一个新概念（图 → 模型 → 状态 → 工具），**都能独立运行、独立验证** | 会有一点重复代码；换来可教学性和可定位性 |

---

## 项目结构

```
XClaw/
├── core/
│   ├── node.py              # 图编排：Node / Flow / shared（92 行）
│   └── llm.py               # 模型接入：call_llm / call_llm_simple
├── tools/
│   ├── executor.py          # ToolCall / ToolResult / ToolExecutor
│   └── builtins/
│       ├── tool_def.py      # Tool 类 + get_builtin_tools()（含给模型看的说明）
│       ├── read.py  write.py  edit.py  bash.py       # 核心四件套
│       └── ls.py    grep.py   find.py  search.py     # 探索与联网
├── examples/
│   ├── workflow/            # ① 三节点串联
│   ├── chatbot/             # ② 多轮对话（共享历史）
│   └── chatbot_with_tools/  # ③ agent 主循环（图里的环）
├── day1_check.py            # 图编排验收：线性 / 分支 / 循环
├── tools_check.py           # 工具层验收：8 工具 + 错误路径 + tool_calls 解析
├── requirements.txt
└── .env.example
```

**工具清单**（8 个）：

| 工具 | 作用 |
|---|---|
| `read` | 读文件（支持 `offset`/`limit` 分页，30KB 截断并提示如何继续读） |
| `write` | 新建文件（父目录自动创建） |
| `edit` | 精确替换一处文本；**要求原文唯一匹配**，否则拒绝 |
| `bash` | 执行命令，返回 stdout/stderr/退出码；支持超时与输出截断 |
| `ls` | 列目录（目录名带 `/` 后缀，不递归） |
| `grep` | 内容搜索，返回 `相对路径:行号:内容`；跳过噪音目录与二进制文件 |
| `find` | 按通配符查找文件 |
| `search` | 联网搜索（DuckDuckGo），用于查询外部信息 |

---

## 技术栈

- **语言**：Python 3.11+（类型注解 + dataclass）
- **模型接入**：OpenAI 兼容协议（`openai` SDK），支持任意兼容服务
- **数据校验**：Pydantic（工具参数模型 + 自动生成 JSON Schema）
- **编排**：自研 `Node` / `Flow`（无第三方 agent 框架）
- **依赖**：`openai`、`python-dotenv`、`ddgs`（仅这三个）

---

## 路线图

- [x] 图编排框架（线性 / 分支 / 循环）
- [x] 模型接入（最小闭环）
- [x] 多轮对话（共享对话历史）
- [x] 工具系统（8 个工具 + 执行器 + 注册表）
- [x] **agent 主循环**（图里的环 + tool 消息配对 + 最大轮数保护）
- [ ] 记忆：对话持久化（重启续聊）+ 长期记忆 + 上下文自动压缩
- [ ] MCP：把远端工具接入同一套 `Tool` 接口
- [ ] Skill：按需加载的操作手册（渐进式加载，降低 prompt 开销）
- [ ] 长任务模式：给一个目标，自主多轮执行直到满足完成判据
- [ ] 工程化：打包成命令行工具、引入测试、危险操作确认机制

---

## 已知限制

- **`bash` 不是沙箱**：`shell=True` 提供了管道/重定向的便利，但也意味着模型可以执行任意命令。
  目前只有"最大轮数"作为兜底；**计划加入危险操作确认机制**（写/改/执行前询问用户）
- **`search` 依赖外网**：网络不可用时该工具会返回错误（模型会据此改用其他工具）
- 会话历史目前**只存在内存**里，重启即丢失（路线图中"记忆"一项会解决）
- 上下文没有压缩机制：长对话会持续增长 `prompt_tokens`（同样由"记忆"一项解决）
- 工具说明每次请求都会全量带给模型；工具数量增多后需要考虑按需加载（即 Skill 的思路）
- 暂未引入自动化测试框架，目前用两个验收脚本（`day1_check.py` / `tools_check.py`）保证核心行为

---

## 参考

- 项目结构与"渐进式示例"的组织方式，参考了 [Learn-OpenClaw](https://github.com/lasywolf/Learn-OpenClaw) 的教学思路
- 工具集的选择（read / write / edit / bash 为核心）参考了 pi-mono 关于最小 coding agent 的讨论
