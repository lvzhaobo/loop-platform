"""从「唯一事实源 case.json」派生数据 JSON Schema(draft-07),写入 schemas/<case>.data.schema.json。

关键原则:Schema 是**派生产物**,不是第二事实源。它由 case.json 生成,供外部工具/文档使用;
Harness 自身的验证仍直接读 case.json(见 verify.py),因此永远不会与事实源漂移。

用法: python loop/engine/tools/build_schema.py
"""
import glob
import json
import os

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # loop/engine/
LOOP_DIR = os.path.dirname(ENGINE_DIR)  # loop/
CASES_DIR = os.path.join(LOOP_DIR, "cases")

_TYPE_MAP = {"int": "integer", "number": "number", "string": "string"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build(case):
    props = {}
    rules = case.get("field_rules", {})
    numeric = case.get("numeric_fields", {})
    for f in case["required_fields"]:
        rule = rules.get(f, {})
        t = rule.get("type") or numeric.get(f) or "string"
        prop = {"type": _TYPE_MAP.get(t, "string")}
        if "max_len" in rule:
            prop["maxLength"] = rule["max_len"]
        if "min_len" in rule:
            prop["minLength"] = rule["min_len"]
        if "gt" in rule:
            prop["exclusiveMinimum"] = rule["gt"]
        if "gte" in rule:
            prop["minimum"] = rule["gte"]
        props[f] = prop
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": f"{case['name']} data item",
        "type": "array",
        "minItems": case["min_items"],
        "items": {
            "type": "object",
            "required": case["required_fields"],
            "properties": props,
        },
    }


def main():
    # Spec 是唯一事实源:用例通过扫描 cases 目录发现,不再依赖已废弃的 constraints.json。
    # 数据 Schema 仅对仍保留 case.json(旧版数据驱动)的用例派生;
    # spec 类用例(仅 manifest.json)没有表格数据模型,自然跳过,保持无产物原形。
    out_dir = os.path.join(LOOP_DIR, "schemas")
    case_files = sorted(glob.glob(os.path.join(CASES_DIR, "*", "case.json")))
    if not case_files:
        print("[build_schema] 无 case.json 用例(spec 类用例不派生数据 Schema),跳过")
        return
    os.makedirs(out_dir, exist_ok=True)
    for cf in case_files:
        name = os.path.basename(os.path.dirname(cf))
        case = load_json(cf)
        case.setdefault("name", name)
        schema = build(case)
        dst = os.path.join(out_dir, f"{name}.data.schema.json")
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
        print(f"[build_schema] 派生 {os.path.relpath(dst, LOOP_DIR)}")


if __name__ == "__main__":
    main()
