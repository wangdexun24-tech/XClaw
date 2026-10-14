# XClaw

> 从零手写的编程智能体（coding agent）。不依赖 LangChain / LangGraph。

用约 90 行实现了一套图编排框架，把「模型 → 工具 → 模型」的循环表达成**图里的一个环**；
在此之上逐层叠加出 workflow、chatbot 和带工具的 agent。

**当前进度**：轻框架 → 模型接入 → 多轮对话 → 工具系统 → agent 主循环 → 记忆 → MCP → Skill
→ 长任务模式 → 操作确认 → 工程化加固，已完成并可运行。收尾（pytest / 打包）在路线图中（见文末）。

---

## 亮点

- **手写图编排框架**（`core/node.py`，约 90 行）：用 `a - "action" >> b` 在代码里画出流程；
  agent 主循环不是写在循环体里，而是**图里的一个环**（`ChatNode ⇄ ToolCallNode`）
- **完整的工具系统**（8 个工具 + 统一执行器）：用声明式 `Tool(name, description, parameters, fn)`
  登记工具，`to_llm_format()` 统一转成模型协议；参数以 JSON 传递（解析容错）；
  工具异常统一规范化为 `tool` 消息，而不是让循环崩掉
- **记忆系统**：对话逐条落盘（jsonl，重启续聊）+ 长期记忆（MEMORY.md，注入 system prompt）
  + 按 token 用量触发的上下文压缩，并且能正确处理"崩溃在工具调用中间"的恢复
- **MCP 支持**：把跑在独立进程里的工具接进同一套 `Tool` 接口，
  接入点只有一个 `register()`；执行器与主循环完全不需要知道 MCP 的存在
- **长任务模式**：给一个目标，程序按**可判定的完成判据**（退出码）反复验证，
  没过就带着失败证据自动重试，直到通过或预算耗尽 ——
  **"做完了没有"由程序说了算，不是由模型宣布**
- **操作确认**：写文件、改文件、执行命令、联网都要先经用户同意（默认拒绝），
  纯读工具自动放行；危险命令会被高亮提示。
  **确认是图上的一个节点**，不是塞在主循环里的一段 `if`
- **工程化加固**：文件工具受**工作区边界**约束（`..` 和符号链接都绕不出去）；
  写入是**原子**的（先写临时文件再改名）；压缩前先**归档**原始记录；
  改文件前会显示 **diff 预览**；被 Ctrl+C 打断后能自动**修复历史**
- **协议层正确性**：严格遵循 `assistant(tool_calls)` ↔ `tool(tool_call_id)` 的配对规则，
  支持一次回复中的多个工具调用，且保证消息数量与顺序合法
- **Skill（渐进式披露）**：操作手册只在**模型主动点名时**才加载，常驻 prompt 的只有一行清单；
  10 份手册全量注入和按需加载的差距，在 `skill_check.py` 里有实测数字
- **渐进式示例**：`workflow → chatbot → chatbot_with_tools → chatbot_with_mcp → chatbot_with_skills`，
  每层只引入一个新概念，**每个都能独立运行**
- **可离线验证**：工具层、记忆、MCP 都能脱离真实模型测试（脚本化假模型 + 断言），验证时不消耗 API 额度

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

### 六个示例，按难度递增运行

```bash
# ① workflow：三个节点串联，让模型总结一个文件
python -m examples.workflow.main

# ② chatbot：多轮对话，记住上下文（/clear 清空历史）
python -m examples.chatbot.main

# ③ agent：能读代码、改文件、跑命令（项目核心）
python -m examples.chatbot_with_tools.main

# ④ agent + MCP：在 ③ 的基础上，外加一个独立进程里的远程工具集
python -m examples.chatbot_with_mcp.main

# ⑤ agent + Skill：在 ③ 的基础上，外加一批"按需加载的操作手册"
python -m examples.chatbot_with_skills.main

# ⑥ 长任务模式：给它一个目标，它自己跑到"程序验证通过"为止
python -m examples.goal_agent.main goals/demo_wc_tool.md
```

离线自检（不消耗 API 额度，随时可以跑）：

