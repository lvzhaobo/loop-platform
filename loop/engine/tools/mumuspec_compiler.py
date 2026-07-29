"""MumuSpec Skill 调度器：R1-R6 六轮 LLM 调用链。

将自由文本需求编译为 MumuSpec 14 文档体系，
最终提炼出 harness 引擎可用的契约三件套（spec.md + manifest.json + acceptance.json）。

用法:
  python loop/engine/tools/mumuspec_compiler.py --name myapp --text "需求描述"
  python loop/engine/tools/mumuspec_compiler.py --name myapp --input req.txt
  python loop/engine/tools/mumuspec_compiler.py --name myapp --mock  # 离线模式
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# ── 路径 ──
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # loop/engine/
LOOP_DIR = os.path.dirname(ENGINE_DIR)  # loop/
CASES_DIR = os.path.join(LOOP_DIR, "cases")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

DOC_NAMES = {
    "01": "01-writing-guidelines.md",
    "02": "02-elicitation.md",   "03": "03-proposal.md",
    "04": "04-prd.md",           "05": "05-user-stories.md",
    "06": "06-fsd.md",           "07": "07-nfr.md",
    "08": "08-architecture.md",  "09": "09-api-spec.md",
    "10": "10-data-model.md",    "11": "11-security.md",
    "12": "12-implementation-plan.md",
    "13": "13-test-strategy.md", "14": "14-traceability-matrix.md",
}

META_DOC_01 = """# Spec 写作总则

> 自动生成 by MumuSpec Skill 调度器

## 写作原则
- 每份文档有明确读者（人/AI/人+AI）
- 事实源唯一：API 契约（09）冻结字段名，下游统一引用
- 可验证：每条用户故事 AC 必须在 API 契约中找到可观测断言

## AI 生成声明
本文档体系由 MumuSpec Skill 调度器（R1-R6）自动生成。
人类应审查并确认关键决策点（立项、架构、安全）。
"""


# ═══════════════════════════════════════════════════════════════════
# LLM 调用
# ═══════════════════════════════════════════════════════════════════

def call_deepseek(system: str, user: str) -> str:
    if not API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        body = json.loads(r.read())
    return body["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════════
# Skill 定义（R1-R6）
# ═══════════════════════════════════════════════════════════════════

def skill_r1_elicit(free_text: str, name: str, prev: dict) -> tuple[str, str]:
    system = """你是需求分析师。根据用户提供的需求描述，撰写一份结构化的需求采集文档（02）。

要求：
1. 记录需求的原始来源和上下文
2. 识别关键利益相关者
3. 明确核心业务目标
4. 列出非功能性的隐含需求（性能/安全/可用性）

输出格式：
<<<FILE: 02-elicitation.md>>>
文档内容（Markdown 格式）
<<<ENDFILE>>>"""
    user = f"需求名称: {name}\n\n需求描述:\n{free_text}"
    return system, user


def skill_r2_propose(free_text: str, name: str, prev: dict) -> tuple[str, str]:
    system = """你是产品经理。基于需求采集文档，撰写立项提案（03）和产品需求文档 PRD（04）。

03 立项提案: 业务背景、价值主张、成功指标、风险
04 PRD: 功能范围、用户流程、验收条件

输出格式：
<<<FILE: 03-proposal.md>>>
文档内容
<<<ENDFILE>>>
<<<FILE: 04-prd.md>>>
文档内容
<<<ENDFILE>>>"""
    prev_doc = prev.get(DOC_NAMES["02"], "")
    user = f"需求名称: {name}\n\n需求采集:\n{prev_doc}\n\n原始需求:\n{free_text}"
    return system, user


def skill_r3_anchor(free_text: str, name: str, prev: dict) -> tuple[str, str]:
    system = """你是 API 架构师。把 PRD 中的能力拆成用户故事（05），同时定义 API 契约（09）。

关键约束：
- 每条用户故事的 AC 必须在 API 契约中找到可观测断言（状态码/字段/错误码）
- 字段名在 09 中冻结，下游所有文档（06/10/13）必须引用这些字段名
- 05 每条 US 带 AC 编号（AC-001, AC-002...）
- 09 包含路由、请求/响应格式、错误处理

输出格式：
<<<FILE: 05-user-stories.md>>>
文档内容
<<<ENDFILE>>>
<<<FILE: 09-api-spec.md>>>
文档内容（含 JSON 示例）
<<<ENDFILE>>>"""
    prev_04 = prev.get(DOC_NAMES["04"], "")
    user = f"需求名称: {name}\n\nPRD:\n{prev_04}\n\n原始需求:\n{free_text}"
    return system, user


def skill_r4_design(free_text: str, name: str, prev: dict) -> tuple[str, str]:
    system = f"""你是技术架构师。基于用户故事（05）和 API 契约（09），完成技术设计文档。

