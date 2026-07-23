"""Spec 编译层(Phase 1):自由文本需求 → LLM → spec 三件套 + case.meta.json → 合规 case。

上游把「模糊的自然语言需求」编译成「结构化、可被 compile_spec 解析的 spec 三件套」,
下游全部沿用现有确定性链路(compile_spec 派生 → case.json → build_schema → run_model → verify)。
LLM 只负责这一步「模糊 → 结构化」,越往下越确定,漂移在门禁处被挡住。

流程:
    自由文本
      │  call_deepseek(严格格式提示)          ← 唯一的「不确定」步骤
      ▼
    spec/data-model.md + spec/api-contract.md + spec/ui-spec.md + case.meta.json
      │  compile_spec.derive()                 ← 确定性派生规格字段
      ▼
    cases/<name>/case.json (= meta + 派生规格字段)
      │  compile_spec.py <name> --check        ← 门禁1:round-trip 一致
      │  contract_gate()                        ← 门禁2:契约非退化(能真正约束生成)
      ▼
    ✅ 合规 case,可直接喂给 run_model / orchestrator

用法:
    # 离线自证(不烧额度):用内置 recipe 领域跑通整条链路
    python harness-4/tools/spec_compiler.py --name recipe --mock

    # 真实 LLM:把一句话/一段话编译成契约
    source .env
    python harness-4/tools/spec_compiler.py --name jobs --text "我要一个招聘网站,首页展示职位卡片,点进去看职位详情"
    python harness-4/tools/spec_compiler.py --name jobs --input req.txt

    # Spec 形态(单页交互工具,不是列表/详情站):产出 spec.md + manifest.json + acceptance.json
    #   下游不走 compile_spec.derive/contract_gate,而是 acceptance_gate + run_model(Spec 形态)+ verify_ac
    python harness-4/tools/spec_compiler.py --name pomodoro --archetype spec --mock            # 离线自证
    python harness-4/tools/spec_compiler.py --name pomodoro --archetype spec --text "番茄钟"    # 真实 LLM
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compile_spec  # noqa: E402  复用确定性派生
import run_model     # noqa: E402  复用 DeepSeek 调用与文件块解析

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# case.json 里属于「代码结构/构建约定」的非规格字段,必须由 meta 提供
META_KEYS = ("name", "title", "data_file", "loader_function",
             "route_functions", "needs_images", "image_field", "extra_required_files")
# 五条标准路由(api-contract 必须齐全,verify 依赖)
STD_ROUTES = ("list", "detail_sample", "api_list", "api_detail_ok", "api_detail_missing")

# Spec 形态:acceptance.json 允许的断言原语闭集(须与 verify_ac.py 一致)→ 每型必填键
SPEC_AC_TYPES = {
    "file_exists": ("file",),
    "text_contains": ("file", "needle"),
    "text_absent": ("file", "needle"),
    "http_status": ("route", "expect"),
    "http_body_contains": ("route", "needle"),
    "http_json_min": ("route", "min"),
    "unit_test": (),
    "manual": (),
}


# ---------------------------------------------------------------- 提示词
def build_prompt(free_text, name):
    """教 LLM 输出「严格可被 compile_spec 解析」的三件套 + meta。格式差一点都会被门禁挡住。"""
    return f"""你是 Spec 编译器。把下面的自由文本需求,编译成一套**结构化规格文件**,供确定性代码生成器使用。

需求原文:
\"\"\"{free_text}\"\"\"

目标用例代号(entity 复数请据此取英文): {name}

必须输出且只输出以下 4 个文件,用如下格式(不要任何解释、不要 markdown 围栏):
<<<FILE: 相对路径>>>
文件内容
<<<ENDFILE>>>

【文件1: spec/data-model.md】—— 数据模型,唯一事实源
- 必须有一行: `- 实体(entity):\\`<英文单数标识符>\\``
- 必须有一行: `- min_items:<正整数>`(建议 6~10)
- 必须有一个表格,表头**逐字**为: | 字段 | 类型 | 必填 | 约束 | 说明 |
  - 第一行必须是 id,类型 int,必填 是,约束 `sequential_from=1`
  - 必须含一个封面/图片字段(string),用于 image_field
  - 约束列用空格分隔的 key=value:可选 max_len=N / min_len=N / gt=N / gte=N / lt=N / lte=N;无约束留空
  - 类型只用 int / number / string
  - 至少 6 个字段,含一个 min_len>=10 的长文本字段(详情正文;具体长度由你根据需求加工拆解,不强制冗长)

