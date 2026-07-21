# Harness-3(标准版)

在 `harness-2/`(加固版)基础上补齐"生产级"能力,做成一套自洽、可回归、有门禁的标准 Harness。核心目标不变:**用确定性工程脚手架稳定生成代码**。

## 相比 harness-2 补全了什么(⑥⑦⑧⑨)

| 短板(见评估) | harness-3 的补全 |
|----------------|------------------|
| ⑥ 确定性只声明未验证 | `generate.sh` 通过后**复跑一次并比对产物哈希**,不一致 → 告警(如实暴露 LLM seed 非严格可复现,由验证层兜底) |
| ⑦ 单用例、无回归防护 | `cases/`(ecommerce + blog)**多用例回归**,`generate.sh` 遍历全部用例,防"修好 A 弄坏 B" |
| ⑧ 无 CI 门禁 | `gate.sh`(自洽性→全用例闭环)+ `ci/github-actions.yml`,产物不过验收即红灯挡合并 |
| ⑨ 约束靠人肉保证不矛盾 | **唯一事实源** `constraints.json` + `cases/*/case.json`;`verify.py` 标尺全部从事实源读取,零硬编码;`check_consistency.py` 校验 spec 文档 ↔ 事实源不漂移 |

## 目录结构

```
harness-3/
├── README.md / VERSION / setup.sh / config.env   # 工程地基 + 确定性/用例配置
├── constraints.json                               # ⑨ 全局唯一事实源(基础文件/禁用依赖/用例清单)
├── prompt.md                                       # 生成入口(用例无关)
├── run_model.py                                    # case 驱动的 DeepSeek 生成器(+确定性日志)
├── verify.py                                       # case 驱动综合验证(标尺全来自事实源)
├── check_consistency.py                            # ⑨ 约束自洽性检查
├── generate.sh                                     # ⑥⑦ 多用例闭环 + 确定性复跑 diff
├── gate.sh                                         # ⑧ 门禁:自洽性 → 全用例闭环
├── ci/github-actions.yml                           # ⑧ CI 工作流模板
├── checklist.md                                    # 人工验收清单
├── rules/
│   ├── base/  (security / error-and-logging / testing / documentation)   # 通用基座
│   └── task/  (tech-stack / structure / conventions)                     # 任务通用约束
└── cases/                                          # ⑦ 回归语料
    ├── ecommerce/  case.json + spec/(data-model / api-contract / ui-spec)
    └── blog/       case.json + spec/(data-model / api-contract / ui-spec)
```

## 用法

```bash
bash harness-3/setup.sh          # 首次:准备环境
source .env                       # 载入 DEEPSEEK_API_KEY(仓库根,已 gitignore)

# 只校验约束是否自洽(不花额度,不调模型):
python harness-3/check_consistency.py

# 门禁全链路(自洽性 → 遍历全部用例生成+验证 + 确定性复跑):
bash harness-3/gate.sh

# 只跑生成闭环(可用环境变量指定用例 / 关闭复跑省额度):
HARNESS_CASES="ecommerce" HARNESS_DET_CHECK=0 bash harness-3/generate.sh
```

产物入 `output/<批次时间戳>-<用例>/`;运行历史(通过率/重试/确定性/模型)追加到 `output/runs.jsonl`。

## 判定成功
`gate.sh` 返回 0,即:约束自洽 + 所有用例 `verify.py` 全绿。确定性复跑若报 `drift` 属预期告警(非失败),表示模型两次输出有差异但均通过验证。

## 新增/修改任务的正确姿势
1. 在 `cases/<新用例>/` 建 `case.json`(唯一事实源)+ `spec/` 三份规格;
2. 把用例名加入 `constraints.json.cases`;
3. `python harness-3/check_consistency.py` 确认自洽;
4. `bash harness-3/gate.sh` 全量回归。
**永远改约束(rules/cases),不改产物。**
