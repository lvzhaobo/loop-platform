"""Loop 统一检查注册表。

将散落在 verify.py / verify_ac.py / guardrails.py / run_model.py 中的所有检查
按 2×2 象限统一注册：前馈/后馈 × 计算型/推理型。

每个检查 = 元数据(id/name/quadrant/description) + 可选的 run() 函数。
generate.sh 执行时直接调用函数；Studio 通过 /api/checks 查询注册表展示。

设计原则：
  - 计算型：客观、可复现、便宜 → 自动执行
  - 推理型：主观、要模型、贵 → 接口预留，Mock 桩
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════════
# 象限定义
# ═══════════════════════════════════════════════════════════════════

QUADRANTS = {
    "inject-rule":         "前馈计算 — 生成前注入规则，机械确定",
    "inject-infer":        "前馈推理 — 生成前注入意图，需模型推断",
    "check-rule":          "后馈计算 — 生成后逐条检查，客观可复现",
    "check-infer":         "后馈推理 — 生成后 LLM-as-Judge，主观判断",
}


@dataclass
class Check:
    id: str
    name: str
    quadrant: str           # inject-rule | inject-infer | check-rule | check-infer
    description: str    
    category: str = ""      # structure | dependency | security | data | ui | runtime | test | reasoning
    run: Callable | None = None  # 可选：执行函数
    mock: bool = False
    auto: bool = True       # 能否自动判定
    active: bool = True     # 是否当前生效（条件规则根据 manifest 动态开关）


# ═══════════════════════════════════════════════════════════════════
# 注册表
# ═══════════════════════════════════════════════════════════════════

REGISTRY: list[Check] = []


def register(check: Check) -> Check:
    REGISTRY.append(check)
    return check


# ═══════════════════════════════════════════════════════════════════
# FF-C：前馈计算型（生成前注入 prompt）
# ═══════════════════════════════════════════════════════════════════

# ── Agent 指令 ──
register(Check(
    id="inject-01", name="AGENTS.md", quadrant="inject-rule",
    description="AGENTS.md 注入（最高优先级）：角色与边界、输出原则、失败处理、交互约定、安全红线。适用于所有生成",
    category="structure", active=True))

# ── 系统提示 ──
register(Check(
    id="inject-02", name="系统提示", quadrant="inject-rule",
    description="prompt.md 注入：角色定义、事实优先级、8 条强制要求、关键提醒。不含任何领域词汇",
    category="structure", active=True))

# ── 宪法 ──
register(Check(
    id="inject-03", name="全局硬约束", quadrant="inject-rule",
    description="constraints.json 注入：tech(框架/入口/端口)、base_required_files、banned_deps、banned_code_patterns、max_inline_style",
    category="structure", active=True))

# ── 通用基座规则 rules/base/ ──
register(Check(
    id="inject-04", name="安全基线", quadrant="inject-rule",
    description="rules/base/security.md 注入：禁止 eval/exec/os.system、密钥走环境变量、外部输入校验、依赖锁版本",
    category="security", active=True))
register(Check(
    id="inject-05", name="错误与日志", quadrant="inject-rule",
    description="rules/base/error-and-logging.md 注入：统一异常处理、日志分级、端口从 PORT 环境变量读取",
    category="structure", active=True))
register(Check(
    id="inject-06", name="测试策略", quadrant="inject-rule",
    description="rules/base/testing.md 注入：每端点 1正向+1 404、列表非空、用 unittest 不用 pytest",
    category="test", active=True))
register(Check(
    id="inject-07", name="文档规范", quadrant="inject-rule",
    description="rules/base/documentation.md 注入：README 含启动方式/路由说明/数据格式、docstring 要求",
    category="structure", active=True))

# ── 任务约束 rules/task/ ──
register(Check(
    id="inject-08", name="技术栈锁定", quadrant="inject-rule",
    description="rules/task/tech-stack.md 注入：Flask+Jinja2、JSON 无数据库、原生 HTML/CSS/JS、禁框架/CDN/ORM",
    category="structure", active=True))
register(Check(
    id="inject-09", name="目录骨架", quadrant="inject-rule",
    description="rules/task/structure.md 注入：app.py/requirements.txt/README.md + templates/ + static/ + tests/",
    category="structure", active=True))
register(Check(
    id="inject-10", name="编码规范", quadrant="inject-rule",
    description="rules/task/conventions.md 注入：路由 snake_case、数据加载唯一函数、CSS类优先、中文注释",
    category="structure", active=True))

# ── 语言规范 rules/lang/（条件生效）──
register(Check(
    id="inject-11", name="Python 规范", quadrant="inject-rule",
    description="rules/lang/python.md 注入（language=python 时生效）：类型标注、Flask 约定、安全红线",
    category="structure", active=True))
register(Check(
    id="inject-12", name="Java 规范", quadrant="inject-rule",
    description="rules/lang/java.md 注入（language=java 时生效，当前不生效）：Maven/Gradle、Spring Boot 约定",
    category="structure", active=False))

# ── 前端规范 rules/frontend/（含 HTML/CSS 时生效）──
register(Check(
    id="inject-13", name="HTML/CSS 规范", quadrant="inject-rule",
    description="rules/frontend/html-css.md 注入（产物含 HTML/CSS 时生效）：语义化、kebab-case、响应式、性能",
    category="ui", active=True))

# ── 用例规格 ──
register(Check(
    id="inject-14", name="数据模型", quadrant="inject-rule",
    description="cases/<name>/spec/data-model.md 注入：字段表、数据量、示例 JSON",
    category="data", active=True))
register(Check(
    id="inject-15", name="API 契约", quadrant="inject-rule",
    description="cases/<name>/spec/api-contract.md 注入：路由表、响应格式、状态码、404 约定",
    category="data", active=True))
register(Check(
    id="inject-16", name="UI 规范", quadrant="inject-rule",
    description="cases/<name>/spec/ui-spec.md 注入：配色、列表/详情结构、marker、字体层级",
    category="ui", active=True))
register(Check(
    id="inject-17", name="硬事实", quadrant="inject-rule",
    description="manifest.json/case.json 注入：字段/filterules/路由/函数名/marker/配色等硬性事实",
    category="data", active=True))

# ═══════════════════════════════════════════════════════════════════
# inject-infer + multi-agent：前馈推理型（需模型推断）
# ═══════════════════════════════════════════════════════════════════

register(Check(
    id="mumu-01", name="MumuSpec 六轮编译", quadrant="inject-infer",
    description="mumuspec_compiler.py R1-R6 Skill 调度器：需求采集→立项→锚定→设计→收口→契约提炼。Mock 模式可用",
    category="structure", active=True))
register(Check(
    id="multi-01", name="LangGraph 多 Agent", quadrant="inject-infer",
    description="langgraph_orchestrator.py 五 Agent 协作：分析→生成→审查→测试→集成。Mock 模式可用",
    category="structure", active=True))

register(Check(
    id="infer-01", name="风格推断", quadrant="inject-infer",
    description="（Mock）让 LLM 读需求自行推断设计风格/交互模式，而非完全按模板生成",
    category="ui", mock=True))

register(Check(
    id="infer-02", name="意图对齐", quadrant="inject-infer",
    description="（Mock）生成前用 LLM 解析需求文本的隐含意图，补全未明确表达的约束",
    category="reasoning", mock=True))

# ═══════════════════════════════════════════════════════════════════
# FB-C：后馈计算型（生成后自动检查）
# ═══════════════════════════════════════════════════════════════════

# ============================================================================
# FB-C：后馈计算型 — Spec 门禁 (verify_ac.py) 的断言原语
# 当前唯一生效的自动验收路径。generate.sh 固定走 verify_ac.py。
# ============================================================================

register(Check(id="FB-C-01", name="护栏：无禁用依赖", quadrant="check-rule",
    description="扫描 requirements.txt，禁止 django/sqlalchemy/react/vue/jQuery/Bootstrap 等",
    category="dependency"))
register(Check(id="FB-C-02", name="护栏：无危险调用", quadrant="check-rule",
    description="扫描所有 .py 文件，禁止 eval()/exec()/os.system()/subprocess/__import__/pickle.load",
    category="security"))
register(Check(id="FB-C-03", name="断言：file_exists", quadrant="check-rule",
    description="检查指定文件是否存在",
    category="structure"))
register(Check(id="FB-C-04", name="断言：text_contains", quadrant="check-rule",
    description="检查文件中是否包含指定字符串/正则",
    category="data"))
register(Check(id="FB-C-05", name="断言：text_absent", quadrant="check-rule",
    description="检查文件中是否不包含指定字符串（如确保不是列表+详情模式）",
    category="data"))
register(Check(id="FB-C-06", name="断言：http_status", quadrant="check-rule",
    description="启动服务后 GET 路由，验证返回状态码",
    category="runtime"))
register(Check(id="FB-C-07", name="断言：http_body_contains", quadrant="check-rule",
    description="启动服务后 GET 路由，验证响应体包含指定文本",
    category="runtime"))
register(Check(id="FB-C-08", name="断言：http_json_min", quadrant="check-rule",
    description="启动服务后 GET JSON 接口，验证数组长度 ≥ 指定值",
    category="runtime"))
register(Check(id="FB-C-09", name="断言：unit_test", quadrant="check-rule",
    description="运行 unittest，验证全部通过",
    category="test"))

# --- 护栏 ---
register(Check(id="FB-C-10", name="护栏：花费上限", quadrant="check-rule",
    description="每批生成累计花费 ≤ ¥100，超限自动终止",
    category="structure"))
register(Check(id="FB-C-11", name="护栏：卡死检测", quadrant="check-rule",
    description="连续 3 次失败报告完全相同 → 判定卡死，终止重试",
    category="structure"))
register(Check(id="FB-C-12", name="确定性：复跑比哈希", quadrant="check-rule",
    description="通过后复跑一次，比对产物文件 SHA256，检测非确定性漂移",
    category="structure"))

# ═══════════════════════════════════════════════════════════════════
# FB-R：后馈推理型（LLM-as-Judge）
# ═══════════════════════════════════════════════════════════════════

register(Check(
    id="judge-01", name="代码审查", quadrant="check-infer",
    description="（Mock）LLM-as-Judge：可读性、最佳实践、隐含安全问题",
    category="reasoning", mock=True))
register(Check(
    id="judge-02", name="UI 还原度", quadrant="check-infer",
    description="（Mock）截图 + 视觉模型比对 UI 与设计稿的还原度",
    category="ui", mock=True))
register(Check(
    id="judge-03", name="意图一致性", quadrant="check-infer",
    description="（Mock）LLM 比对生成产物与原始需求文本，判断是否覆盖所有功能点",
    category="reasoning", mock=True))


# ═══════════════════════════════════════════════════════════════════
# 查询 API
# ═══════════════════════════════════════════════════════════════════

def get_checks(quadrant: str | None = None, category: str | None = None) -> list[dict]:
    """按象限和/或分类筛选检查。结合功能开关动态计算 active 状态。"""
    # 读取功能开关（如果可用）
    features = {}
    try:
        from guardrails import load_features
        features = load_features()
    except ImportError:
        pass

    # 功能开关 → checker ID 映射
    feature_map = {
        "reasoning_review": "judge-01",
        "reasoning_style": "judge-02",
        "langgraph": "multi-01",
        "mumuspec": "mumu-01",
    }

    result = []
    for c in REGISTRY:
        if quadrant and c.quadrant != quadrant:
            continue
        if category and c.category != category:
            continue
        # 动态 active: 如果该检查有对应功能开关，以开关为准
        active = c.active
        for feat_key, check_id in feature_map.items():
            if c.id == check_id:
                active = features.get(feat_key, c.active)
                break
        result.append({
            "id": c.id, "name": c.name, "quadrant": c.quadrant,
            "quadrant_label": QUADRANTS.get(c.quadrant, c.quadrant),
            "description": c.description, "category": c.category,
            "mock": c.mock, "auto": c.auto, "active": active,
        })
    return result


def summary() -> dict:
    """返回注册表摘要统计。"""
    quadrants: dict[str, int] = {}
    for c in REGISTRY:
        quadrants[c.quadrant] = quadrants.get(c.quadrant, 0) + 1
    return {
        "total": len(REGISTRY),
        "by_quadrant": quadrants,
        "mocked": sum(1 for c in REGISTRY if c.mock),
        "auto": sum(1 for c in REGISTRY if c.auto),
    }
