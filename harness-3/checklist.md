# 验收清单(harness-3 标准版,每项须打勾)

## 0 约束自洽性(⑨,门禁第一关)
- [ ] `python check_consistency.py` 通过:每个 case.json 与其 spec 文档一致
- [ ] `constraints.json.cases` 与 `cases/` 实际目录一致

## 1 结构(逐用例)
- [ ] 含 constraints.base_required_files 全部文件 + 该用例 extra_required_files
- [ ] 含 README.md 与 tests/test_app.py

## 2 数据(逐用例,标尺来自 case.json)
- [ ] 数据文件合法且 ≥ min_items 条
- [ ] required_fields 齐全,numeric_fields 类型正确

## 3 依赖
- [ ] requirements.txt 不含 constraints.banned_deps 任一项(含 pytest)

## 4 编码规范(标尺来自 case.json)
- [ ] loader_function 仅定义一次
- [ ] route_functions 全部存在
- [ ] 模板内联 style ≤ constraints.max_inline_style

## 5 测试层
- [ ] 产物自带 tests/test_app.py
- [ ] python -m unittest 全部通过

## 6 接口 + 真渲染 UI(标尺来自 case.json)
- [ ] api_list 200 且 ≥ min_items;api_detail_missing → 404
- [ ] 列表页渲染出的 list_marker 数 ≥ 数据条数
- [ ] 详情页含全部 detail_markers
- [ ] CSS 含全部 colors

## 7 确定性(⑥)
- [ ] _run_meta.json 记录 case/model/temperature/seed/version
- [ ] 复跑比对:identical(字节一致)或 drift(告警,均通过验证)

## 8 回归(⑦)
- [ ] cases/ 下全部用例均通过(非仅电商)

## 9 门禁(⑧)
- [ ] `bash gate.sh` 返回 0
- [ ] ci/github-actions.yml 已知晓启用方式(复制到 .github/workflows/)