【文件2: spec/api-contract.md】—— 路由契约
- 必须有一个表格,表头**逐字**为: | 名称 | 路径 |
- 且**必须且只有**这五行(路径里的实体复数替换成你取的英文复数):
  | list               | /                        |
  | detail_sample      | /<单数>/1                |
  | api_list           | /api/<复数>              |
  | api_detail_ok      | /api/<复数>/1            |
  | api_detail_missing | /api/<复数>/9999         |

【文件3: spec/ui-spec.md】—— UI 规范
- 必须有一个表格,表头**逐字**为: | 键 | 值 |
- 且必须含这四行:
  | list_marker        | <kebab-case,如 xxx-card>                       |
  | list_card_children | <逗号分隔的 4 个 class,均以 list_marker 前缀开头> |
  | detail_markers     | <逗号分隔的 2 个详情页 class,如 btn-xxx, xxx-body> |
  | required_colors    | <逗号分隔的 2 个十六进制色,如 #e67e22, #27ae60>  |
- 【关键·不要丢约束】若需求原文明确要求页面出现某段**字面文案**(品牌名/日期/版本号/口号/指定字样,
  如「页面要显示 Loop-20260721」),必须再加一行,把这些文案**逐字照抄**(不得改写/翻译/意译):
  | must_contain_text  | <逗号分隔的字面文案,逐字照抄需求原文> |
  若需求没有此类字面文案要求,则**整行省略**(不要写空值、不要编造)。

【文件4: case.meta.json】—— 非规格的构建约定(严格 JSON,不要注释)
{{
  "name": "{name}",
  "title": "<一句话中文标题>",
  "data_file": "data/<复数>.json",
  "loader_function": "load_<复数>",
  "route_functions": ["<单数>_list", "<单数>_detail", "api_<复数>", "api_<单数>_detail"],
  "needs_images": true,
  "image_field": "<data-model 里那个封面字段名>",
  "extra_required_files": ["data/<复数>.json"]
}}
"""


# ---------------------------------------------------------------- 提示词(Spec 形态)
def build_prompt_spec(free_text, name):
    """教 LLM 把自由文本编译成 Spec 形态三件套:spec.md + manifest.json + acceptance.json。
    acceptance 只能用 verify_ac 支持的断言原语闭集;TC 引用的文件必须列进 manifest.required_files。"""
    return f"""你是 Spec 编译器。把下面的自由文本需求,编译成一套**结构化规格**,
供代码生成器生成一个「单页交互式 Web 工具」——它围绕某个**核心交互**(计时/计算/编辑/绘制/播放等),
**不是**「列表页 + 详情页 + 数据集」那套内容站。

需求原文:
\"\"\"{free_text}\"\"\"

用例代号: {name}

必须输出且只输出以下 3 个文件,用如下格式(不要任何解释、不要 markdown 围栏):
<<<FILE: 相对路径>>>
文件内容
<<<ENDFILE>>>

【文件1: spec/spec.md】—— 需求规格(给生成器读的中文说明)
- 写清:一句话概述、核心交互(用户能做什么)、结构建议、非目标。
- 结构建议里**点明哪些纯逻辑抽成独立 Python 模块**(如 `xxx_core.py`,纯函数、无副作用),便于单测。
- 后端 Flask 很薄:`app.py` 渲染首页(通常 `/`)+ 必要时少量 JSON 接口;核心交互在前端 JS。
- 明确「非目标」:不是内容列表站,没有列表页/详情页/数据集/图鉴。

【文件2: spec/manifest.json】—— 构建约定(严格 JSON,不要注释)
{{
  "archetype": "spec",
  "name": "{name}",
  "title": "<一句话中文标题>",
  "tech": {{"framework": "flask", "language": "python", "port_env": "PORT"}},
  "required_files": ["app.py", "requirements.txt", "README.md", "templates/index.html", "static/js/<名>.js", "static/css/style.css", "<名>_core.py", "tests/test_<名>.py"]
}}
- required_files 必须列全「验收标准里引用到的每一个文件」,且至少含 `app.py`。