```bash
python day1_check.py      # 图编排：线性 / 分支 / 循环
python tools_check.py     # 工具层：8 个工具 + 错误路径 + tool_calls 解析
python memory_check.py    # 记忆：字段过滤 / 崩溃恢复 / 压缩边界 / 长期记忆
python mcp_check.py       # MCP：连接 / 转换 / 注册 / 调用 / 错误路径 / 收尾
python skill_check.py     # Skill：渐进式加载 / frontmatter 容错 / 幂等 / 接入
python goal_check.py      # 长任务：加载校验 / 判据执行 / 重试证据 / 预算 / 内环重置
python approval_check.py  # 操作确认：默认值 / 分类 / 配对 / 不越权
python hardening_check.py # 工程化加固：工作区边界 / 原子写 / 归档 / 中断恢复 / 差异预览
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

而在 MCP / Skill 示例里，它能做的事会变多（工具变多了，模型自己选）：

| 输入 | 它做的事 |
|---|---|
| `(128*3+45)/7 等于多少？` | 调用远程 MCP 工具 `calc`（跑在**另一个进程**里） |
| `团队知识库里关于值班的约定是什么？` | 调用远程 MCP 工具 `query_notes` |
| `帮我看看 tools/builtins/edit.py 有什么问题` | **先加载** `code-review` 手册 → 再 `read` → 按手册的格式输出 |
| `我这次改动该怎么写提交信息？` | **先加载** `commit-message` 手册 → `git diff` → 按规范生成 |

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
        core/memory.py (Memory)                   ← 对话落盘 + 长期记忆 + 上下文压缩
                    │
        core/llm.py   (call_llm / call_llm_simple)← 唯一调用模型的地方
                    │
        tools/executor.py (ToolExecutor)          ← 解析 tool_calls、执行、规范化结果
                    │
        ┌───────────┼───────────┬───────────┐
        │           │           │           │
 tools/builtins/  tools/mcp/    tools/skills/
   (8 个工具)    (client+adapter) (loader+tool)
        │           │           │
  读写文件/跑命令  MCP 服务器     skills/*/SKILL.md
    /搜索          （另一个进程）  （按需加载的手册）
```

**依赖是单向的**：示例依赖 `core` 和 `tools`，反过来不依赖；`core` 不知道 `tools` 的存在。
`ToolExecutor` 既不知道 MCP、也不知道 Skill 的存在 —— 它只认 `Tool` 那四样东西。

**两条接入路径完全同构**，都是"把别的东西翻译成 `Tool`，再 `register()` 进来"：

```
tools/mcp/    远程的**动作**  →  MCPClient + to_local_tools()   →  executor.register()
tools/skills/ 本地的**知识**  →  SkillLoader + build_skill_tool() →  executor.register()
                     两者都没让 主循环 / 执行器 / llm 改动一行
```

这就是「先定接口、再扩能力」的收益：能力可以无限加，核心永远不用动。

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

### MCP：让"不在本进程里的工具"也能用

Day 4 的工具都是函数调用（`read` / `bash` 就在本进程里）。但真实世界的工具常常不在：
可能是另一个进程（本地 CLI、MCP 服务器），也可能是另一台机器（HTTP 服务）。
每接一个新工具就改一遍 agent 是不现实的，MCP（Model Context Protocol）就是给这件事定的标准。

**协议本身只有两件事**，而且相互独立：

1. **说什么**：JSON-RPC 2.0 —— `tools/list` 拿工具清单，`tools/call` 调工具
2. **怎么运**：transport —— 改 `transport` 就能从 stdio 换到 HTTP，**约定不变**

**接入路径只有四步**，全部代码都在 `tools/mcp/`：

```
MCPClient.start()         有连接了（后台线程跑 event loop，把 async 包成 sync）
        │
        ▼
client.list_tools()       拿到远端工具清单（name / description / inputSchema）
        │
        ▼
to_local_tools(client)    ← 关键一步：适配成 Tool(name, description, parameters, fn)
        │
        ▼
executor.register(...)    挂进执行器，和 8 个本地工具平起平坐
```

对执行器来说，远程工具和本地 `read` 没有任何区别 —— **这是 Day 4 把工具接口定型成
`Tool` 契约的回报**：接入 MCP 没有改动 `ToolExecutor`、`ChatNode`、`ToolCallNode`、`call_llm` 中的任何一行逻辑。

```bash
$ python mcp_check.py
① 远程工具 3 个：['server_info', 'calc', 'query_notes']
③ 工具总数 8 → 11
④ calc: 61.285714285714285
   server_info: {'cwd': '.../XClaw', 'pid': 95093}   ← 进程号和主进程不同，证明确实在另一个进程里
⑤ calc({'expression': 'import os'}) → [工具失败] ...（远程异常被规范化，没有炸掉循环）
```

**MCP 的代价**：远端工具的完整说明每次请求都要塞进 prompt，工具一多就浪费 token。
这正是下一步 Skill（渐进式加载）要解决的问题。

---

### Skill：按需加载的操作手册

有些能力不是"一个动作"，而是"一整套流程和领域知识"（怎么审查代码、怎么排查报错、
这个项目的提交信息怎么写）。它们写不成函数，只能写成**手册**。

把手册全塞进 system prompt 的代价是线性的：50 份 × 约 2000 token = 10 万 token，
而一次对话通常只用得上其中一份。解法叫**渐进式披露**，分三个阶段：

```
阶段① 扫描        启动时只解析 YAML frontmatter（name + description），正文不进上下文
        │
阶段② 注入        每次请求只带一张清单（N × 约 25 token），塞进 skill 工具的 description
        │
阶段③ 加载        模型主动调用 skill(name=...) 时，才把正文读出来
```

**为什么能接进已有的 agent**：产物仍然是一个 `Tool(name, description, parameters, fn)`。
所以和 Day 7 的 MCP 一样 —— 靠 `executor.register()` 一个口子进来，**主循环零改动**。

