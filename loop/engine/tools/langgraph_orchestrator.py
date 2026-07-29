"""LangGraph 多 Agent 协作编排器。

五 Agent 流水线：分析 → 生成 → 审查 → 测试 → 集成。
每个 Agent 是独立 LLM 调用，通过 FILE 协议传递产物。
不依赖外部 langgraph 库，纯 Python stdlib 实现。

用法:
  python loop/engine/tools/langgraph_orchestrator.py --name myapp --text "需求"
  python loop/engine/tools/langgraph_orchestrator.py --name myapp --mock
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # loop/engine/
LOOP_DIR = os.path.dirname(ENGINE_DIR)  # loop/
CASES_DIR = os.path.join(LOOP_DIR, "cases")

FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def call_llm(system: str, user: str) -> str:
    """调 DeepSeek，返回原始文本。"""
    if not API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")
    payload = json.dumps({
        "model": MODEL, "temperature": 0, "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        body = json.loads(r.read())
    return body["choices"][0]["message"]["content"]


def parse_files(text: str) -> dict[str, str]:
    """从 LLM 输出提取 FILE 块。返回 {相对路径: 内容}。"""
    return {rel.strip(): content for rel, content in FILE_RE.findall(text)}


# ═══════════════════════════════════════════════════════════════════
# Agent 定义
# ═══════════════════════════════════════════════════════════════════

AGENT_ANALYST = """你是需求分析师 Agent。接收用户需求，输出结构化的子任务拆解。

输出两份文件：

1. analysis.md — 需求分析报告：
   - 一句话概述
   - 核心功能点（3-7个）
   - 技术约束识别
   - 风险与假设

2. tasks.jsonl — 子任务清单（每行一个 JSON）：
   {"id":"T1","title":"xxx","desc":"xxx","deps":[],"files":["file1.py","file2.html"]}

输出格式：
<<<FILE: analysis.md>>>
内容
<<<ENDFILE>>>
<<<FILE: tasks.jsonl>>>
{"id":"T1","title":"...","desc":"...","deps":[],"files":["..."]}
{"id":"T2","title":"...","desc":"...","deps":["T1"],"files":["..."]}
<<<ENDFILE>>>"""


AGENT_BUILDER = """你是代码生成师 Agent。根据需求分析和子任务清单，逐个生成代码文件。

关键规则：
1. 每个子任务生成对应的代码文件
2. 所有文件遵循 tasks.jsonl 中声明的文件列表
3. 前后端代码协作一致（路由匹配、接口对齐）
4. 技术栈：Python Flask + 原生 HTML/CSS/JS + JSON 文件存储
5. 包含完整的 app.py、requirements.txt、README.md、测试文件

输出格式：每个文件一个 FILE 块
<<<FILE: app.py>>>
代码
<<<ENDFILE>>>
<<<FILE: requirements.txt>>>
Flask==3.0.*
<<<ENDFILE>>>
...（所有文件）"""


AGENT_REVIEWER = """你是代码审查师 Agent。检查 Builder 生成的代码，输出审查报告和修复建议。

审查维度：
1. 安全检查：eval/exec/os.system、密钥硬编码、注入风险
2. 代码质量：函数长度、命名规范、注释完整度
3. 功能完整性：是否覆盖所有子任务
4. 一致性：前后端接口是否对齐
5. 依赖合规：是否使用了 banned_deps

输出两份文件：
1. review.md — 审查报告（pass/warn/fail 逐条）
2. review-fixes.md — 修复建议（如有）

<<<FILE: review.md>>>
# 代码审查报告
## 安全检查：pass
## 代码质量：warn — app.py 第 45 行函数过长
## 功能完整性：pass
## 一致性：pass
## 依赖合规：pass
<<<ENDFILE>>>"""


AGENT_TESTER = """你是测试工程师 Agent。为生成的代码编写并执行测试。

1. 生成 tests/test_app.py（unittest）
2. 验证关键路由：首页 200、API 数据接口返回正确格式、404 处理
3. 生成验收报告

<<<FILE: tests/test_app.py>>>
import unittest
from app import app

class TestApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
    def test_index(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
    # ... 更多测试
<<<ENDFILE>>>
<<<FILE: test-report.md>>>
# 测试报告
- 测试用例数：N
- 通过：N
- 失败：0
<<<ENDFILE>>>"""


AGENT_INTEGRATOR = """你是集成协调师 Agent。汇总所有上游 Agent 产出，做出最终决策。

输入：
- analysis.md（需求分析）
- 所有代码文件（Builder 产出）
- review.md + review-fixes.md（审查结果）
- test-report.md（测试结果）

输出：
1. integration-report.md — 集成报告（pass/fail + 决策理由）
2. final/ 目录 — 最终交付物（完整可运行项目文件）

如果审查或测试未通过，给出具体修复指令回喂给 Builder。
如果全部通过，输出最终交付物。

<<<FILE: integration-report.md>>>
# 集成报告
- 状态：✅ PASS / ❌ FAIL
- Agent 协作总结
- 关键决策
- 下一步建议
<<<ENDFILE>>>
<<<FILE: README.md>>>
# 项目说明（最终版）
<<<ENDFILE>>>"""


AGENTS = [
    {"id": "A1", "name": "需求分析师", "system": AGENT_ANALYST,
     "desc": "接收需求 → 拆解子任务"},
    {"id": "A2", "name": "代码生成师", "system": AGENT_BUILDER,
     "desc": "分析报告 → 生成代码"},
    {"id": "A3", "name": "代码审查师", "system": AGENT_REVIEWER,
     "desc": "检查代码 → 审查报告"},
    {"id": "A4", "name": "测试工程师", "system": AGENT_TESTER,
     "desc": "生成测试 → 执行验证"},
    {"id": "A5", "name": "集成协调师", "system": AGENT_INTEGRATOR,
     "desc": "汇总结果 → 集成决策"},
]


# ═══════════════════════════════════════════════════════════════════
# Mock 模式
# ═══════════════════════════════════════════════════════════════════

def _mock_output(agent_id: str) -> str:
    """为每个 Agent 返回确定性 Mock 输出。"""
    if agent_id == "A1":
        return """<<<FILE: analysis.md>>>
# 需求分析

## 一句话概述
番茄钟计时器：25分钟专注 + 5分钟休息循环。

## 核心功能点
1. 倒计时显示（mm:ss 格式）
2. 开始/暂停切换
3. 重置按钮
4. 专注/休息模式自动切换
5. 计时结束声音提示

## 技术约束
- 后端: Python Flask
- 前端: 原生 HTML/CSS/JS
- 存储: 无持久化（纯前端状态）

## 风险
- 低风险，功能明确，技术成熟
<<<ENDFILE>>>
<<<FILE: tasks.jsonl>>>
{"id":"T1","title":"Flask 后端骨架","desc":"创建 app.py 提供首页路由和健康检查","deps":[],"files":["app.py","requirements.txt"]}
{"id":"T2","title":"前端计时器","desc":"HTML+JS 实现倒计时显示和控制","deps":["T1"],"files":["templates/index.html","static/css/style.css","static/js/timer.js"]}
{"id":"T3","title":"测试","desc":"单元测试验证路由和计时逻辑","deps":["T1","T2"],"files":["tests/test_timer.py"]}
<<<ENDFILE>>>"""

    elif agent_id == "A2":
        return """<<<FILE: app.py>>>
import os
from flask import Flask, render_template
app = Flask(__name__)
PORT = int(os.environ.get("PORT", 5000))
@app.route("/")
def index():
    return render_template("index.html")
@app.route("/health")
def health():
    return {"status": "ok"}
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
<<<ENDFILE>>>
<<<FILE: requirements.txt>>>
Flask==3.0.*
<<<ENDFILE>>>
<<<FILE: templates/index.html>>>
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>番茄钟</title><link rel="stylesheet" href="/static/css/style.css"></head><body><div class="container"><h1>番茄钟</h1><div class="timer" id="timer">25:00</div><div class="controls"><button id="startBtn">开始</button><button id="resetBtn">重置</button></div><div class="mode" id="mode">专注</div></div><script src="/static/js/timer.js"></script></body></html>
<<<ENDFILE>>>
<<<FILE: static/css/style.css>>>
*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#f5f5f5}.container{text-align:center;background:#fff;padding:40px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.1)}.timer{font-size:72px;font-weight:700;color:#e74c3c;margin:20px 0}.timer.break{color:#27ae60}.controls button{padding:12px 28px;margin:0 8px;border:0;border-radius:8px;font-size:16px;cursor:pointer}#startBtn{background:#e74c3c;color:#fff}#resetBtn{background:#bdc3c7;color:#333}.mode{font-size:14px;color:#999;margin-top:12px}
<<<ENDFILE>>>
<<<FILE: static/js/timer.js>>>
var total=25*60,remaining=total,running=false,mode='focus',timer=null,el=document.getElementById('timer'),modeEl=document.getElementById('mode'),startBtn=document.getElementById('startBtn'),resetBtn=document.getElementById('resetBtn');function update(){var m=Math.floor(remaining/60),s=remaining%60;el.textContent=(m<10?'0':'')+m+':'+(s<10?'0':'')+s;el.className='timer'+(mode==='break'?' break':'')}function tick(){if(!running)return;remaining--;update();if(remaining<=0){clearInterval(timer);if(mode==='focus'){mode='break';remaining=5*60;modeEl.textContent='休息';startBtn.textContent='开始';}else{mode='focus';remaining=25*60;modeEl.textContent='专注';startBtn.textContent='开始'}update();running=false;var a=new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACAf39/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gA==');a.play().catch(function(){})}}startBtn.onclick=function(){running=!running;startBtn.textContent=running?'暂停':'开始';if(running){timer=setInterval(tick,1000)}else{clearInterval(timer)}};resetBtn.onclick=function(){running=false;clearInterval(timer);mode='focus';remaining=25*60;modeEl.textContent='专注';startBtn.textContent='开始';update()};update()
<<<ENDFILE>>>
<<<FILE: README.md>>>
# 番茄钟

Python Flask 番茄钟计时器。25分钟专注 + 5分钟休息循环。

## 启动
```bash
pip install -r requirements.txt
python app.py
```
访问 http://localhost:5000
<<<ENDFILE>>>"""

    elif agent_id == "A3":
        return """<<<FILE: review.md>>>
# 代码审查报告

## 安全检查：pass
- 无 eval/exec/os.system 调用
- 无密钥硬编码
- 端口从环境变量读取

## 代码质量：pass
- app.py 简洁清晰
- 前端 JS 逻辑完整
- 命名规范

## 功能完整性：pass
- 3 个子任务全部实现
- 倒计时、控制、模式切换均已覆盖

## 一致性：pass
- 前后端路由匹配
- 接口对齐

## 依赖合规：pass
- 仅依赖 Flask
- 无 banned_deps
<<<ENDFILE>>>"""

    elif agent_id == "A4":
        return """<<<FILE: tests/test_timer.py>>>
import unittest
from app import app

class TestApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
    def test_index_ok(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
    def test_index_has_timer(self):
        r = self.client.get('/')
        self.assertIn(b'25:00', r.data)
    def test_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json, {'status': 'ok'})

if __name__ == '__main__':
    unittest.main()
<<<ENDFILE>>>
<<<FILE: test-report.md>>>
# 测试报告
- 测试用例数：3
- 通过：3
- 失败：0
- 状态：✅ 全部通过
<<<ENDFILE>>>"""

    elif agent_id == "A5":
        return """<<<FILE: integration-report.md>>>
# 集成报告

## 状态：✅ PASS

## Agent 协作总结
- A1 需求分析师：拆解为 3 个子任务（后端骨架、前端计时、测试）
- A2 代码生成师：生成 5 个文件，代码完整可运行
- A3 代码审查师：4 项检查全部通过
- A4 测试工程师：3 个测试用例全部通过

## 关键决策
- 采用纯前端计时逻辑，后端只提供页面渲染
- 声音提示用内嵌 base64 WAV，无需外部文件

## 下一步
产物已可交付。可直接 `python app.py` 启动。
<<<ENDFILE>>>"""

    return ""


# ═══════════════════════════════════════════════════════════════════
# 管道执行
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AgentResult:
    agent_id: str
    agent_name: str
    files: dict[str, str] = field(default_factory=dict)
    raw_output: str = ""
    status: str = "pending"   # pending | ok | failed


def run_pipeline(free_text: str, name: str, mock: bool = False,
                 max_retry: int = 2) -> list[AgentResult]:
    """执行多 Agent 协作管道。返回每个 Agent 的执行结果。"""
    results: list[AgentResult] = []
    context = f"项目名称: {name}\n\n需求:\n{free_text}"

    for agent in AGENTS:
        aid = agent["id"]
        aname = agent["name"]
        print(f"  [{aid}] {aname}...", end=" ", flush=True)
        result = AgentResult(agent_id=aid, agent_name=aname)

        for attempt in range(max_retry):
            try:
                if mock:
                    text = _mock_output(aid)
                else:
                    text = call_llm(agent["system"], context)
                result.raw_output = text
                result.files = parse_files(text)
                result.status = "ok"
                break
            except Exception as e:
                print(f"失败 (attempt {attempt+1}): {e}")
                result.status = "failed"
                if attempt == max_retry - 1:
                    print(f"  ⛔ [{aid}] 重试耗尽，管道中断")
                    results.append(result)
                    return results

        n_files = len(result.files)
        print(f"✓ {n_files} 文件")

        # 累积上下文：上游产出拼入下游输入
        for fname, content in result.files.items():
            if fname.endswith((".md", ".jsonl", ".json")):
                context += f"\n\n--- {aid} 产出: {fname} ---\n{content[:2000]}"

        results.append(result)

    return results


def write_output(name: str, results: list[AgentResult]) -> str:
    """将 Agent 管道产物写入 cases/<name>/langgraph/。"""
    out_dir = os.path.join(CASES_DIR, name, "langgraph")
    os.makedirs(out_dir, exist_ok=True)

    for r in results:
        agent_dir = os.path.join(out_dir, f"{r.agent_id}-{r.agent_name}")
        os.makedirs(agent_dir, exist_ok=True)
        for fname, content in r.files.items():
            path = os.path.join(agent_dir, fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        # 保存原始输出
        with open(os.path.join(agent_dir, "_raw.txt"), "w", encoding="utf-8") as f:
            f.write(r.raw_output)

    # 从 Builder (A2) 提取最终产物到 spec/
    builder = next((r for r in results if r.agent_id == "A2"), None)
    if builder and builder.files:
        spec_dir = os.path.join(CASES_DIR, name, "spec")
        os.makedirs(spec_dir, exist_ok=True)
        # 写 manifest.json
        manifest = {
            "archetype": "spec", "name": name, "title": name,
            "tech": {"framework": "flask", "language": "python"},
            "required_files": list(builder.files.keys()),
        }
        with open(os.path.join(spec_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        # 从 Tester (A4) 提取 acceptance
        tester = next((r for r in results if r.agent_id == "A4"), None)
        if tester:
            test_report = tester.files.get("test-report.md", "")
            tc_count = len([f for f in tester.files if f.endswith(".py") and "test" in f])
            acceptance = {
                "name": name, "ready_route": "/",
                "acceptance": [
                    {"id": "TC1", "type": "http_status", "route": "/", "expect": 200, "desc": "首页可访问"},
                    {"id": "TC2", "type": "unit_test", "test": "tests/test_app.py", "desc": "单测全绿"},
                ],
            }
            with open(os.path.join(spec_dir, "acceptance.json"), "w", encoding="utf-8") as f:
                json.dump(acceptance, f, ensure_ascii=False, indent=2)

    return out_dir


def main():
    import argparse
    ap = argparse.ArgumentParser(description="LangGraph 多 Agent 协作编排器")
    ap.add_argument("--name", required=True)
    ap.add_argument("--text")
    ap.add_argument("--input")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    free_text = ""
    if args.text:
        free_text = args.text
    elif args.input:
        with open(args.input, encoding="utf-8") as f:
            free_text = f.read()
    elif args.mock:
        free_text = "番茄钟计时器"
    if not free_text.strip():
        ap.error("需要 --text / --input / --mock")

    mode = "mock" if args.mock else "LLM"
    print("=" * 64)
    print(f"LangGraph 多 Agent 协作 | name={args.name} | mode={mode}")
    print("=" * 64)
    print(f"Agent 管道: {' → '.join(a['id']+' '+a['name'] for a in AGENTS)}")
    print()

    results = run_pipeline(free_text, args.name, mock=args.mock)
    out_dir = write_output(args.name, results)

    ok = sum(1 for r in results if r.status == "ok")
    print(f"\n📊 管道完成: {ok}/{len(AGENTS)} Agent 成功")
    for r in results:
        icon = "✅" if r.status == "ok" else "❌"
        print(f"  {icon} {r.agent_id} {r.agent_name}: {len(r.files)} 文件")
    print(f"\n产物: {out_dir}/")
    print(f"下一步: HARNESS_CASES={args.name} bash loop/engine/generate.sh")


if __name__ == "__main__":
    main()
