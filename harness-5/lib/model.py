"""harness-5 · 【Maker(生成器)】—— Loop 中"写"的那一半。

模型层:一个函数 generate(),两种模式。

  - real  :调用 DeepSeek,按 prompt + 约束 + spec + facts 生成;失败反馈会拼进 user。
  - sample:离线确定性生成器,不烧额度。为了在无网络/无 key 时也能演示 Loop,
            它在【第 1 次尝试】故意写一个有 bug 的 factorial(factorial(0) 返回 0),
            从【第 2 次尝试】起产出完全正确的版本 —— 于是 L2 的循环能被直观看到:
            attempt1 验收失败 → 回喂 → attempt2 修好。

环境变量:
  HARNESS_MODE=real|sample (默认 sample,开箱即用)
  DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
  HARNESS_TEMPERATURE (默认 0)  HARNESS_SEED (默认 42)
"""
import json
import os
import sys
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
import observ  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

MODE = os.environ.get("HARNESS_MODE", "sample")
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.environ.get("HARNESS_TEMPERATURE", "0"))
SEED = int(os.environ.get("HARNESS_SEED", "42"))

# ---- sample 模式下内置的两份产物(教学用:先错后对) ----

_CORRECT = '''\
"""mathkit —— 由 harness-5 生成(sample 正确版)。"""


def add(a, b):
    return a + b


def is_prime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def factorial(n):
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
'''

# 与 _CORRECT 仅 factorial 不同:base 写错,导致 factorial(0)=0、factorial(5)=0
_BUGGY = _CORRECT.replace(
    "def factorial(n):\n    result = 1\n    for i in range(2, n + 1):\n        result *= i\n    return result\n",
    "def factorial(n):\n    result = 0  # BUG: 0 的阶乘应为 1\n    for i in range(2, n + 1):\n        result *= i\n    return result\n",
)


def build_prompt(
    spec_text: str,
    facts: dict[str, Any],
    constraints: dict[str, Any],
    feedback: str | None,
) -> tuple[str, str]:
    """把 spec + facts + 约束 + (可选)失败反馈 拼成给模型的完整上下文。"""
    sys_parts = [
        "你是严谨的代码生成器。只输出文件,不要解释、不要 markdown 围栏。",
        "每个文件用如下格式输出:\n<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>",
        "\n===== 规格(人读) =====\n" + spec_text,
        "\n===== 唯一事实源 facts.json(不得违反) =====\n"
        + json.dumps(facts, ensure_ascii=False, indent=2),
        "\n===== 硬约束 constraints.json =====\n"
        + json.dumps(constraints, ensure_ascii=False, indent=2),
        "\n必须输出文件: " + facts["module"],
    ]
    user = "请依据以上约束与规格,生成 " + facts["module"] + " 的完整实现。"
    if feedback:
        user += "\n\n上一轮验收失败,以下是失败报告,请只修复失败项并重新输出完整文件:\n" + feedback
    return "".join(sys_parts), user


def call_deepseek(system: str, user: str) -> str:
    if not API_KEY:
        sys.exit("[model] 缺少 DEEPSEEK_API_KEY(请 source .env,或用 HARNESS_MODE=sample 离线)")
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "seed": SEED,
        "max_tokens": 4096,
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    usage = data.get("usage") or {}
    observ.emit(
        "llm.call",
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
    return data["choices"][0]["message"]["content"]


def generate(
    out_dir: str,
    spec_text: str,
    facts: dict[str, Any],
    constraints: dict[str, Any],
    attempt: int = 1,
    feedback: str | None = None,
) -> list[str]:
    """生成产物到 out_dir,返回写入的文件相对路径列表。

    attempt: 第几次尝试(从 1 开始)。sample 模式据此决定"先错后对"。
    feedback: 上一轮失败报告(real 模式拼进 prompt;sample 模式忽略内容,只看 attempt)。
    """
    module = facts["module"]
    # 埋点上下文:第 1 次尝试开一条新链路,后续尝试复用同一 trace_id。
    observ.set_context(mode=MODE, attempt=attempt)
    if attempt <= 1 or observ.current("trace_id") is None:
        observ.new_trace(str(facts.get("task") or "mathkit"))
    if MODE == "sample":
        # HARNESS_SAMPLE_STUCK=1:永远产出 BUGGY(模拟"模型怎么修都修不好"),
        # 用于演示 L3 护栏(迭代上限 / 卡死检测)被触发。
        stuck = os.environ.get("HARNESS_SAMPLE_STUCK") == "1"
        is_buggy = attempt <= 1 or stuck
        # mall 任务:多文件产物(app.py + 模板 + products.json),素材在 lib/sample_mall.py。
        if facts.get("task") == "mall":
            import sample_mall  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
            blocks = sample_mall.files(is_buggy)
            for rel, c in blocks.items():
                common.write(os.path.join(out_dir, rel), c)
            tag = "BUGGY(7条)" if is_buggy else "CORRECT(8条)"
            print(f"[model] sample 生成 mall 产物 (attempt={attempt}, {tag}, {len(blocks)} 个文件)")
            return list(blocks.keys())
        content = _BUGGY if is_buggy else _CORRECT
        common.write(os.path.join(out_dir, module), content)
        print(f"[model] sample 生成 {module} (attempt={attempt}, {'BUGGY' if is_buggy else 'CORRECT'})")
        return [module]

    system, user = build_prompt(spec_text, facts, constraints, feedback)
    text = call_deepseek(system, user)
    blocks = common.parse_file_blocks(text)
    if not blocks:
        sys.exit("[model] 未解析到任何文件,模型输出不符合格式")
    for rel, content in blocks.items():
        common.write(os.path.join(out_dir, rel), content)
        print(f"[model] real 写入 {rel}")
    return list(blocks.keys())