区别在于这两个字的含义：

| | MCP | Skill |
|---|---|---|
| 接进来的是什么 | 别处跑的**动作** | 本地的**知识/流程** |
| prompt 占用 | 全部工具的完整说明，每次都带 | 只有一行清单常驻；正文按需 |
| 谁执行 | 代码执行 | 模型读完之后自己动手 |
| 数量级 | 十来个 | 可以几十上百 |

**手册长这样**（`skills/code-review/SKILL.md`）：

```markdown
---
name: code-review
description: 按团队规范审查 Python 代码。当用户要求 review、检查代码、找 bug、看代码风格，
             或问"这段代码有什么问题"时，先加载本手册再动手。
---

# 代码审查流程
## 硬性检查（逐条过，不要跳）
1. 边界条件：空输入、None、越界、除零
...
```

**两个设计要点，也是大多数实现失败的地方：**

1. **`description` 是"路由信息"，不是"介绍"**。模型只靠它判断"现在该不该加载"，
   所以必须写**什么时候用**，而不是"这是什么"。
2. **整个技能库只是一个工具**（`skill`，用 JSON Schema 的 `enum` 约束可选项），
   而不是 N 个工具 —— 否则每份手册的说明都要常驻 prompt，又回到了全量注入。

**实测数据**（`skill_check.py` 输出，3 份手册）：

```
· 注入成本：约 243 字符
· 若全量注入正文：约 2393 字符
· 节省：90%
```

手册越多、越长，这个比例越高。另外还有一层**幂等保护**：
同一份手册第二次被点名时只回一句"已经在上下文里了"，不再重复塞全文。

---

### 长任务模式：把"结束"的决定权从模型手里拿走

前面所有的模块都在做同一件事：**给模型更多能力和信息**。
而在这之前，"活干完了没有"一直是**模型自己宣布的**：

```python
tool_calls = saved.get("tool_calls")
if not tool_calls:
    return "done"        # ← 模型说完了，程序就信了
```

问题是模型经常说"我修好了"，而测试还是红的。更根本地说——
拿模型的判断去验证模型的行为，是**循环论证**。

长任务模式把它反过来：**"结束"的条件从「模型说完了」改成「程序验证通过」。**

```
                    ┌──────────────────────────────────────┐
                    │                                      │
                    ▼                                      │
       ChatNode ⇄ ToolCallNode      ← 内环：怎么做（Day 5 的代码，一行没改）
            │
            └─"done"─▶ VerifyNode ─"retry"─▶ ChatNode      ← 外环：做完了没有
                           │
                           ├─"passed" ─┐
                           └─"give_up"─┴─▶ ReportNode ─▶ 结束
```

**自主性三要素，缺一个就失控：**

| 要素 | 少了它会怎样 |
|---|---|
| 循环（失败就带着原因重来） | 停在第一次失败，需要人盯着 |
| 判据（程序可判定的完成条件） | 无限打转，永远不知道自己好了没有 |
| 预算（最多尝试几轮） | 可以烧光 API 额度 |

**任务文件**（frontmatter 格式复用了 Day 8 的解析器，已下沉到 `core/frontmatter.py`）：

```markdown
---
goal: 在 tools/builtins/ 下新增一个 wc 工具，注册进 get_builtin_tools()，并保证 tools_check.py 通过。
check:
  - python tools_check.py
  - python -c "from tools.builtins import get_builtin_tools as g; assert 'wc' in {t.name for t in g()}"
budget: 8
---
```

**四条最重要的设计约束：**

1. **判据必须由外部给出，不能由模型自己定。** 让模型定判据等于让运动员自己当裁判 ——
   它会定一个自己稳过的判据。所以判据写死在任务文件里。
2. **判据必须是程序可判定的**：只收退出码（`pytest -q`、`python check.py`），
   不收"代码质量好不好"这种没法判真假的条件。
3. **重试必须带证据**：命令原文 + 退出码 + 输出尾部。只说"没过，请继续"，
   模型就会把同一个错误再犯一遍。这也是为什么 Day 4 的 `bash` 要返回**结构化的
   `exit_code`** 而不是一坨字符串 —— 那个决定到这一步才收网。
4. **缺 check 的任务文件直接拒绝运行**：没有判据的长任务，等于退回"模型自己说做完了"，
   那还不如不做。**早失败，比跑偏 12 轮再失败便宜得多。**

**一个诚实的漏洞**：模型有 `bash` 和 `edit`，完全可以去改测试让判据变绿
（reward hacking，真实 agent 系统里的常见问题）。当前有三道防线：
提示词里写明禁止改检查 → 判据尽量用外部工具（`pytest` 跑的是你写的测试）→
跑判据前用 `git status` 挑出"看起来像测试"的改动并**提示给人**。
最后一道只提供证据、不强制拦截 —— **程序负责提供证据，人负责定夺。**

