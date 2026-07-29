"""从三份 spec(唯一事实源)编译出 case.json 的**全部规格字段**。

    cases/<name>/spec/data-model.md   ← 数据模型源  → entity/min_items/required_fields/numeric_fields/field_rules
    cases/<name>/spec/api-contract.md ← 接口契约源  → routes
    cases/<name>/spec/ui-spec.md      ← UI 规范源   → list_marker/list_card_children/detail_markers/colors
        │  compile_spec.py
        └─→ case.json 的规格字段(随后 build_schema.py 再从 case.json 派生 schema)

因此凡是「spec 内容」只在 spec 写一次,case.json 里对应字段是编译产物;
不再需要 check_consistency 去「校验两份对齐」——从根上消除漂移。

仍手写在 case.json 的是**非 spec 的 harness 配置**(name/title/data_file/
loader_function/route_functions/needs_images/image_field/extra_required_files),
它们是"代码结构/构建约定",本就不属于业务规格。

命名说明:沿用业界 compile 语义(protoc/dbt),spec 是源码、case.json 是编译产物。
harness 里 generate 已表示「Maker 生成代码」,故这里用 compile 以免撞概念。

用法:
    python harness-4/tools/compile_spec.py            # 编译全部用例并写回 case.json
    python harness-4/tools/compile_spec.py ecommerce  # 只编译某个用例
    python harness-4/tools/compile_spec.py --check     # 只校验不写;任一用例不一致退出码 1(供门禁/CI)
"""
import json
import os
import re
import sys

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_RANGE_KEYS = ("gt", "gte", "lt", "lte")
_NUMERIC_TYPES = ("int", "number", "float")


def _num(v):
    """约束值:能转 int 就 int,否则 float。"""
    return int(v) if re.fullmatch(r"-?\d+", v) else float(v)


def _split_list(s):
    """'a, b，c' -> ['a','b','c'];空/占位符 -> []"""
    if not s or s.strip() in ("(无)", "无", "-"):
        return []
    return [x.strip() for x in re.split(r"[，,]", s) if x.strip()]


def _split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _tables(md_text):
    """把 md 里的每个表格解析成 {'header': [...], 'rows': [dict,...]}。"""
    tables, cur = [], None
    for line in md_text.splitlines():
        if line.strip().startswith("|"):
            cells = _split_row(line)
            if cur is None:
                cur = {"header": cells, "rows": []}
            elif set("".join(cells)) <= set("-: "):  # 分隔行 |---|---|
                continue
            else:
                cur["rows"].append(dict(zip(cur["header"], cells)))
        elif cur is not None:
            tables.append(cur)
            cur = None
    if cur is not None:
        tables.append(cur)
    return tables


def _find_table(md_text, *need):
    for t in _tables(md_text):
        if all(k in t["header"] for k in need):
            return t
    return None


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------- 各 spec 的解析 ----------

def parse_data_model(md):
    """data-model.md → entity / min_items / required_fields / numeric_fields / field_rules。"""
    m = re.search(r"entity[)）]?\s*[:：]\s*`?([A-Za-z_]\w*)`?", md)
    entity = m.group(1) if m else None
    m = re.search(r"min_items\s*[:：]\s*(\d+)", md)
    min_items = int(m.group(1)) if m else None

    tbl = _find_table(md, "字段", "约束")
    required_fields, numeric_fields, field_rules = [], {}, {}
    for r in (tbl["rows"] if tbl else []):
        name, typ = r["字段"], r["类型"]
        cons = {}
        for tok in r.get("约束", "").split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                cons[k.strip()] = _num(v.strip())
        if r["必填"] == "是":
            required_fields.append(name)
        if cons:
            field_rules[name] = {"type": typ, **cons}
        if r["必填"] == "是" and typ in _NUMERIC_TYPES and any(k in cons for k in _RANGE_KEYS):
            numeric_fields[name] = typ

    return {
        "entity": entity,
        "min_items": min_items,
        "required_fields": required_fields,
        "numeric_fields": numeric_fields,
        "field_rules": field_rules,
    }


def parse_routes(md):
    """api-contract.md 的「名称|路径」表 → routes 字典。"""
    tbl = _find_table(md, "名称", "路径")
    return {r["名称"]: r["路径"] for r in (tbl["rows"] if tbl else [])}


def parse_ui(md):
    """ui-spec.md 的「键|值」标记表 → list_marker/list_card_children/detail_markers/colors。"""
    tbl = _find_table(md, "键", "值")
    d = {r["键"]: r["值"] for r in (tbl["rows"] if tbl else [])}
    out: dict = {
        "list_marker": d.get("list_marker", "").strip() or None,
        "detail_markers": _split_list(d.get("detail_markers", "")),
        "colors": [c.lower() for c in _split_list(d.get("required_colors", ""))],
    }
    children = _split_list(d.get("list_card_children", ""))
    if children:  # 可选字段:只有声明了才写入(保持无该需求用例的原形)
        out["list_card_children"] = children
    # 可选字段:需求明确要求页面出现的字面文案(品牌名/日期/口号等),
    # 逐字保留进 case.json,供 maker 照抄渲染、verify 校验渲染页确实含之。
    must = _split_list(d.get("must_contain_text", ""))
    if must:
        out["must_contain_text"] = must
    return out


def derive(cdir):
    d = parse_data_model(read(os.path.join(cdir, "spec", "data-model.md")))
    d["routes"] = parse_routes(read(os.path.join(cdir, "spec", "api-contract.md")))
    d.update(parse_ui(read(os.path.join(cdir, "spec", "ui-spec.md"))))
    return d


# ---------- 编译一个用例 ----------

def compile_case(name, check_only):
    cdir = os.path.join(HARNESS_DIR, "cases", name)
    derived = derive(cdir)
    case_path = os.path.join(cdir, "case.json")
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)

    diffs = [f"    - {k}: spec 派生={derived[k]!r}  ≠  case.json={case.get(k)!r}"
             for k in derived if derived[k] != case.get(k)]

    if check_only:
        if diffs:
            print(f"❌ [{name}] case.json 规格字段与 spec 不一致:")
            print("\n".join(diffs))
        else:
            print(f"✅ [{name}] case.json 规格字段与 spec 一致(唯一源:spec)")
        return not diffs

    for k in derived:  # 原地覆盖,保持非规格字段与键序不变
        case[k] = derived[k]
    with open(case_path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[compile_spec] {name}: 已从 spec 派生规格字段 → case.json" +
          ("(有变化)" if diffs else "(无变化)"))
    return True


def main():
    check_only = "--check" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        names = args
    else:
        constraints = {"cases": []}  # Spec 是唯一事实源，不再依赖外部约束文件
        names = constraints["cases"]

    ok = all(compile_case(n, check_only) for n in names)
    if check_only and not ok:
        print("   → 请运行 `python harness-4/tools/compile_spec.py`(不带 --check)重新派生")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
