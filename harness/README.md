# Harness-1（最小骨架 / MVP）

> 四代演进的**起点**。这里刻意只做"能跑通闭环"的最小实现，方便你看清一个 Harness 的骨架由哪几块拼成——不追求通用、不追求健壮。后面 `harness-2/3/4` 会逐级补齐它的缺口。

## 它证明一件事：契约 → 生成 → 验收 → 失败重试

```
prompt.md + rules/ + spec/   ← 约束与规格（喂给模型的上下文）
        │  run_model.py       ← Maker：调 DeepSeek，按固定格式吐文件
        ▼
   output/<时间戳>/           ← 生成的可运行 Flask 产物
        │  verify.py          ← Checker：结构/数据/依赖/起服务查接口/UI 主色
        ▼
   通过 → 结束；不通过 → 把 _verify.log 回喂，重生成（generate.sh 最多 3 次）
```

## 用法

```bash
source .env                    # 载入 DEEPSEEK_API_KEY（仓库根，已 gitignore）
bash harness/generate.sh       # 生成→验证→失败带反馈重生成，产物入 output/<时间戳>/
```

## 刻意的局限（正因如此才叫"一代"）

这些**不是 bug，是有意为之的简化**，也正是后续几代要解决的问题：

| 局限 | 后续哪一代补上 |
|---|---|
| 领域写死：`verify.py` 把电商 case（`products.json`、主色 `#FF5000`、字段名）硬编码，只能验这一个 spec | harness-3 起引入 `cases/` 多用例；harness-4 用 `spec` 编译 + schema 通用化 |
| 约束不分层：`rules/` 平铺，通用规范与电商专属混在一起 | harness-2 拆 `rules/base` 与 `rules/task` |
| 无测试层、无基线、无运行历史 | harness-2 补 `tests/`、`baseline/`、`output/runs.jsonl` |
| 起服务用固定 `sleep(2)` 等待，慢机器可能偶发失败 | harness-2 起改健壮的就绪探测 |
| 只跑一个固定 case，没有"生成前自洽性检查" | harness-3 加 `constraints.json` + `check_consistency.py` |

## 下一步

看 [`../harness-2/README.md`](../harness-2/README.md)：在此基础上补齐"基层"（分层约束 / 测试 / 基线 / 确定性配置 / 工程地基）。
完整学习路线见仓库根的 [`LEARNING_PATH.md`](../LEARNING_PATH.md)。
