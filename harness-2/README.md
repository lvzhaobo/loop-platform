# Harness-2(加固版)

在 `harness/`(MVP)基础上补齐"基层",目标仍是**稳定生成代码**,但把地基夯实。

## 相比 harness/ 补全了什么

| 缺口(见 3.md 分析) | harness-2 的补全 |
|----------------------|------------------|
| ① 约束层没分层 | 拆成 `rules/base/`(跨任务通用基座)+ `rules/task/`(电商专属) |
| ② 缺测试层 | `rules/base/testing.md` 要求产物自带 `tests/test_app.py`(stdlib unittest),`verify.py` 自动运行 |
| ③ 验证浅、有盲区 | `verify.py` 增加**真渲染校验**(拉取渲染后 HTML 断言卡片数/按钮数)+ **规范校验**(单函数/内联样式/命名) |
| ④ 无可观测性 | `baseline/manifest.json` 结构基线比对 + `output/runs.jsonl` 运行历史(通过率/重试次数/模型) |
| ⑤ 确定性未落地 | `config.env` 固定 model/temperature/seed;`run_model.py` 写 `_run_meta.json` 并记入 `_verify.log` 头部 |
| ⑥ 缺工程地基 | 本 `README.md` + `VERSION` + `setup.sh` 一键环境准备 |

## 目录结构

```
harness-2/
├── README.md / VERSION / setup.sh / config.env   # 工程地基 + 确定性配置
├── prompt.md                                      # ③ 生成入口
├── run_model.py                                   # ③ DeepSeek 生成器(+确定性日志)
├── generate.sh                                    # ③+④+⑤ 闭环 + 运行历史
├── verify.py                                      # ④ 综合验证(7 类检查)
├── checklist.md                                   # ④ 人工验收清单
├── rules/
│   ├── base/  (security / error-and-logging / testing / documentation)
│   └── task/  (tech-stack / structure / conventions)
├── spec/      (data-model / api-contract / ui-spec)
└── baseline/manifest.json                          # ④ 结构基线
```

## 用法

```bash
bash harness-2/setup.sh          # 首次:准备环境
source .env                       # 载入 DEEPSEEK_API_KEY(仓库根,已 gitignore)
bash harness-2/generate.sh        # 生成→验证→失败带反馈重生成,产物入 output/<时间戳>/
```

## 判定成功
连续 3 次生成,`verify.py` 全部通过(7 类检查全绿),且结构与 `baseline/manifest.json` 一致。