```
$ python -m examples.goal_agent.main goals/demo_wc_tool.md
🎯 XClaw 长任务模式
目标：在 tools/builtins/ 下新增一个 wc 工具 …
判据（2 条，退出码 0 表示通过）：…

🤖 助手：…（自己选工具、动手、自测）
🔍 验证第 1/8 次尝试
  [✓] python tools_check.py
  [✓] python -c "…assert 'wc' in names…"
✅ 目标达成（第 1 次尝试）
```

每次尝试都会往 `goal_runs/*.jsonl` 追加一行（尝试序号、每条件判据的退出码、耗时），
用途有三个：调试、放弃时有据可查、以及攒出"平均尝试轮数 / 成功率"这类简历数据。

---

### 操作确认：把"允许不允许"变成图上一个节点

`bash` 是 `shell=True`，模型理论上能执行任意命令。这件事从 Day 4 起就挂在
"已知限制"里，Day 10 把它补上。

**关键是"补在哪"**。如果往 `ChatNode` 里塞一段 `if 需要确认: input(...)`，
主循环会开始膨胀（同类项目 ZipClaw 的主循环因此涨到 788 行）。
在"控制流是数据"的图里，确认是一段独立的控制流，所以它应该是一个**节点**：

```
ChatNode ─"tool_call"─▶ ApprovalNode ─"proceed"─▶ ToolCallNode
                              │                        │
                              └──（拒绝的信息也走 tool 消息）──┘
```

**接入的改动量**：1 个新文件（`core/approval.py`）+ 3 处小改动。
`ChatNode` 一行没动，`ToolCallNode` 只多了一个"这条被拒了"的分支。

**确认策略由 `Tool` 自己声明**，而不是由主循环记住每个工具的名字：

| 工具 | 策略 |
|---|---|
| `read` `ls` `grep` `find` | 免确认（只读本地） |
| `write` `edit` `bash` `search` | 需要确认 |
| MCP 工具 / 其他外部工具 | **默认需要确认**（代码不是我们控制的） |

**四条设计决策：**

1. **默认值是"需要确认"（fail-safe）**：新增工具忘了声明，后果是"多问一句"，
   不是"默默放行"。Day 7 的 MCP 工具和 Day 8 的 `skill` 工具没改一行代码，
   就被自动纳入了保护范围。
2. **拒绝也要回一条 `tool` 消息**：消息配对是铁律（Day 3/5）。
   直接跳过会产生"孤立的 tool_call"，下一次请求被 API 拒绝 —— 那是用一个 bug 换另一个 bug。
3. **危险检测只提示，不做决定**：`scan_command()` 会把 `rm` / `sudo` / `git push` /
   `curl | sh` / 重定向覆盖等模式标出来，但**放行与否完全由人说**。
   正则永远会漏（`find -delete`、`python -c "shutil.rmtree(...)"`），
   误报也永远会有 —— 它只能提高人的注意力，不能变成权限系统。
4. **没配置确认器时默认拒绝**：无人值守的场景必须**显式声明**自己的信任策略
   （`AutoApprover()`），而不是靠"忘了配 → 自动放行"。

```
$ python -m examples.chatbot_with_tools.main
👤 你：在 /tmp 下创建 demo.txt，内容写 hello

────────────────────────────────────────────────────────
[需要确认] write
完整参数（不截断 —— 人要据此做决定）：
{
  "path": "/tmp/demo.txt",
  "content": "hello\n"
}
────────────────────────────────────────────────────────
允许执行吗？输入 y 同意，其它一律拒绝 [y/N]：
```

拒绝之后模型的表现（真实模型实测）：

```
  [工具 ✗] write({'path': '/tmp/demo.txt', ...})
           → 本次工具调用未获得用户确认，未执行任何操作。
             请向用户说明情况，不要自行重试，也不要改用其它工具去完成同一件被拒绝的事。

🤖 助手：本次操作未获得你的确认，所以工具没有真正执行，/tmp/demo.txt 目前并未创建。
        按规则我不会自行重试，也不会换其他工具绕过这个确认。
```

注意拒绝消息里那句"**不要改用其它工具去完成同一件被拒绝的事**"——
没有这句话，模型会很自然地换成 `bash` 用 `echo > file` 把文件写出来，确认就形同虚设。

---

### 工程化加固：四件"看不见但很重要"的事

这四件事都不增加新功能，但每一件都在堵一个真实的坑。

**① 工作区边界**（`core/workspace.py`）

Day 4 起文件工具接受任意路径，模型可以说"帮我看看 `~/.ssh/id_rsa`"。现在不行了：

```
    工作区 .                      传给工具的路径
      ├── src/app.py              a.py                → 在工作区内 ✓
      └── link -> /etc/passwd     ../../etc/passwd    → 解析后跑出去了 ✗
                                  link                → 解析后是 /etc/passwd ✗
```

两个细节决定它有没有用：