输出 5 篇：
06 FSD 功能规格: 功能清单 + 交互流程
07 NFR 非功能需求: 性能/安全/可用性指标
08 架构选型: 技术栈（Python Flask + JSON 文件存储 + 原生 HTML/CSS/JS）
10 数据模型: 字段定义（引用 09 中的字段名）+ 数据类型 + 约束
11 安全设计: 认证/授权/数据保护/安全红线

输出格式：
<<<FILE: 06-fsd.md>>>
内容
<<<ENDFILE>>>
<<<FILE: 07-nfr.md>>>
内容
<<<ENDFILE>>>
<<<FILE: 08-architecture.md>>>
内容
<<<ENDFILE>>>
<<<FILE: 10-data-model.md>>>
内容
<<<ENDFILE>>>
<<<FILE: 11-security.md>>>
内容
<<<ENDFILE>>>"""
    prev_05 = prev.get(DOC_NAMES["05"], "")
    prev_09 = prev.get(DOC_NAMES["09"], "")
    user = f"需求名称: {name}\n\n用户故事:\n{prev_05}\n\nAPI 契约:\n{prev_09}"
    return system, user


def skill_r5_close(free_text: str, name: str, prev: dict) -> tuple[str, str]:
    system = """你是项目经理。生成实施计划（12）、测试策略（13）和追溯矩阵（14）。

12 实施计划: 里程碑/交付物/时间线
13 测试策略: 把 05 中的 AC 映射为 TC（测试用例），标注可自动判定 vs 人工抽检
14 追溯矩阵: REQ → US → API → TC 四向映射表

输出格式：
<<<FILE: 12-implementation-plan.md>>>
内容
<<<ENDFILE>>>
<<<FILE: 13-test-strategy.md>>>
内容
<<<ENDFILE>>>
<<<FILE: 14-traceability-matrix.md>>>
内容（Markdown 表格格式）
<<<ENDFILE>>>"""
    prev_05 = prev.get(DOC_NAMES["05"], "")
    prev_09 = prev.get(DOC_NAMES["09"], "")
    user = f"需求名称: {name}\n\n用户故事:\n{prev_05}\n\nAPI 契约:\n{prev_09}"
    return system, user


def skill_r6_extract_contract(free_text: str, name: str, prev: dict) -> tuple[str, str]:
    system = """你是 Harness 引擎契约提炼师。从 MumuSpec 14 文档中提炼引擎可用的契约三件套。

只读以下关键文档: 06 (FSD), 07 (NFR), 09 (API), 10 (数据), 11 (安全), 13 (测试), 14 (追溯)

输出三个文件：

1. spec/spec.md: 一句话概述 + 核心交互 + 结构建议 + 非目标
2. spec/manifest.json: 严格 JSON，包含 archetype/name/title/tech/required_files
3. spec/acceptance.json: 严格 JSON，包含 name/ready_route/acceptance 数组

acceptance 数组中的断言类型（闭集）:
- file_exists: {file}
- text_contains: {file, needle}
- text_absent: {file, needle}
- http_status: {route, expect}
- http_body_contains: {route, needle}
- http_json_min: {route, min}
- unit_test: {test}
- manual: {}

每条 TC 必须可自动判定（manual 除外），且 TC 数量 >= 4。

