"""从「唯一事实源 case.json」派生数据 JSON Schema(draft-07),写入 schemas/<case>.data.schema.json。

关键原则:Schema 是**派生产物**,不是第二事实源。它由 case.json 生成,供外部工具/文档使用;
Harness 自身的验证仍直接读 case.json(见 verify.py),因此永远不会与事实源漂移。

用法: python harness-4/tools/build_schema.py
"""
import json
import os

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    constraints = load_json(os.path.join(HARNESS_DIR, "constraints.json"))
    out_dir = os.path.join(HARNESS_DIR, "schemas")
    os.makedirs(out_dir, exist_ok=True)
    for name in constraints["cases"]:
        case = load_json(os.path.join(HARNESS_DIR, "cases", name, "case.json"))
        schema = build(case)
        dst = os.path.join(out_dir, f"{name}.data.schema.json")
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
        print(f"[build_schema] 派生 {os.path.relpath(dst, HARNESS_DIR)}")


if __name__ == "__main__":
    main()
