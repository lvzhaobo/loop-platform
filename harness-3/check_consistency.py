"""Harness-3 约束自洽性检查(⑨):校验唯一事实源 case.json 与 spec 文档不打架。

动机:min_items/字段/路由/配色等约束若在 case.json 与 spec 文档两处各写一遍,
可能悄悄漂移(改了一处忘另一处),导致"闭环全绿但守的不是同一条线"。
本脚本让二者不一致时直接红灯,是门禁 gate.sh 的第一道关卡。

用法: python harness-3/check_consistency.py
返回: 全部一致 → 0;任一冲突 → 非 0(并打印全部冲突)。
"""
import glob
import json
import os
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
errors = []


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def expect(cond, msg):
    if not cond:
        errors.append(msg)


constraints = load_json(os.path.join(HARNESS_DIR, "constraints.json"))
cases_dir = os.path.join(HARNESS_DIR, "cases")

# A. 全局:constraints.cases 必须与 cases/ 下实际目录一致
declared = set(constraints["cases"])
actual = {os.path.basename(os.path.dirname(p))
          for p in glob.glob(os.path.join(cases_dir, "*", "case.json"))}
expect(declared == actual,
       f"constraints.cases {sorted(declared)} 与实际用例目录 {sorted(actual)} 不一致")

# B. 每个用例:case.json 事实源必须能在对应 spec 文档中找到落点
for name in sorted(actual):
    cdir = os.path.join(cases_dir, name)
    case = load_json(os.path.join(cdir, "case.json"))
    spec_data = read(os.path.join(cdir, "spec", "data-model.md"))
    spec_api = read(os.path.join(cdir, "spec", "api-contract.md"))
    spec_ui = read(os.path.join(cdir, "spec", "ui-spec.md")).lower()

    # 用例名自洽
    expect(case["name"] == name, f"[{name}] case.json.name={case['name']} 与目录名不符")

    # data-model:数据文件名、数量下限、必填字段都要在规格里出现
    data_basename = os.path.basename(case["data_file"])
    expect(data_basename in spec_data, f"[{name}] data-model.md 未提及数据文件 {data_basename}")
    expect(str(case["min_items"]) in spec_data,
           f"[{name}] data-model.md 未提及数量下限 {case['min_items']}(与 case.json 漂移)")
    for fld in case["required_fields"]:
        expect(fld in spec_data, f"[{name}] data-model.md 未定义必填字段 {fld}")

    # api-contract:列表接口、详情路由前缀、404 语义都要在规格里出现
    routes = case["routes"]
    expect(routes["api_list"] in spec_api, f"[{name}] api-contract.md 未提及 {routes['api_list']}")
    detail_prefix = routes["detail_sample"].rsplit("/", 1)[0] + "/"
    expect(detail_prefix in spec_api, f"[{name}] api-contract.md 未提及详情路由 {detail_prefix}")
    expect("404" in spec_api, f"[{name}] api-contract.md 未定义 404 语义")

    # ui-spec:列表标记、详情标记、配色都要在规格里出现
    expect(case["list_marker"] in spec_ui, f"[{name}] ui-spec.md 未提及列表标记 {case['list_marker']}")
    for m in case["detail_markers"]:
        expect(m.lower() in spec_ui, f"[{name}] ui-spec.md 未提及详情标记 {m}")
    for color in case["colors"]:
        expect(color.lower() in spec_ui, f"[{name}] ui-spec.md 未提及配色 {color}")

if errors:
    print("[FAIL] 约束自洽性检查未通过,发现以下冲突:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print(f"[OK] 约束自洽:{len(actual)} 个用例的 case.json 与 spec 文档全部一致")