- **先 `Path.resolve()` 再判断**，所以 `..` 和**符号链接**都拦得住（只做字符串前缀比较挡不住软链）
- **用 `parents` 判断子路径**，而不是 `str(p).startswith(root)` ——
  后者会把 `/tmp/ws_evil` 误判成 `/tmp/ws` 的子路径

`ensure_inside()` 返回**已解析的绝对路径**，工具直接拿它用，不再 resolve 第二次 ——
避免"检查的是 A、使用的是 B"。

**② 原子写**（`core/workspace.py` 里的 `atomic_write`）

写到一半崩了（磁盘满、进程被杀），直接 `write_text` 会把原文件变成半截。
改成"先写同目录的临时文件，再改名覆盖"之后，要么全成、要么原文件一点没动。
（`replace` 而不是 `rename`：Windows 上 rename 不能覆盖已存在的目标。）

**③ 压缩前归档**（`core/memory.py`）

上下文压缩是**有损**的。现在压缩前会把完整原始记录存到 `chat_memory/archive/*.jsonl`。

关键是**顺序**：

```
生成摘要 → 确认摘要真的更短 → 归档 → 最后才替换
   失败就跳过      失败就跳过     失败就跳过（宁可多占上下文，也不丢原始记录）
```

任何一步失败都保留原状，绝不出现"历史没了、摘要也没有"的空档。

**④ 中断恢复**（`Memory.repair()`）

优雅处理 Ctrl+C 之后会暴露一个真 bug：打断可能正好落在
"assistant 已经写了 `tool_calls`、tool 结果还没写回"的缝隙里，
历史里留下一条**孤立的 tool_call**，下一次请求会被 API 直接拒绝。

修法是复用 Day 6 就写好的恢复逻辑 —— 把它从 `_load_session` 里提成模块级函数
`drop_incomplete_round()`，文件读回和内存修复共用一份：

> **同一份规则被第二处需要，就该提取出来，而不是复制粘贴。**

**⑤ 差异预览**（顺带做的）

`edit` 现在会在确认时显示 diff。**预览函数由工具自己提供**（`Tool.preview`）：
只有工具知道 `old_text/new_text` 是什么意思，确认器和节点都不该认识具体工具的语义。

```
────────────────────────────────────────────────────────────
[需要确认] edit
完整参数（不截断 —— 人要据此做决定）：
{
  "path": "demo.py",
  "old_text": "    return a - b",
  "new_text": "    return a + b"
}

[修改预览] - 表示删除，+ 表示新增（只预览被替换的片段）：
--- 原文
+++ 修改后
@@ -1 +1 @@
-    return a - b
+    return a + b
────────────────────────────────────────────────────────────
```

