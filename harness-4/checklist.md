# 验收清单(harness-4 标准版,每项须打勾)

## 0 约束自洽性(门禁第一关)
- [ ] `python tools/check_consistency.py` 通过:每个 case.json 与其 spec 文档一致
- [ ] `constraints.json.cases` 与 `cases/` 实际目录一致
- [ ] `python tools/build_schema.py` 成功派生 `schemas/<case>.data.schema.json`(派生物,非事实源)

## 1 结构(逐用例)
- [ ] 含 `constraints.base_required_files` 全部文件 + 该用例 `extra_required_files`
- [ ] 含 README.md 与 tests/test_app.py

## 2 数据(逐用例,标尺来自 case.json)
- [ ] 数据文件合法且 ≥ `min_items` 条,`id` 连续
- [ ] `required_fields` 齐全
- [ ] `field_rules` 量化约束全部满足(长度 / 数值范围 / 类型)
- [ ] `needs_images` 用例:图片文件齐全

## 3 依赖 + 安全
- [ ] requirements.txt 不含 `banned_deps` 任一项(含 pytest)
- [ ] .py 源码不含 `banned_code_patterns` 任一危险调用

## 4 编码规范(标尺来自 case.json)
- [ ] `loader_function` 仅定义一次
- [ ] `route_functions` 全部存在
- [ ] 模板内联 style ≤ `constraints.max_inline_style`

## 5 测试层
- [ ] 产物自带 tests/test_app.py
- [ ] `python -m unittest` 全部通过

## 6 接口 + 真渲染 UI(标尺来自 case.json)
- [ ] 就绪轮询成功启动(非固定 sleep)
- [ ] api_list 200 且 ≥ min_items;api_detail_missing → 404
- [ ] 列表页渲染出的 list_marker 数 ≥ 数据条数
- [ ] 详情页含全部 detail_markers
- [ ] CSS 含全部 colors

## 7 报告 + 确定性
- [ ] `reports/verify-report.json` 与 `reports/summary.md` 已生成
- [ ] `_run_meta.json` 记录 case/mode/model/temperature/seed/version
- [ ] 复跑比对:identical(字节一致)或 drift(告警,均通过验证)

## 8 回归 + 门禁
- [ ] cases/ 下全部用例均通过(非仅电商)
- [ ] `HARNESS_MODE=sample bash gate.sh` 返回 0(离线自检)
- [ ] `bash gate.sh` 返回 0(真实闭环,需密钥)
- [ ] ci/github-actions.yml 已知晓启用方式