【文件3: spec/acceptance.json】—— 验收标准 TC/AC(门禁逐条自动执行,严格 JSON)
{{
  "name": "{name}",
  "ready_route": "/",
  "acceptance": [ ... ]
}}
- acceptance 至少 5 条,其中**可自动判定的至少 3 条**(除 manual 外)。
- 每条形如 {{"id":"TC1","type":"<类型>",...,"desc":"<中文说明>"}}。
- type **只能**用下面这些(闭集),对应字段必须齐全:
  - file_exists        {{"file":"相对路径"}}
  - text_contains      {{"file":"相对路径","needle":"子串"}}   (可加 "regex":true)
  - text_absent        {{"file":"相对路径","needle":"子串"}}
  - http_status        {{"route":"/","expect":200}}
  - http_body_contains {{"route":"/","needle":"页面应出现的文案"}}   (可加 "status":200)
  - http_json_min      {{"route":"/api/x","min":3}}
  - unit_test          {{"test":"tests/test_xxx.py"}}
  - manual             {{"desc":"需人工抽检的主观项"}}
- file_exists / text_* / unit_test 引用的文件**必须**出现在 manifest.required_files 里。
- 至少包含:1 条 http_status 首页返回 200;1 条 http_body_contains 校验核心文案;
  1 条 unit_test 校验抽出的纯逻辑;建议再加 1 条 text_absent 断言「不是列表站」(如 app.py 不含 detail_markers)。
- **若需求原文点名要求页面出现某段字面文案(如版本号/口号/日期),必须为每段这样的文案各加一条
  http_body_contains 断言(needle 逐字照抄,不得改写/翻译/省略),确保它真出现在渲染后的页面上。**
- 只写**客观可判定**的断言;主观效果(声音/动画/美观)一律用 manual。
"""


# ---------------------------------------------------------------- 内置离线样例(自证链路,不烧额度)
MOCK = {
    "recipe": {
        "spec/data-model.md": """# 数据模型:`data/recipes.json` 为数组,每个元素结构如下

> 本文件是「数据模型」的唯一事实源;case.json 的数据字段由 compile_spec 从下表派生。

- 实体(entity):`recipe`
- min_items:6

| 字段    | 类型   | 必填 | 约束              | 说明               |
|---------|--------|------|-------------------|--------------------|
| id      | int    | 是   | sequential_from=1 | 唯一,从 1 递增     |
| title   | string | 是   | max_len=40        | 菜名               |
| chef    | string | 是   |                   | 主厨               |
| cuisine | string | 是   |                   | 菜系:川/粤/日...   |
| minutes | int    | 是   | gt=0              | 烹饪时长(分钟)   |
| cover   | string | 是   |                   | 封面图 `static/img/<id>.png` |
| summary | string | 是   | max_len=100       | 一句话简介         |
| steps   | string | 是   | min_len=10        | 详细做法正文       |
""",
        "spec/api-contract.md": """# 接口契约(路由 / 响应 / 状态码)

## 路由清单(compile_spec 从此表派生 case.json.routes)
| 名称               | 路径              |
|--------------------|-------------------|
| list               | /                 |
| detail_sample      | /recipe/1         |
| api_list           | /api/recipes      |
| api_detail_ok      | /api/recipes/1    |
| api_detail_missing | /api/recipes/9999 |
""",
        "spec/ui-spec.md": """# UI 规范(美食暖色风,确定数值)

## 结构标记(compile_spec 从此表派生 case.json 的 UI 字段)
| 键                 | 值                                                       |
|--------------------|----------------------------------------------------------|
| list_marker        | recipe-card                                              |
| list_card_children | recipe-cover, recipe-title, recipe-meta, recipe-summary  |
| detail_markers     | btn-cook, recipe-steps                                   |
| required_colors    | #e67e22, #27ae60                                         |
| must_contain_text  | 美食工坊 Loop-Kitchen                                    |
""",
        "case.meta.json": json.dumps({
            "name": "recipe",
            "title": "美食菜谱:菜谱列表 + 做法详情",
            "data_file": "data/recipes.json",
            "loader_function": "load_recipes",
            "route_functions": ["recipe_list", "recipe_detail", "api_recipes", "api_recipe_detail"],
            "needs_images": True,
            "image_field": "cover",
            "extra_required_files": ["data/recipes.json"],
        }, ensure_ascii=False, indent=2),
    }
}

# 内置离线样例(Spec 形态):番茄钟,用于不烧额度自证「编译 → acceptance_gate」
MOCK_SPEC = {
    "pomodoro": {
        "spec/spec.md": """# 需求规格:番茄时钟(Pomodoro Timer)