注意预览**只读参数、不读文件** —— 读整个文件既慢，又会在"预览"和"真正执行"之间
产生时间差；片段是否唯一匹配，留到执行时再检查（那时才有权威答案）。

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
| **只维护一组渐进式小示例，而不是一个大程序** | 每个示例只引入一个新概念（图 → 模型 → 状态 → 工具 → 外部工具），**都能独立运行、独立验证** | 会有一点重复代码；换来可教学性和可定位性 |
| 对话用 **jsonl 追加**而不是每次重写整个文件 | 追加便宜，且前缀不变更容易命中服务商的 prefix KV cache；坏一行只坏一行 | 需要自己处理"读回时把没走完的一轮丢掉"的恢复逻辑 |
| 压缩**只在"一轮结束"时触发** | 在工具轮中间压缩会把 `assistant(tool_calls)` 和 `tool` 结果拆散，API 直接报错 | 需要判断边界；换来历史永远合法 |
| MCP 客户端用**后台线程 + 常驻事件循环** | MCP 官方客户端是 async，而 agent 是同步的；连接必须复用，不能每次调用都重启子进程 | 多一层线程桥；换来同步代码里可直接用远程工具 |
| 连接在**同一个任务里 enter/exit** | anyio 的 cancel scope 要求进出同任务，否则退出时报 `Attempted to exit cancel scope in a different task` | 写法稍绕（`_serve()` 长驻）；换来退出干净、不留僵尸进程 |
| 适配器把远程错误**抛成异常**而不是返回错误字符串 | Executor 只认"抛异常 → `is_error=True`"这一条通路，模型才知道自己失败了 | 多一层转换；换来远程/本地工具的错误处理完全一致 |
| `ToolExecutor` **不认识 MCP** | 执行器不该关心工具"在哪跑"；接入新来源只需在外部转换 | 需要调用方管理连接生命周期；换来关注点分离 |
| Skill 做成**一个工具 + `enum`**，而不是 N 个工具 | 工具列表每次请求都要付 token；N 个工具等于让每份手册常驻 prompt | 模型要多一步"先加载再动手"；换来常驻成本从 O(正文) 降到 O(一行说明) |
| frontmatter 只支持 **`key: value` 单行** | 我们的元数据只有 name/description 两个单行字段，手写解析 15 行足够 | 支持不了列表/多行；真需要时换 `yaml.safe_load`（**不是** `yaml.load`，那能构造任意 Python 对象） |
| 缺 `description` 的手册**直接丢弃** | 没法路由的手册留在索引里只会干扰模型判断 | 少一份手册；换来索引里每一条都是"可用"的 |
| 记录已加载手册（`loaded` 集合） | 同一份手册读两遍纯属浪费 token | `loaded` 不感知上下文压缩，这是已知缺陷（见"已知限制"） |
| 任务文件复用 **frontmatter** 格式（Day 9） | 同一份能力被第二个地方需要，就该提取出来 —— 解析器从 `tools/skills/` 下沉到 `core/frontmatter.py` | 多一次重构；换来 `tools/` 和 `core/` 都能用，依赖方向仍是单向的 |
| 完成判据用**退出码**，不用模型判断 | shell 退出码是沉淀了几十年的"完成判据协议"，`pytest` 已经替你写好了 | 判据必须能被表达成命令；换来判断**客观**、可复现、不烧 token |
| 判据**不走 `ToolExecutor`** | Executor 是"模型调用的工具"的通道；判据是"程序自己跑的检查"，混在一起模型就有机会干预 | 多一点代码；换来判据和模型之间的隔离 |
| 判据**全部跑完**，不提前退出 | 目标常是多条件的（功能 + 测试 + 不留脏文件），一次把问题都说清，比挤牙膏高效 | 多花几秒；换来重试更有针对性 |
| 重试消息里塞**命令原文 + 退出码 + 输出尾部** | 只说"没过，请继续"，模型会把同一个错误再犯一遍 | 消息变长；换来重试有效 |
| 缺 `check` 就**拒绝运行** | 没有判据的长任务等于退回"模型自己说做完了" —— 那还不如不做 | 少一种"随便跑跑"的用法；换来不会静默退化 |
| 长任务把进程 cwd **切到 `goal.workdir`** | 8 个工具都按相对路径 + `Path.resolve()` 定位，判据按 `workdir` 跑；两者不一致会出现"判据在 A 找、模型在 B 写" | `chdir` 是进程级全局状态，作为库被调用时不够礼貌（退出时已还原）；更干净的做法是给工具传 cwd |
| `Tool.requires_approval` **默认 True** | fail-safe：忘了声明的后果必须是"多问一句"，不能是"默默放行"；新接入的工具（MCP / Skill）自动被纳入保护 | 纯读工具要显式传 `False`，多写一个参数 |
| 操作确认做成**图上的节点**，不塞进 `ChatNode` | 控制流是数据：确认是一段独立的控制流，做成节点后主循环零改动，且能单独测试 | 多一个节点、多一次解析 `tool_calls`；换来职责清晰（同类项目把确认写进主循环，那个类涨到 788 行） |
| **拒绝也写回 `tool` 消息** | `assistant(tool_calls)` ↔ `tool` 的配对是协议铁律；跳过会产生孤立调用，下一次请求直接被拒 | 拒绝路径要多写几行；换来历史永远合法 |
| 危险模式**只提示、不做决定** | 正则永远会漏也永远会误报，只有人能综合判断；把它变成"自动拒绝"会给人虚假的安全感 | 用户仍可能点错 y；换来不越权、不误伤 |
| 确认器用 **`Protocol` + 依赖注入** | 测试可以自己造替身（`RecordingApprover`），不用改产品代码；`input`/`print` 注入后"会阻塞人"的代码变得可测 | 多一层抽象；换来可测 + 终端/微信/自动三种场景共用一个节点 |
| 没配置确认器时**默认拒绝** | 忘记配置必须表现为"立刻报错"，而不是"静默危险" | 每个示例入口都要显式写一行 `shared["approver"] = ...`；换来不会静默放行 |
| 路径边界用 **`resolve()` + `parents`**，不用字符串前缀 | 只比较前缀挡不住符号链接，还会把 `/tmp/ws_evil` 误判成 `/tmp/ws` 的子路径 | 每次调用多一次 `resolve()`（可忽略）；换来真的拦得住 |
| `ensure_inside()` **返回解析后的路径** | 工具拿它直接用，不再 resolve 第二次 —— 避免"检查的是 A、使用的是 B" | 调用方要改一行（`Path(path).resolve()` → `ensure_inside(path)`）；换来检查和执行是同一个对象 |
| 写完文件用 **临时文件 + `replace`** 原子落盘 | 写一半崩了会让原文件变成半截；"改坏文件"比"没改成"严重得多 | 多一次改名；换来要么全成、要么原文件不动 |
| **先归档、再压缩；归档失败就不压** | 压缩是有损的，丢了就找不回来。宁可不压（多占上下文），也不丢原始记录 | 多一份磁盘占用；换来可回溯 |
| 恢复逻辑提成模块级 `drop_incomplete_round()` | Day 6 只在读文件时用，Day 11 中断恢复要在内存里用 —— 同一规则两处需要就该提取 | 要保证提取后语义**逐字等价**（`memory_check.py` 保护了这次重构）；换来不会出现两份会改歪的逻辑 |
| 预览由 **`Tool.preview`** 提供，不放在确认器/节点里 | 只有工具知道参数的含义；确认器要服务 MCP 工具、节点不该认识 `old_text` | 多一个可选参数；换来职责归位 |
| 预览失败**返回 None 而不是抛异常** | 预览是辅助信息，不是功能本身 —— 不能因为"看不清预览"就让人没法确认操作 | 静默降级；换来主流程不被辅助环节拖垮 |
| 工作区边界**不覆盖 `bash`** | 试图分析 shell 命令里的路径必然漏（变量、管道、子 shell）；`bash` 归操作确认管 | 两套机制各管一摊；换来不产生"以为拦住了"的虚假安全感 |

