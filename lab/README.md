# lab · 教学切片

主平台的可读切片。**不是第二套产品**，是把平台里的机制压缩到能在一小时内读完的规模。

## 三块

| 目录 | 是什么 | 跑起来 |
|---|---|---|
| `console/` | 6 页控制台 + 9 个后端模块（~1,300 行） | `cd console && python3 app.py --real` |
| `demo/` | 可运行的 agent 工程（配置/工具/审批/循环/门禁） | `cd demo/A-python && python3 main.py` |
| `experiments/` | 六个可复现实验：跑 → 判定 → 差分 → 停止 | `cd experiments && bash run-all.sh` |

## 为什么放在一起

`console/` 依赖 `../demo`（同一个工作区、同一份门禁）。
路径约定是 `console/modules/*.py` → `Path(__file__).parent.parent.parent / "demo"`，
所以 `lab/console/` + `lab/demo/` 并排放就自动对上，不需要改一行代码。

## 和主平台的关系

| | 主平台 | lab |
|---|---|---|
| 规模 | 8,000+ 文件 | 111 文件 |
| 入口 | `studio/` Vue | `console/` 单页 HTML |
| 用途 | 交付 | **讲清楚为什么这么设计** |
| 依赖 | 全栈 | 零外部依赖（纯标准库） |

## 一条命令验证

```bash
cd console && python3 ../demo/reset.py && ./run-all.sh
```

四份自检 49 项全绿：

```
verify.py            10/10   需求 → 执行 → 审批 → 门禁 → SSE
verify_specs.py      14/14   14 份 DAG → 审核 → 失效传播
verify_pipeline.py   15/15   门禁逐条 / 四象限 / WBS / Jira
verify_workspace.py  10/10   需求绑工作区 → 真改对应仓库
```

## 三个实验最值得先跑

```bash
cd experiments
bash run-all.sh        # 三条停止条件：通过 / 回归 / 不收敛
python3 safety.py      # 门禁 / 白名单 / 路径监狱 / 三重预算
```

实验 2（制造回归）是核心：

```
轮  退出码  error  fixed  regressed  still_red  判定
2   1       2      1      1          1          ⛔ B 回归 ['ERR002']
```

**error 总数没变，但修好一条的同时弄坏了一条。**
只看总数会以为"继续跑"，实际这一轮变坏了。
