"""Loop 引擎护栏：花费上限 + 卡死检测。

设计原则：
  - 计算型护栏（花费/卡死）在 generate.sh 中调用，不进 prompt
  - 推理型护栏（LLM-as-Judge）预留接口，暂 Mock
  - 所有护栏统一从此模块导出，单一入口
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# 花费上限（Guardrail：计算型/反馈）
# ============================================================================

# DeepSeek V3 定价（CNY/1M tokens）
# 实际价格请以官方为准，此处为近似值
PRICING = {
    "deepseek-chat":     {"input": 1.0, "output": 2.0},
    "deepseek-reasoner": {"input": 4.0, "output": 16.0},
}

DEFAULT_COST_CAP = float(os.environ.get("HARNESS_COST_CAP", "100"))  # 默认 100 元/批


@dataclass
class CostTracker:
    """累计花费追踪器。"""
    model: str = "deepseek-chat"
    input_tokens: int = 0
    output_tokens: int = 0
    generations: int = 0

    def record(self, prompt_chars: int, response_chars: int) -> None:
        """记录一次生成的花费（粗略估算：1 token ≈ 2 中文字符 ≈ 4 英文字符）。"""
        price = PRICING.get(self.model, PRICING["deepseek-chat"])
        in_tok = max(prompt_chars // 4, 1)
        out_tok = max(response_chars // 4, 1)
        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.generations += 1

    @property
    def cost(self) -> float:
        """累计花费（元）。"""
        price = PRICING.get(self.model, PRICING["deepseek-chat"])
        return (self.input_tokens / 1_000_000 * price["input"]
                + self.output_tokens / 1_000_000 * price["output"])

    @property
    def remaining(self) -> float:
        """剩余预算。"""
        return max(DEFAULT_COST_CAP - self.cost, 0)

    def within_budget(self) -> bool:
        return self.cost < DEFAULT_COST_CAP

    def summary(self) -> dict:
        return {
            "model": self.model,
            "generations": self.generations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_yuan": round(self.cost, 4),
            "remaining_yuan": round(self.remaining, 2),
            "cap_yuan": DEFAULT_COST_CAP,
        }


# ============================================================================
# 卡死检测（Guardrail：计算型/反馈）
# ============================================================================

@dataclass
class StallDetector:
    """检测"原地踏步"：连续 N 轮失败报告完全相同 → 判定卡死，终止重试。"""

    max_same_failures: int = 2          # 连续相同失败次数阈值
    _history: list[str] = field(default_factory=list)

    def check(self, verify_log: str) -> dict[str, Any]:
        """检查本轮是否卡死。

        返回 {"stalled": bool, "reason": str}
        当前为 Mock 实现：基于验证日志哈希检测完全相同的失败。
        后续可替换为 LLM 语义比对（推理型）。
        """
        h = hashlib.sha256(verify_log.encode()).hexdigest()
        self._history.append(h)
        if len(self._history) >= self.max_same_failures + 1:
            recent = self._history[-(self.max_same_failures + 1):]
            if len(set(recent)) == 1:
                return {"stalled": True, "reason": f"连续 {self.max_same_failures + 1} 次失败报告完全相同，判定卡死"}
        return {"stalled": False, "reason": ""}

    def reset(self) -> None:
        self._history.clear()


# ============================================================================
# 功能开关
# ============================================================================

import json as _json

FEATURES_FILE = os.environ.get("LOOP_FEATURES_FILE", "data/features.json")
DEFAULT_FEATURES = {
    "reasoning_review": False,       # LLM-as-Judge 代码审查
    "reasoning_style": False,        # LLM UI 还原度检查
    "langgraph": True,               # 多 Agent 协作
    "mumuspec": True,                # MumuSpec 六轮编译
    "cost_cap": True,                # 花费上限
    "stall_detect": True,            # 卡死检测
    "det_check": True,               # 确定性复跑
}


def load_features() -> dict:
    """读取功能开关。"""
    try:
        if os.path.exists(FEATURES_FILE):
            with open(FEATURES_FILE) as f:
                saved = _json.load(f)
            return {**DEFAULT_FEATURES, **saved}
    except Exception:
        pass
    return dict(DEFAULT_FEATURES)


def save_features(updates: dict) -> dict:
    """保存功能开关。"""
    current = load_features()
    current.update(updates)
    os.makedirs(os.path.dirname(FEATURES_FILE) or ".", exist_ok=True)
    with open(FEATURES_FILE, "w") as f:
        _json.dump(current, f, indent=2)
    return current


def is_enabled(feature: str) -> bool:
    return load_features().get(feature, False)


# ============================================================================
# 推理型护栏（LLM-as-Judge，真实调用）
# ============================================================================

def _call_reasoning(system: str, user: str) -> str:
    """调 DeepSeek 做推理型判断。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return '{"error": "DEEPSEEK_API_KEY 未设置"}'
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    payload = _json.dumps({
        "model": model, "temperature": 0, "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = __import__("urllib.request").Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with __import__("urllib.request").urlopen(req, timeout=60) as r:
        body = _json.loads(r.read())
    return body["choices"][0]["message"]["content"]


def reasoning_review(code_dir: str, spec_text: str) -> dict:
    """LLM-as-Judge 代码审查。检查可读性、最佳实践、隐含安全问题。

    需要启用功能开关: reasoning_review = true
    """
    if not is_enabled("reasoning_review"):
        return {"score": 0, "issues": [], "mock": True,
                "summary": "推理型代码审查未开启。在设置页启用 reasoning_review 开关。"}

    # 收集代码
    code_snippets = []
    for root, _, files in os.walk(code_dir):
        if "__pycache__" in root or "reports" in root:
            continue
        for fn in files:
            if fn.endswith((".py", ".html", ".js", ".css")):
                path = os.path.join(root, fn)
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                    if len(content) > 3000:
                        content = content[:1500] + "\n... (truncated) ...\n" + content[-1500:]
                    code_snippets.append(f"--- {os.path.relpath(path, code_dir)} ---\n{content}")
                except Exception:
                    pass

    if not code_snippets:
        return {"score": 0, "issues": ["无代码文件"], "summary": "未找到可审查的代码", "mock": False}

    system = """你是资深代码审查专家。审查以下代码，输出 JSON 格式：

{
  "score": 0-100,
  "issues": ["问题1", "问题2"],
  "summary": "一句话总结"
}

审查维度：
1. 可读性：命名、注释、结构
2. 最佳实践：错误处理、资源管理、DRY原则
3. 安全：注入风险、密钥泄露、不安全的API调用
4. 与需求对齐：代码是否覆盖了 spec 描述的功能点

只输出 JSON，不要解释。"""

    user = f"需求描述:\n{spec_text[:1000]}\n\n代码:\n" + "\n".join(code_snippets[:10])
    try:
        raw = _call_reasoning(system, user)
        result = _json.loads(raw)
        result["mock"] = False
        return result
    except Exception as e:
        return {"score": 0, "issues": [str(e)], "summary": "LLM 推理失败", "mock": False}


def reasoning_style_check(html_path: str, ui_spec: dict) -> dict:
    """LLM UI 还原度检查。比对 HTML 与 UI 规范的匹配度。

    需要启用功能开关: reasoning_style = true
    """
    if not is_enabled("reasoning_style"):
        return {"match": 0, "issues": [], "mock": True,
                "summary": "UI 还原度检查未开启。在设置页启用 reasoning_style 开关。"}

    if not os.path.exists(html_path):
        return {"match": 0, "issues": ["HTML 文件不存在"], "summary": "无法检查", "mock": False}

    try:
        with open(html_path, encoding="utf-8") as f:
            html = f.read()[:5000]
    except Exception:
        return {"match": 0, "issues": ["无法读取 HTML"], "summary": "读取失败", "mock": False}

    system = """你是 UI 设计审查专家。比对 HTML 页面与 UI 规范的匹配度，输出 JSON：

{
  "match": 0.0-1.0,
  "issues": ["不匹配1", "不匹配2"],
  "summary": "一句话"
}

检查点：
1. 颜色方案是否匹配 spec 中声明的配色
2. 布局结构是否合理（语义化、响应式）
3. 交互元素是否完整（按钮、表单、链接）

只输出 JSON。"""

    spec_text = _json.dumps(ui_spec, ensure_ascii=False) if isinstance(ui_spec, dict) else str(ui_spec)
    user = f"UI 规范:\n{spec_text[:1000]}\n\nHTML 源码:\n{html}"
    try:
        raw = _call_reasoning(system, user)
        result = _json.loads(raw)
        result["mock"] = False
        return result
    except Exception as e:
        return {"match": 0, "issues": [str(e)], "summary": "LLM 推理失败", "mock": False}


# ============================================================================
# 指标收集（ROI / 采纳率 / bug 率 / 返工率）
# ============================================================================

@dataclass
class RunMetrics:
    """单次运行的效率指标。"""
    case: str = ""
    lines_generated: int = 0
    lines_accepted: int = 0       # 通过验收的有效行数
    attempts: int = 1
    cost_yuan: float = 0.0
    generation_time_s: float = 0.0
    verify_time_s: float = 0.0
    first_pass: bool = False      # 是否一次通过


def collect_metrics(output_dir: str, cost_tracker: CostTracker,
                    attempts: int, gen_start: float, verify_start: float) -> RunMetrics:
    """从产物目录采集效率指标。"""
    m = RunMetrics()
    m.attempts = attempts
    m.cost_yuan = cost_tracker.cost
    m.generation_time_s = round(time.time() - gen_start, 1)

    # 统计产物代码行数（排除元数据/缓存）
    total = 0
    for root, _, files in os.walk(output_dir):
        for fn in files:
            if fn.endswith((".py", ".html", ".css", ".js", ".md")):
                try:
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        total += len(f.readlines())
                except Exception:
                    pass
    m.lines_generated = total
    if attempts == 1:
        m.first_pass = True
    m.lines_accepted = total  # 验收通过即全部接受
    return m


def metrics_summary(metrics_list: list[RunMetrics]) -> dict:
    """聚合多次运行的指标。"""
    if not metrics_list:
        return {}
    total = len(metrics_list)
    passed = sum(1 for m in metrics_list if m.lines_accepted > 0)
    first_pass = sum(1 for m in metrics_list if m.first_pass)
    return {
        "total_runs": total,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "first_pass_rate": round(first_pass / total * 100, 1) if total else 0,
        "total_cost_yuan": round(sum(m.cost_yuan for m in metrics_list), 2),
        "total_lines": sum(m.lines_generated for m in metrics_list),
        "avg_attempts": round(sum(m.attempts for m in metrics_list) / total, 1) if total else 0,
        "avg_time_s": round(sum(m.generation_time_s for m in metrics_list) / total, 1) if total else 0,
    }