---

## 项目结构

```
XClaw/
├── core/
│   ├── node.py              # 图编排：Node / Flow / shared（92 行）
│   ├── llm.py               # 模型接入：call_llm / call_llm_simple
│   ├── memory.py            # 记忆：对话落盘 + 长期记忆 + 上下文压缩
│   ├── frontmatter.py       # 通用 frontmatter 解析（Skill 和 Goal 共用）
│   ├── goal.py              # 长任务：Goal / run_checks / build_retry_message
│   ├── approval.py          # 操作确认：ApprovalNode / ConsoleApprover / 危险模式
│   └── workspace.py         # 工作区边界 + 原子写（ensure_inside / atomic_write）
├── skills/                  # 操作手册（YAML frontmatter + 正文）
│   ├── code-review/SKILL.md
│   ├── commit-message/SKILL.md
│   └── debug-python/SKILL.md
├── goals/
│   └── demo_wc_tool.md      # 一个真实可跑的长任务（目标 + 判据 + 预算）
├── tools/
│   ├── executor.py          # ToolCall / ToolResult / ToolExecutor
│   ├── builtins/
│   │   ├── tool_def.py      # Tool 类 + get_builtin_tools()（含给模型看的说明）
│   │   ├── read.py  write.py  edit.py  bash.py       # 核心四件套
│   │   └── ls.py    grep.py   find.py  search.py     # 探索与联网
│   ├── mcp/
│   │   ├── server.py        # MCP 服务器：把普通函数注册成远程工具
│   │   ├── client.py        # MCP 客户端：后台线程 + 常驻连接（async → sync）
│   │   └── adapter.py       # 适配器：MCP 工具 → 本地 Tool
│   └── skills/
│       └── loader.py        # SkillLoader（扫描/解析）+ build_skill_tool（注入/加载）
├── examples/
│   ├── workflow/            # ① 三节点串联
│   ├── chatbot/             # ② 多轮对话（共享历史）
│   ├── chatbot_with_tools/  # ③ agent 主循环（图里的环）
│   ├── chatbot_with_mcp/    # ④ 在本机工具之外再加一组远程工具
│   ├── chatbot_with_skills/ # ⑤ 再加一批按需加载的操作手册
│   └── goal_agent/          # ⑥ 长任务模式（在外层再套一个环）
├── day1_check.py            # 图编排验收：线性 / 分支 / 循环
├── tools_check.py           # 工具层验收：8 工具 + 错误路径 + tool_calls 解析
├── memory_check.py          # 记忆验收：字段过滤 / 崩溃恢复 / 压缩边界 / 长期记忆
├── mcp_check.py             # MCP 验收：连接 / 转换 / 注册 / 调用 / 错误路径 / 收尾
├── skill_check.py           # Skill 验收：渐进式加载 / 容错 / 幂等 / 接入
├── goal_check.py            # 长任务验收：加载校验 / 判据 / 重试证据 / 预算 / 内环重置
├── approval_check.py        # 确认验收：默认值 / 分类 / 拒绝配对 / 危险检测不越权
├── hardening_check.py       # 加固验收：边界 / 原子写 / 归档 / 中断恢复 / 预览
├── requirements.txt
└── .env.example
```

**工具清单**（8 个）：

| 工具 | 作用 |
|---|---|
| `read` | 读文件（支持 `offset`/`limit` 分页，30KB 截断并提示如何继续读） · 免确认 |
| `write` | 新建文件（父目录自动创建） |
| `edit` | 精确替换一处文本；**要求原文唯一匹配**，否则拒绝 |
| `bash` | 执行命令，返回 stdout/stderr/退出码；支持超时与输出截断 |
| `ls` | 列目录（目录名带 `/` 后缀，不递归） · 免确认 |
| `grep` | 内容搜索，返回 `相对路径:行号:内容`；跳过噪音目录与二进制文件 · 免确认 |
| `find` | 按通配符查找文件 · 免确认 |
| `search` | 联网搜索（DuckDuckGo），用于查询外部信息 |

---

## 技术栈

