"""harness-5 共享小工具:读写、哈希、解析模型输出。

刻意保持极小、无第三方依赖,方便 Workshop 现场逐行讲。
"""
import hashlib
import json
import os
import re
from typing import Any

# harness-5 根目录(本文件在 harness-5/lib/ 下)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 模型输出的文件分块格式:<<<FILE: 相对路径>>> ... <<<ENDFILE>>>
FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def parse_file_blocks(text: str) -> dict[str, str]:
    """把模型输出解析成 {相对路径: 内容}。"""
    return {rel.strip(): content for rel, content in FILE_RE.findall(text)}


def sha256_file(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    return hashlib.sha256(read(path).encode("utf-8")).hexdigest()


# 任务档:环境变量 HARNESS_TASK 选择要跑哪个任务(默认 mathkit,保持向后兼容)。
# 每个任务 = 一份人读规格 + 一份 facts + 一份 constraints,其余流水线(Maker/Checker/Loop)完全复用。
_TASKS = {
    "mathkit": ("spec/spec.md", "spec/facts.json", "constraints.json"),
    "mall": ("spec/spec-mall.md", "spec/facts-mall.json", "constraints-mall.json"),
}


def load_spec() -> tuple[str, dict[str, Any], dict[str, Any]]:
    """按 HARNESS_TASK 返回 (spec_text, facts, constraints),供各层复用。"""
    task = os.environ.get("HARNESS_TASK", "mathkit")
    if task not in _TASKS:
        raise SystemExit(f"[common] 未知 HARNESS_TASK={task},可选: {', '.join(_TASKS)}")
    spec_rel, facts_rel, cons_rel = _TASKS[task]
    spec_text = read(os.path.join(ROOT, spec_rel))
    facts = load_json(os.path.join(ROOT, facts_rel))
    constraints = load_json(os.path.join(ROOT, cons_rel))
    return spec_text, facts, constraints