## 一句话
一个单页番茄工作法计时器:默认 25:00 倒计时,可开始/重置,计时结束给出明显提示。

## 核心交互
- 页面打开即显示 `25:00`(分:秒)。
- 「开始」按钮:点击后每秒递减(浏览器端用 setInterval 驱动)。
- 「重置」按钮:把时间归回 25:00 并停止计时。
- 计时到 0:停止,并通过明显的视觉变化提示结束。

## 结构建议
- 后端 `app.py` 只负责渲染首页 `/`,很薄。
- 倒计时的**纯逻辑**抽到 `timer_core.py`:
  - `format_time(seconds) -> "MM:SS"`,如 `format_time(1500) == "25:00"`。
  - `tick(seconds) -> seconds-1`(不小于 0)。
- 前端 `static/js/timer.js` 用 setInterval 每秒递减并刷新显示。
- `tests/test_timer.py` 针对 `timer_core` 断言边界。

## 非目标
- 不是内容列表站;没有列表页/详情页/数据集/图片。
- 不需要账号、数据库、外部服务。
""",
        "spec/manifest.json": json.dumps({
            "archetype": "spec",
            "name": "pomodoro",
            "title": "番茄时钟:25 分钟专注倒计时(可开始/重置,结束有提示)",
            "tech": {"framework": "flask", "language": "python", "port_env": "PORT"},
            "required_files": [
                "app.py", "requirements.txt", "README.md", "templates/index.html",
                "static/js/timer.js", "static/css/style.css", "timer_core.py", "tests/test_timer.py",
            ],
        }, ensure_ascii=False, indent=2),
        "spec/acceptance.json": json.dumps({
            "name": "pomodoro",
            "ready_route": "/",
            "acceptance": [
                {"id": "TC1", "type": "http_status", "route": "/", "expect": 200, "desc": "首页可访问"},
                {"id": "TC2", "type": "http_body_contains", "route": "/", "needle": "25:00", "desc": "默认显示 25:00"},
                {"id": "TC3", "type": "http_body_contains", "route": "/", "needle": "id=\"start\"", "desc": "有开始按钮"},
                {"id": "TC4", "type": "file_exists", "file": "static/js/timer.js", "desc": "有计时逻辑脚本"},
                {"id": "TC5", "type": "text_contains", "file": "static/js/timer.js", "needle": "setInterval", "desc": "用定时器驱动倒计时"},
                {"id": "TC6", "type": "unit_test", "test": "tests/test_timer.py", "desc": "倒计时纯函数单测"},
                {"id": "TC7", "type": "text_absent", "file": "app.py", "needle": "detail_markers", "desc": "不是 catalog 列表站"},
                {"id": "AC1", "type": "manual", "desc": "计时结束有明显提示(声音/颜色),人工抽检"},
            ],
        }, ensure_ascii=False, indent=2),
    }
}


# ---------------------------------------------------------------- 步骤
def gen_spec_blocks(free_text, name, mock):
    """产出 {相对路径: 内容}。mock=True 用内置样例;否则调 LLM。"""
    if mock:
        if name not in MOCK:
            sys.exit(f"[spec_compiler] --mock 无内置样例:{name}(可选:{', '.join(MOCK)})")
        print(f"[spec_compiler] 离线 mock 模式,使用内置领域 '{name}' 自证链路")
        return dict(MOCK[name])
    print(f"[spec_compiler] 调用 LLM 把自由文本编译为 spec 三件套 (name={name}) ...")
    text = run_model.call_deepseek("你是严谨的规格编译器,只输出要求的文件块。",
                                   build_prompt(free_text, name))
    blocks = {rel.strip(): content for rel, content in run_model.FILE_RE.findall(text)}
    if not blocks:
        sys.exit("[spec_compiler] LLM 输出未解析到文件块,格式不符")
    return blocks


def write_case(name, blocks):
    """把三件套写入 cases/<name>/spec/,并用 case.meta.json 写出 case.json 骨架。"""
    need = ("spec/data-model.md", "spec/api-contract.md", "spec/ui-spec.md", "case.meta.json")
    missing = [f for f in need if f not in blocks]
    if missing:
        sys.exit(f"[spec_compiler] 缺少必需文件:{missing}\n拿到的是:{list(blocks)}")

    cdir = os.path.join(HARNESS_DIR, "cases", name)
    os.makedirs(os.path.join(cdir, "spec"), exist_ok=True)
    for rel in ("spec/data-model.md", "spec/api-contract.md", "spec/ui-spec.md"):
        with open(os.path.join(cdir, rel), "w", encoding="utf-8") as f:
            f.write(blocks[rel].rstrip() + "\n")

    try:
        meta = json.loads(blocks["case.meta.json"])
    except json.JSONDecodeError as e:
        sys.exit(f"[spec_compiler] case.meta.json 不是合法 JSON:{e}")
    bad = [k for k in META_KEYS if k not in meta]
    if bad:
        sys.exit(f"[spec_compiler] case.meta.json 缺字段:{bad}")
    with open(os.path.join(cdir, "case.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[spec_compiler] 已写 cases/{name}/(spec 三件套 + case.json 骨架)")
    return cdir


def contract_gate(cdir, name):
    """门禁2:契约必须『非退化』——能真正约束下游生成,而不是空壳。"""
    case = json.load(open(os.path.join(cdir, "case.json"), encoding="utf-8"))
    errs = []

    ent = case.get("entity")
    if not (isinstance(ent, str) and re.fullmatch(r"[A-Za-z_]\w*", ent or "")):
        errs.append(f"entity 非法或缺失: {ent!r}")

    mi = case.get("min_items")
    if not (isinstance(mi, int) and mi >= 1):
        errs.append(f"min_items 必须为正整数: {mi!r}")

    rf = case.get("required_fields") or []
    if "id" not in rf:
        errs.append(f"required_fields 必须含 id: {rf}")
    if len(rf) < 4:
        errs.append(f"required_fields 过少(<4),契约太弱: {rf}")

    routes = case.get("routes") or {}
    miss_routes = [r for r in STD_ROUTES if r not in routes]
    if miss_routes:
        errs.append(f"routes 缺标准路由: {miss_routes}")

    if not case.get("list_marker"):
        errs.append("list_marker 缺失(列表页无法验收)")
    if not (case.get("detail_markers") or []):
        errs.append("detail_markers 为空(详情页无法验收)")

    colors = case.get("colors") or []
    if not colors:
        errs.append("colors 为空(配色无法验收)")
    else:
        bad_c = [c for c in colors if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", c)]
        if bad_c:
            errs.append(f"colors 含非法十六进制: {bad_c}")

    fr = case.get("field_rules") or {}
    if not any(v.get("min_len", 0) >= 10 for v in fr.values() if isinstance(v, dict)):
        errs.append("缺长文本字段(无 min_len>=10 的详情正文),详情页会太空")

    if errs:
        print(f"❌ [contract_gate] {name} 契约不合规:")
        for e in errs:
            print(f"    - {e}")
        return False
    print(f"✅ [contract_gate] {name} 契约合规:"
          f" entity={ent} min_items={mi} 字段{len(rf)}个 路由{len(routes)}条"
          f" list_marker={case['list_marker']} colors={colors}")
    return True


def run_check_cli(name):
    """门禁1:实际调用 compile_spec.py <name> --check(与 CI 同一条命令)。"""
    cmd = [sys.executable, os.path.join(HARNESS_DIR, "tools", "compile_spec.py"), name, "--check"]
    print(f"[spec_compiler] 门禁: {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r.returncode == 0


# ---------------------------------------------------------------- 步骤(Spec 形态)
def gen_spec_blocks_spec(free_text, name, mock):
    """产出 Spec 形态三件套 {相对路径: 内容}。mock=True 用内置样例;否则调 LLM。"""
    if mock:
        if name not in MOCK_SPEC:
            sys.exit(f"[spec_compiler] --archetype spec --mock 无内置样例:{name}(可选:{', '.join(MOCK_SPEC)})")
        print(f"[spec_compiler] 离线 mock(Spec 形态),使用内置样例 '{name}'")
        return dict(MOCK_SPEC[name])
    print(f"[spec_compiler] 调用 LLM 把自由文本编译为 Spec 三件套 (name={name}) ...")
    text = run_model.call_deepseek("你是严谨的规格编译器,只输出要求的文件块。",
                                   build_prompt_spec(free_text, name))
    blocks = {rel.strip(): content for rel, content in run_model.FILE_RE.findall(text)}
    if not blocks:
        sys.exit("[spec_compiler] LLM 输出未解析到文件块,格式不符")
    return blocks


def write_case_spec(name, blocks):
    """把 Spec 三件套写入 cases/<name>/spec/;两个 JSON 先解析校验再规范化落盘(挡非法 JSON)。"""
    need = ("spec/spec.md", "spec/manifest.json", "spec/acceptance.json")
    missing = [f for f in need if f not in blocks]
    if missing:
        sys.exit(f"[spec_compiler] (Spec 形态)缺少必需文件:{missing}\n拿到的是:{list(blocks)}")
    cdir = os.path.join(HARNESS_DIR, "cases", name)
    os.makedirs(os.path.join(cdir, "spec"), exist_ok=True)
    with open(os.path.join(cdir, "spec", "spec.md"), "w", encoding="utf-8") as f:
        f.write(blocks["spec/spec.md"].rstrip() + "\n")
    for rel in ("spec/manifest.json", "spec/acceptance.json"):
        try:
            obj = json.loads(blocks[rel])
        except json.JSONDecodeError as e:
            sys.exit(f"[spec_compiler] {rel} 不是合法 JSON:{e}")
        with open(os.path.join(cdir, rel), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
    # 定性为 Spec 形态:清除同名 case 的 catalog 残留(旧 case.json 及 catalog spec 三件套),
    # 否则 run_model 一见 case.json 就误走 catalog(列表站),这套 Spec 契约形同虚设。
    for stale in ("case.json", "case.meta.json",
                  os.path.join("spec", "api-contract.md"),
                  os.path.join("spec", "data-model.md"),
                  os.path.join("spec", "ui-spec.md")):
        p = os.path.join(cdir, stale)
        if os.path.exists(p):
            os.remove(p)
            print(f"[spec_compiler] 清除 catalog 残留: {stale}")
    print(f"[spec_compiler] 已写 cases/{name}/spec/(spec.md + manifest.json + acceptance.json)")
    return cdir


def acceptance_gate(cdir, name):
    """Spec 形态门禁:manifest 合理 + acceptance 非退化(能真正约束生成与验收,不是橡皮图章)。"""
    try:
        manifest = json.load(open(os.path.join(cdir, "spec", "manifest.json"), encoding="utf-8"))
        ac = json.load(open(os.path.join(cdir, "spec", "acceptance.json"), encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"❌ [acceptance_gate] 读取 manifest/acceptance 失败:{e}")
        return False
    errs = []

    if manifest.get("archetype") != "spec":
        errs.append(f"manifest.archetype 必须为 'spec': {manifest.get('archetype')!r}")
    if manifest.get("name") != name:
        errs.append(f"manifest.name({manifest.get('name')!r}) 与 --name({name!r}) 不一致")
    if not (manifest.get("title") or "").strip():
        errs.append("manifest.title 缺失")
    tech = manifest.get("tech") or {}
    for k in ("framework", "language"):
        if not tech.get(k):
            errs.append(f"manifest.tech 缺 {k}")
    req = manifest.get("required_files") or []
    if not isinstance(req, list) or "app.py" not in req:
        errs.append(f"manifest.required_files 必须为列表且含 app.py: {req}")
    reqset = set(req)

    acc = ac.get("acceptance") or []
    if len(acc) < 4:
        errs.append(f"acceptance 过少(<4),验收太弱: {len(acc)} 条")
    if ac.get("name") != name:
        errs.append(f"acceptance.name({ac.get('name')!r}) 与 --name 不一致")
    rr = ac.get("ready_route", "/")
    if not (isinstance(rr, str) and rr.startswith("/")):
        errs.append(f"ready_route 非法: {rr!r}")

    auto = 0
    for i, tc in enumerate(acc):
        tid = tc.get("id", f"#{i}")
        t = tc.get("type")
        if t not in SPEC_AC_TYPES:
            errs.append(f"{tid}: 未知断言类型 {t!r}")
            continue
        for k in SPEC_AC_TYPES[t]:
            if k not in tc:
                errs.append(f"{tid}({t}): 缺字段 {k}")
        f = tc.get("file") if t in ("file_exists", "text_contains", "text_absent") else \
            (tc.get("test") if t == "unit_test" else None)
        if f and f not in reqset:
            errs.append(f"{tid}: 引用文件 {f} 不在 manifest.required_files(无法保证会被生成)")
        if t != "manual":
            auto += 1
    if auto < 3:
        errs.append(f"可自动判定的 TC 过少(<3),门禁形同虚设: {auto} 条")

    if errs:
        print(f"❌ [acceptance_gate] {name} 验收标准不合规:")
        for e in errs:
            print(f"    - {e}")
        return False
    print(f"✅ [acceptance_gate] {name} 合规: {len(acc)} 条 TC/AC(可自动判定 {auto} 条),"
          f" required_files {len(req)} 个, ready_route={rr}")
    return True


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Spec 编译层:自由文本 → 合规 case 契约")
    ap.add_argument("--name", required=True, help="用例代号(将写入 cases/<name>/)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--text", help="直接给一段自由文本需求")
    src.add_argument("--input", help="从文件读自由文本需求")
    ap.add_argument("--mock", action="store_true", help="离线模式:用内置领域样例自证链路,不调用 LLM")
    ap.add_argument("--archetype", choices=("catalog", "spec"), default="catalog",
                    help="catalog=列表/详情站(默认,原路径);spec=单页交互工具(产 spec.md+manifest+acceptance)")
    args = ap.parse_args()

    if not args.mock:
        if args.input:
            free_text = compile_spec.read(args.input)
        elif args.text:
            free_text = args.text
        else:
            ap.error("非 --mock 模式必须提供 --text 或 --input")
    else:
        free_text = ""

    print("=" * 64)
    print(f"Spec 编译层 Phase 1 | name={args.name} | archetype={args.archetype} | mode={'mock' if args.mock else 'LLM'}")
    print("=" * 64)

    # Spec 形态:产 spec.md + manifest.json + acceptance.json,过 acceptance_gate(不走 catalog 的 derive/contract_gate)
    if args.archetype == "spec":
        blocks = gen_spec_blocks_spec(free_text, args.name, args.mock)
        cdir = write_case_spec(args.name, blocks)
        ok = acceptance_gate(cdir, args.name)
        print("-" * 64)
        if ok:
            print(f"🎉 编译成功(Spec 形态):cases/{args.name}/spec/ 已产出 spec.md + manifest.json + acceptance.json。")
            print(f"   下一步生成: HARNESS_MODE=real python harness-4/tools/run_model.py {args.name} output/{args.name}")
            sys.exit(0)
        print("💥 编译未通过 acceptance_gate(见上)。不合规的验收标准当场被挡住。")
        sys.exit(1)

    # 1) 自由文本 → spec 块
    blocks = gen_spec_blocks(free_text, args.name, args.mock)
    # 2) 写入 cases/<name>/ + case.json 骨架
    cdir = write_case(args.name, blocks)
    # 3) 确定性派生:compile_spec 把 spec 规格字段写进 case.json
    print("[spec_compiler] compile_spec 派生规格字段 ...")
    compile_spec.compile_case(args.name, check_only=False)
    # 4) 门禁1:round-trip 一致(CLI --check)
    ok1 = run_check_cli(args.name)
    # 5) 门禁2:契约非退化
    ok2 = contract_gate(cdir, args.name)

    print("-" * 64)
    if ok1 and ok2:
        print(f"🎉 编译成功:cases/{args.name}/ 已产出**合规契约**,可直接喂 run_model / orchestrator。")
        print(f"   下一步(可选)冒烟: HARNESS_MODE=sample python harness-4/tools/run_model.py {args.name} output/{args.name}")
        sys.exit(0)
    print("💥 编译未通过门禁(见上)。这正是 Spec 编译层的价值:不合规的契约当场被挡住。")
    sys.exit(1)


if __name__ == "__main__":
    main()