- **语言**：Python 3.11+（类型注解 + dataclass）
- **模型接入**：OpenAI 兼容协议（`openai` SDK），支持任意兼容服务
- **工具协议**：手写 JSON Schema 声明参数，统一由 `to_llm_format()` 转成模型协议
- **编排**：自研 `Node` / `Flow`（无第三方 agent 框架）
- **外部工具**：MCP（`mcp` 官方客户端 + `fastmcp` 服务器端）
- **知识注入**：自研 Skill 加载器（YAML frontmatter + 渐进式披露，无第三方依赖）
- **操作确认**：自研 `ApprovalNode` + `Protocol` 确认器（终端 / 自动两种实现，无第三方依赖）
- **依赖**：`openai`、`python-dotenv`、`ddgs`、`mcp`、`fastmcp`（只有这五个）

---

## 路线图

- [x] 图编排框架（线性 / 分支 / 循环）
- [x] 模型接入（最小闭环）
- [x] 多轮对话（共享对话历史）
- [x] 工具系统（8 个工具 + 执行器 + 注册表）
- [x] **agent 主循环**（图里的环 + tool 消息配对 + 最大轮数保护）
- [x] 记忆：对话持久化（重启续聊）+ 长期记忆 + 上下文自动压缩
- [x] **MCP：把远端工具接入同一套 `Tool` 接口**
- [x] **Skill：按需加载的操作手册（渐进式加载，降低 prompt 开销）**
- [x] **长任务模式：给一个目标，自主多轮执行直到满足完成判据**
- [x] **危险操作确认机制（写/改/执行/联网前询问，默认拒绝，危险命令高亮）**
- [x] **工程化加固：工作区边界 / 原子写 / 压缩前归档 / 中断恢复 / 差异预览**
- [ ] 工程化收尾：打包成命令行工具、把验收脚本改造成 pytest

---

## 已知限制

- **`bash` 仍然不是沙箱**：`shell=True` 提供了管道/重定向的便利，也意味着模型能执行任意命令。
  Day 10 加了操作确认作为**人为拦截**，但它不是隔离：
  用户点了 y 之后命令就是在你本机真实执行的；`AutoApprover` 场景（长任务）下没有这层拦截
- **`search` 依赖外网**：网络不可用时该工具会返回错误（模型会据此改用其他工具）
- **MCP 工具**的说明仍然是每次请求全量带给模型的（只有 Skill 做到了按需加载）；
  远程工具一多，这层开销还会回来 —— 可以考虑把 MCP 工具也做成"按需披露"的两级结构
- **上下文压缩是有损的**：摘要会丢细节，所以阈值设在 90%，且只在"一轮结束"时触发
- 压缩后保留的是"最近 N 条原文 + 一份摘要"，**不保证与原对话逐字等价**
- **Skill 的 `loaded` 集合不感知上下文压缩**：如果某份手册的正文被压成了摘要、
  而 `loaded` 还记着"已加载"，模型就再也读不到正文了（`skill_check.py` 末尾留了这个思考题）
- Skill 的 frontmatter 解析器只支持 `key: value` 单行，放不了列表和多行文本
- **危险模式靠字符串匹配**：`scan_command()` 认不出 `find -delete`、
  `python -c "shutil.rmtree(...)"` 这类写法，也分不清"命令里的 rm"和"文本里的 rm"。
  它只用来提醒人，**不能当成安全边界**
- **拒绝只在"这一次调用"上生效**：模型下一轮还可以再请求同一个操作
  （重试是允许的，只是不能"换个工具绕过去"）—— 真正的防线仍然是用户不点 y
- **长任务模式的判据挡不住"奖励作弊"**：模型有 `bash` / `edit`，可以去改测试让判据变绿。
  目前只做到"用 `git status` 指出可疑改动并提示给人"，没有强制拦截
- 长任务的判据由 `shell=True` 执行，和 `bash` 工具是同样的信任假设：**判据命令必须可信**
- `run_goal` 用 `os.chdir()` 切换工作目录（退出时还原），是进程级全局状态，
  作为库被别的程序调用时不够礼貌
- **工作区边界是"防手滑"，不是"防恶意"**：模型有 `bash`，`cat /etc/passwd` 照样能读。
  真正的隔离要靠容器/沙箱，不是靠路径判断
- **工作区用的是全局状态**（`core/workspace.py` 里的模块级变量），
  和 `shared` 一样是教学取舍；生产里应由调用方显式传入
- **`drop_incomplete_round()` 偏保守**：历史停在 tool 结果上时也会被清掉。
  宁可多删一轮，也不发出会被 API 拒绝的历史 —— 代价是可能丢掉一个合法的尾部
- 暂未引入自动化测试框架，目前用八个验收脚本（`day1_check.py` / `tools_check.py` /
  `memory_check.py` / `mcp_check.py` / `skill_check.py` / `goal_check.py` /
  `approval_check.py` / `hardening_check.py`）保证核心行为

---

## 参考

- 项目结构与"渐进式示例"的组织方式，参考了 [Learn-OpenClaw](https://github.com/lasywolf/Learn-OpenClaw) 的教学思路
- 工具集的选择（read / write / edit / bash 为核心）参考了 pi-mono 关于最小 coding agent 的讨论
