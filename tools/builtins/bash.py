"""执行命令。抛异常会导致程序结束，抛错误码可以让模型知道哪里错误，从而可以针对性的去修"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = 30
MAX_LINES = 2000
MAX_BYTES = 30 * 1024


def bash(command: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """在工作目录下执行命令，返回 {stdout, stderr, exit_code}。

    注意：**非零退出码不是异常**——"命令跑起来了但结果失败"是正常结果，
    模型需要看到错误信息才能修。
    """
    try:
        result = subprocess.run(
            command,
            shell=True,               # 允许管道、重定向（见下方取舍讨论）
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"命令超时（{timeout} 秒）", "exit_code": -1}
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "exit_code": -1}

    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")

    # 截断时保留**最后** N 行 —— 因为报错信息通常在尾部
    lines = output.splitlines()
    if len(lines) > MAX_LINES:
        output = f"[输出只保留最后 {MAX_LINES} 行]\n" + "\n".join(lines[-MAX_LINES:])

    raw = output.encode("utf-8")
    if len(raw) > MAX_BYTES:
        output = "[输出只保留最后 30KB]\n" + raw[-MAX_BYTES:].decode("utf-8", errors="ignore")

    return {"stdout": output, "stderr": result.stderr or "", "exit_code": result.returncode}