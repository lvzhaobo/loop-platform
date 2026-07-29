"""从（studio 自有的）事实源 case dict 派生三份人类可读规格 spec/*.md,并复用同一份逻辑做自洽性预检。

⚠️ 方向提醒(已知冲突,待重构):本模块是 case -> spec,与仓库新模型
    spec -> compile_spec.py -> case（spec 才是唯一真源）**相反**。下方的 check_consistency
    只服务 studio 页面实时反馈(in-memory),**不再是门禁**;门禁已改用 compile_spec.py --check。

设计要点(仅就 studio 自身而言):spec 文档不是"第二事实源",而是 case dict 事实的确定性渲染。
只要渲染器保证把每条会被自洽性预检(本文件 check_consistency)校验的事实都写进文档。
"""
from __future__ import annotations

from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# 字段辅助
# ---------------------------------------------------------------------------
def field_type(case: Dict[str, Any], field: str) -> str:
    rule = case.get("field_rules", {}).get(field) or {}
    if rule.get("type"):
        return rule["type"]
    nf = case.get("numeric_fields", {}).get(field)
    if nf:
        return nf
    return "string"


def field_desc(case: Dict[str, Any], field: str) -> str:
    rule = case.get("field_rules", {}).get(field, {})
    parts: List[str] = []
    if rule.get("sequential_from") is not None:
        parts.append(f"唯一,从 {rule['sequential_from']} 递增")
    if "max_len" in rule:
        parts.append(f"≤ {rule['max_len']} 字")
    if "min_len" in rule:
        parts.append(f"≥ {rule['min_len']} 字")
    if "gt" in rule:
        parts.append(f"> {rule['gt']}")
    if "gte" in rule:
        parts.append(f"≥ {rule['gte']}")
    if field == case.get("image_field"):
        parts.append("封面/图片路径 `static/img/<id>.png`")
    return ",".join(parts) if parts else "-"


def _sample_value(case: Dict[str, Any], field: str) -> Any:
    t = field_type(case, field)
    if field == "id":
        return 1
    if field == case.get("image_field"):
        return "static/img/1.png"
    if t in ("int",):
        return 60
    if t in ("number",):
        return 9.9
    if t == "array":
        return ["示例"]
    if field == "content":
        return "此处应有正文,分多段展开(实际数据需满足最小长度要求)。"
    return f"示例{field}"