输出格式（严格遵守，JSON 必须合法）：
<<<FILE: spec/spec.md>>>
内容
<<<ENDFILE>>>
<<<FILE: spec/manifest.json>>>
{"archetype":"spec","name":"...","title":"...","tech":{"framework":"flask","language":"python"},"required_files":["app.py","requirements.txt","README.md",...]}
<<<ENDFILE>>>
<<<FILE: spec/acceptance.json>>>
{"name":"...","ready_route":"/","acceptance":[{"id":"TC1","type":"http_status","route":"/","expect":200,"desc":"..."},{"id":"TC2",...}]}
<<<ENDFILE>>>"""
    # 只喂 AI 要读的 7 篇
    ai_keys = ["06", "07", "09", "10", "11", "13", "14"]
    ai_docs = "\n\n".join(
        f"--- {k} ---\n{prev.get(DOC_NAMES[k], '')}" for k in ai_keys
    )
    user = f"需求名称: {name}\n\n{ai_docs}"
    return system, user


SKILLS = [
    {"id": "R1", "name": "需求采集",     "fn": skill_r1_elicit},
    {"id": "R2", "name": "立项提案",     "fn": skill_r2_propose},
    {"id": "R3", "name": "锚定对齐",     "fn": skill_r3_anchor},
    {"id": "R4", "name": "技术设计",     "fn": skill_r4_design},
    {"id": "R5", "name": "收口",         "fn": skill_r5_close},
    {"id": "R6", "name": "契约提炼",     "fn": skill_r6_extract_contract},
]


# ═══════════════════════════════════════════════════════════════════
# 门禁校验
# ═══════════════════════════════════════════════════════════════════

def mumuspec_validate(cdir: str, name: str, docs: dict) -> tuple[bool, list[str]]:
    """检查 14 文档完整性和契约三件套合法性。返回 (pass, errors)。"""
    errors = []
    # 1. 14 文档完整性（每篇 > 50 字符）
    for doc_id, fname in DOC_NAMES.items():
        content = docs.get(fname, "")
        if doc_id == "01":
            continue  # 01 自动生成，不检查
        if len(content.strip()) < 50:
            errors.append(f"文档 {fname} 内容不足（{len(content.strip())} 字符）")

    # 2. 契约三件套存在 + JSON 合法
    for rel, label in [("spec/spec.md", "spec.md"), ("spec/manifest.json", "manifest.json"),
                       ("spec/acceptance.json", "acceptance.json")]:
        content = docs.get(rel, "")
        if not content.strip():
            errors.append(f"契约文件缺失: {label}")
        elif label.endswith(".json"):
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(f"{label} JSON 不合法: {e}")

    # 3. manifest 字段校验
    try:
        manifest = json.loads(docs.get("spec/manifest.json", "{}"))
        if manifest.get("archetype") != "spec":
            errors.append("manifest.archetype 必须为 'spec'")
        if not manifest.get("name"):
            errors.append("manifest.name 缺失")
        if not manifest.get("required_files"):
            errors.append("manifest.required_files 缺失或为空")
    except Exception:
        pass

    # 4. acceptance TC 数量 >= 4，可自动判定 >= 3
    try:
        acc = json.loads(docs.get("spec/acceptance.json", "{}"))
        acs = acc.get("acceptance", [])
        auto = sum(1 for a in acs if a.get("type") != "manual")
        if len(acs) < 4:
            errors.append(f"acceptance TC 数量不足: {len(acs)} < 4")
        if auto < 3:
            errors.append(f"可自动判定 TC 不足: {auto} < 3")
    except Exception:
        pass

    return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════════════════
# 四维评分（轻量版，完整版见 mumuspec_grade.py）
# ═══════════════════════════════════════════════════════════════════

def simple_grade(docs: dict) -> dict:
    """快速评分：文档填充率 + TC 覆盖。"""
    filled = sum(1 for k, v in docs.items()
                 if k.startswith("0") and len(v.strip()) >= 50)
    total_docs = 13  # 02-14
    pct = round(filled / total_docs * 100, 1)
    return {"filled": filled, "total": total_docs, "pct": pct,
            "grade": "A" if pct >= 80 else "B" if pct >= 60 else "C"}


# ═══════════════════════════════════════════════════════════════════
# Mock 模式
# ═══════════════════════════════════════════════════════════════════

def _run_mock(name: str) -> dict:
    """内置番茄钟样例，14 文档 + 契约三件套。"""
    docs = {}
    docs[DOC_NAMES["02"]] = f"# 需求采集: {name}\n\n用户需要一个番茄钟计时器。核心功能：25分钟专注计时 + 5分钟休息。要求界面简洁、一键操作、有声音提示。"
    docs[DOC_NAMES["03"]] = f"# 立项提案: {name}\n\n## 背景\n番茄工作法是广泛使用的时间管理方法。需要一个轻量 Web 工具。\n\n## 价值主张\n提升个人工作效率，零学习成本。\n\n## 风险\n低风险，功能明确，技术成熟。"
    docs[DOC_NAMES["04"]] = f"# PRD: {name}\n\n## 功能范围\n1. 25分钟倒计时\n2. 5分钟休息倒计时\n3. 开始/暂停/重置按钮\n4. 结束声音提示\n\n## 验收条件\n- 页面显示倒计时\n- 按钮可操作\n- 计时结束有提示"
    docs[DOC_NAMES["05"]] = f"# 用户故事: {name}\n\n## US-001 开始专注\n作为用户，我希望能点击开始按钮启动 25 分钟倒计时。\n\nAC-001: 页面默认显示 25:00\nAC-002: 点击开始后计时器开始倒数\n\n## US-002 休息模式\n作为用户，专注结束后自动切换到 5 分钟休息。\n\nAC-003: 计时归零后自动切换为 5:00\nAC-004: 结束时播放提示音"
    docs[DOC_NAMES["06"]] = f"# 功能规格: {name}\n\n## 功能清单\n1. 倒计时显示（mm:ss）\n2. 开始/暂停切换\n3. 重置按钮\n4. 专注/休息模式切换\n5. 计时结束声音警报\n\n## 交互流程\n打开页面 → 显示 25:00 → 点开始 → 倒计时 → 归零 → 自动切换 5:00 → 循环"
    docs[DOC_NAMES["07"]] = f"# NFR: {name}\n\n## 性能\n- 页面加载 < 1s\n- 计时精度 ±0.1s\n\n## 可用性\n- 移动端适配\n- 颜色区分专注（红）和休息（绿）"
    docs[DOC_NAMES["08"]] = f"# 架构选型: {name}\n\n- 后端: Python Flask\n- 前端: 原生 HTML/CSS/JS\n- 存储: 无持久化（纯前端状态）\n- 端口: PORT 环境变量"
    docs[DOC_NAMES["09"]] = f"# API 契约: {name}\n\n## GET /\n返回番茄钟页面（HTML）\n\n## GET /health\n返回 {{\"status\":\"ok\"}}"
    docs[DOC_NAMES["10"]] = f"# 数据模型: {name}\n\n无持久化数据。计时状态由前端 JS 管理。\n\n- `seconds`: int 剩余秒数\n- `running`: bool 是否运行中\n- `mode`: 'focus' | 'break'"
    docs[DOC_NAMES["11"]] = f"# 安全设计: {name}\n\n- 无用户输入，无注入风险\n- 端口从环境变量读取\n- 生产环境关闭 debug"
    docs[DOC_NAMES["12"]] = f"# 实施计划: {name}\n\n## 里程碑\n1. 静态页面 + 计时逻辑\n2. 样式美化 + 移动适配\n3. 声音提示 + 测试\n\n## 预估工时: 2天"
    docs[DOC_NAMES["13"]] = f"# 测试策略: {name}\n\n## TC-001 | AC-001 | http_body_contains | 页面包含 25:00\n## TC-002 | AC-002 | http_status | / 返回 200\n## TC-003 | AC-003 | text_contains | static/js/timer.js 含 setInterval\n## TC-004 | AC-004 | unit_test | tests/test_app.py"
    docs[DOC_NAMES["14"]] = f"# 追溯矩阵: {name}\n\n| REQ | US | TC | API |\n|-----|-----|-----|-----|\n| 专注计时 | US-001 | TC-001 | GET / |\n| 开始按钮 | US-001 | TC-002 | GET / |\n| 休息切换 | US-002 | TC-003 | - |\n| 声音提示 | US-002 | TC-004 | - |"

    # 契约三件套
    docs["spec/spec.md"] = f"# 需求规格: {name}\n\n## 一句话概述\n番茄钟计时器，25分钟专注 + 5分钟休息，支持开始/暂停/重置。\n\n## 核心交互\n用户打开页面看到倒计时，点击开始后计时，结束后自动切换模式并播放提示音。\n\n## 结构建议\n- 前端: 单页 HTML + JS 计时逻辑\n- 后端: Flask 提供 / 渲染页面\n- 测试: tests/test_timer.py"
    docs["spec/manifest.json"] = json.dumps({
        "archetype": "spec", "name": name, "title": "番茄钟",
        "tech": {"framework": "flask", "language": "python"},
        "required_files": ["app.py", "requirements.txt", "README.md",
                          "templates/index.html", "static/css/style.css",
                          "static/js/timer.js", "tests/test_timer.py"],
    }, ensure_ascii=False, indent=2)
    docs["spec/acceptance.json"] = json.dumps({
        "name": name, "ready_route": "/",
        "acceptance": [
            {"id": "TC1", "type": "http_status", "route": "/", "expect": 200, "desc": "首页可访问"},
            {"id": "TC2", "type": "http_body_contains", "route": "/", "needle": "25:00", "desc": "默认显示 25:00"},
            {"id": "TC3", "type": "text_contains", "file": "static/js/timer.js", "needle": "setInterval", "desc": "使用 setInterval 计时"},
            {"id": "TC4", "type": "text_absent", "file": "app.py", "needle": "list_marker", "desc": "不是列表站"},
            {"id": "TC5", "type": "file_exists", "file": "static/js/timer.js", "desc": "计时脚本存在"},
            {"id": "TC6", "type": "unit_test", "test": "tests/test_timer.py", "desc": "计时逻辑单测"},
            {"id": "AC1", "type": "manual", "desc": "结束时播放声音提示，人工确认"},
        ],
    }, ensure_ascii=False, indent=2)
    return docs


# ═══════════════════════════════════════════════════════════════════
# 主调度
# ═══════════════════════════════════════════════════════════════════

def write_docs(name: str, docs: dict) -> str:
    """将 docs 字典写入 cases/<name>/mumuspec/ 和 cases/<name>/spec/。"""
    cdir = os.path.join(CASES_DIR, name)
    mumu_dir = os.path.join(cdir, "mumuspec")
    spec_dir = os.path.join(cdir, "spec")
    os.makedirs(mumu_dir, exist_ok=True)
    os.makedirs(spec_dir, exist_ok=True)

    for fname, content in docs.items():
        if fname.startswith("spec/"):
            path = os.path.join(cdir, fname)
        else:
            path = os.path.join(mumu_dir, fname)
        # JSON 文件规范化
        if fname.endswith(".json"):
            try:
                obj = json.loads(content)
                content = json.dumps(obj, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return cdir


def run_pipeline(free_text: str, name: str, mock: bool = False) -> dict:
    """执行 MumuSpec 六轮 Skill 调度。

    返回 docs 字典: { "01-xxx.md": content, ..., "spec/manifest.json": ... }
    """
    docs: dict[str, str] = {}
    docs[DOC_NAMES["01"]] = META_DOC_01

    if mock:
        print(f"[mumuspec] 离线 mock 模式，使用内置番茄钟样例")
        return _run_mock(name)

    print(f"[mumuspec] 真实 LLM 模式，6 轮 Skill 调度开始")
    for skill in SKILLS:
        sid = skill["id"]
        print(f"  {sid} {skill['name']}...", end=" ", flush=True)
        system, user = skill["fn"](free_text, name, docs)
        try:
            text = call_deepseek(system, user)
        except Exception as e:
            print(f"失败: {e}")
            raise
        blocks = {rel.strip(): content for rel, content in FILE_RE.findall(text)}
        for fname, content in blocks.items():
            docs[fname] = content
        new_keys = [k for k in blocks if k not in docs or k in blocks]
        print(f"✓ 产出 {len(blocks)} 个文件")

    # 门禁校验
    ok, errors = mumuspec_validate("", name, docs)
    if not ok:
        print(f"\n⚠️  门禁未通过 ({len(errors)} 个问题):")
        for e in errors:
            print(f"    - {e}")
    else:
        print(f"\n✅ 门禁通过")

    # 评分
    grade = simple_grade(docs)
    print(f"📊 文档填充率: {grade['filled']}/13 ({grade['pct']}%)  评级: {grade['grade']}")

    return docs


def main():
    import argparse
    ap = argparse.ArgumentParser(description="MumuSpec Skill 调度器")
    ap.add_argument("--name", required=True, help="用例名称")
    ap.add_argument("--text", help="自由文本需求")
    ap.add_argument("--input", help="从文件读取需求")
    ap.add_argument("--mock", action="store_true", help="离线 mock 模式")
    args = ap.parse_args()

    free_text = ""
    if args.text:
        free_text = args.text
    elif args.input:
        with open(args.input, encoding="utf-8") as f:
            free_text = f.read()
    elif args.mock:
        free_text = "番茄钟"

    if not free_text.strip():
        ap.error("需要 --text 或 --input 或 --mock")

    print("=" * 64)
    print(f"MumuSpec Skill 调度器 | name={args.name} | mode={'mock' if args.mock else 'LLM'}")
    print("=" * 64)

    docs = run_pipeline(free_text, args.name, mock=args.mock)
    cdir = write_docs(args.name, docs)

    # 统计
    mumu_count = sum(1 for k in docs if k.startswith("0"))
    print(f"\n[mumuspec] 已写 {cdir}/")
    print(f"  mumuspec/: {mumu_count} 文档")
    has_spec = all(k in docs for k in ["spec/spec.md", "spec/manifest.json", "spec/acceptance.json"])
    if has_spec:
        acc = json.loads(docs["spec/acceptance.json"])
        tc = len(acc["acceptance"])
        auto = sum(1 for a in acc["acceptance"] if a.get("type") != "manual")
        print(f"  spec/: 契约三件套 ({tc} 条 TC, {auto} 可自动判定)")
    print(f"\n🎉 MumuSpec 编译完成")
    print(f"   下一步: bash loop/pipeline/run.sh 或 HARNESS_CASES={args.name} bash loop/engine/generate.sh")


if __name__ == "__main__":
    main()
