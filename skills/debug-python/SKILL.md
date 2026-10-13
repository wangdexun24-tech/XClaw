---
name: debug-python
description: 排查 Python 报错和异常行为。当用户贴出 Traceback、说程序报错、崩溃、结果不对，或要求定位 bug 根因时使用。
---

# Python 报错排查流程

## 第一步：读 Traceback，从下往上

1. **最后一行是错误类型和消息**：`KeyError: 'name'`、`TypeError: ... missing 1 required positional argument`
2. **倒数第二段是出错位置**：文件名 + 行号，通常指向**你自己的代码**（不要盯着标准库或第三方库的行）
3. 一路往上看调用链，找到**你自己的代码第一次出现**的那一帧

## 第二步：区分"我的错"和"上游的错"

| 现象 | 大概率原因 |
|---|---|
| `ModuleNotFoundError` | 依赖没装，或跑错了虚拟环境 |
| `TypeError: missing ... argument` | 调用处少传/多传了参数（参数名拼错也算） |
| `KeyError` | 字典没有这个 key，该用 `.get()` 或先 `in` 判断 |
| `AttributeError: 'NoneType'` | 某处返回了 None 没检查 |
| `FileNotFoundError` | 路径错，或 cwd 和你想的不是一个地方 |
| `JSONDecodeError` | 拿到的根本不是 JSON（可能是 HTML 错误页或空字符串） |

## 第三步：验证，不要猜

1. **必须实际运行**：先用 `read` 看代码，再用 `bash` 跑一遍复现
2. 复现不了就先想办法复现 —— **能稳定复现的 bug 才是好 bug**
3. 假设 → 做最小验证 → 再改。**不要在没验证的情况下改代码**

## 第四步：报告

```
## 根因
`path/file.py:42` —— 一句话说清为什么会这样

## 证据
实际运行的命令 + 输出

## 修改建议
最小改动方案；如果还有别的改法，说明各自的取舍
```

## 禁忌

- 不要凭"看起来像"就下结论，必须跑一遍
- 不要一次改十处 —— 那样即使好了，也不知道是哪一处起的作用