# ---------------------------------------------------------------------------
# 三份 spec 渲染
# ---------------------------------------------------------------------------
def render_data_model(case: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# 数据模型:`{case['data_file']}` 为数组,每个元素结构如下")
    lines.append("")
    lines.append("| 字段 | 类型 | 必填 | 说明 |")
    lines.append("|------|------|------|------|")
    for f in case.get("required_fields", []):
        lines.append(f"| {f} | {field_type(case, f)} | 是 | {field_desc(case, f)} |")
    lines.append("")
    lines.append("## 数据量要求")
    lines.append(f"- 至少 {case['min_items']} 项,id 连续 1~{case['min_items']}")
    lines.append("")
    lines.append("## 示例")
    lines.append("```json")
    lines.append("{")
    fields = case.get("required_fields", [])
    for i, f in enumerate(fields):
        val = _sample_value(case, f)
        import json as _json
        comma = "," if i < len(fields) - 1 else ""
        lines.append(f'  "{f}": {_json.dumps(val, ensure_ascii=False)}{comma}')
    lines.append("}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def render_api_contract(case: Dict[str, Any]) -> str:
    entity = case["entity"]
    routes = case["routes"]
    api_list = routes["api_list"]
    lines: List[str] = []
    lines.append("# 接口契约(路由 / 响应 / 状态码)")
    lines.append("")
    lines.append(f"## 1. {entity} 列表页(HTML)")
    lines.append(f"`GET {routes['list']}` → 渲染 list.html,展示全部 {entity}")
    lines.append("")
    lines.append(f"## 2. {entity} 详情页(HTML)")
    lines.append(f"`GET /{entity}/<int:id>` → 渲染 detail.html;id 不存在返回 404")
    lines.append("")
    lines.append(f"## 3. {entity} 列表(JSON)")
    lines.append(f"`GET {api_list}` → 200,body 为 {entity} 数组")
    lines.append("")
    lines.append(f"## 4. {entity} 详情(JSON)")
    lines.append(f"`GET {api_list}/<int:id>`")
    lines.append("- 存在:200,单个对象")
    lines.append(f'- 不存在:404,`{{"error": "{entity} not found"}}`')
    return "\n".join(lines) + "\n"


def render_ui_spec(case: Dict[str, Any]) -> str:
    colors = case.get("colors", [])
    lines: List[str] = []
    lines.append("# UI 规范(确定数值)")
    lines.append("")
    lines.append("## 配色")
    if colors:
        lines.append(f"- 主色:`{colors[0]}`")
    for c in colors[1:]:
        lines.append(f"- 强调色:`{c}`")
    lines.append("- 背景白:`#FFFFFF`;正文文字 `#333333`;次要/元信息 `#888888`")
    lines.append("")
    lines.append("## 列表页")
    lines.append("- 顶部标题栏,站点名居左")
    lines.append(f"- 列表为卡片,每项一张卡片,卡片根元素带 class `{case['list_marker']}`")
    children = case.get("list_card_children", [])
    if children:
        lines.append("- **每张卡片必须同时包含以下子元素(硬性,缺一不可):**")
        for c in children:
            lines.append(f"  - `class=\"{c}\"`")
    if colors:
        lines.append(f"- 卡片 hover 时标题变主色 `{colors[0]}`")
    lines.append("")
    lines.append("## 详情页")
    lines.append("- 顶部标题 + 元信息")
    for m in case.get("detail_markers", []):
        lines.append(f"- 关键元素带 class `{m}`")
    lines.append("- 底部返回列表链接")
    lines.append("")
    lines.append("## 字号")
    lines.append("- 列表标题 18px、详情标题 28px、正文 16px、元信息 13px")
    return "\n".join(lines) + "\n"


def render_all_specs(case: Dict[str, Any]) -> Dict[str, str]:
    return {
        "data-model.md": render_data_model(case),
        "api-contract.md": render_api_contract(case),
        "ui-spec.md": render_ui_spec(case),
    }


# ---------------------------------------------------------------------------
# 自洽性预检(studio 页面实时反馈用,in-memory);门禁侧已改用 tools/compile_spec.py --check
# ---------------------------------------------------------------------------
def check_consistency(case: Dict[str, Any], specs: Dict[str, str]) -> List[str]:
    fails: List[str] = []
    spec_data = specs.get("data-model.md", "")
    spec_api = specs.get("api-contract.md", "")
    spec_ui = specs.get("ui-spec.md", "")

    if str(case.get("min_items", "")) not in spec_data:
        fails.append(f"min_items={case.get('min_items')} 未在 data-model 出现")
    for f in case.get("required_fields", []):
        if f not in spec_data:
            fails.append(f"required_field '{f}' 未在 data-model 出现")
    for f, rule in case.get("field_rules", {}).items():
        for key in ("max_len", "min_len"):
            if key in rule and str(rule[key]) not in spec_data:
                fails.append(f"field_rules.{f}.{key}={rule[key]} 未在 data-model 出现")

    routes = case.get("routes", {})
    if routes.get("api_list") and routes["api_list"] not in spec_api:
        fails.append(f"api_list {routes['api_list']} 未在 api-contract 出现")
    if "404" not in spec_api:
        fails.append("api-contract 未声明 404")

    if case.get("list_marker") and case["list_marker"] not in spec_ui:
        fails.append(f"list_marker '{case['list_marker']}' 未在 ui-spec 出现")
    for c in case.get("list_card_children", []):
        if c not in spec_ui:
            fails.append(f"list_card_children '{c}' 未在 ui-spec 出现")
    for m in case.get("detail_markers", []):
        if m not in spec_ui:
            fails.append(f"detail_marker '{m}' 未在 ui-spec 出现")
    for c in case.get("colors", []):
        if c.lower() not in spec_ui.lower():
            fails.append(f"color '{c}' 未在 ui-spec 出现")
    return fails
