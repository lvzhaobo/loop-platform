# Sample A · 自研最小 harness

约 450 行，六个文件，把「一次任务怎么闭环」摊开给人看。

| 文件 | 行数 | 讲什么 |
|---|---|---|
| `config.py` | ~40 | 唯一配置点：key / 模型 / 工作区 / 策略 |
| `llm.py` | ~75 | 模型接入 + **离线 mock**（无 key 也能演示） |
| `tools.py` | ~120 | **白名单 + 路径监狱**（本 Sample 的核心） |
| `session.py` | ~25 | 仅追加 jsonl，可回放 |
| `approve.py` | ~17 | 行前闸门 G1 的最简版 |
| `policy.py` | ~35 | 重试预算与**终止判定** |
| `loop.py` | ~75 | 心脏：while + tool_calls + 四种终止 |
| `main.py` | ~75 | 入口 + **安全检查** |

## 跑法

```bash
python3 main.py --check-safety   # ① 先看闸门有没有暴露在工作区里
python3 main.py --mock --yes     # ② 离线演示（不调 API）
python3 main.py                  # ③ 真实模型（需 config.env 填 key）
```

## 演示出来的样子

```
[step 4] → run_command({"argv": ["rm", "-rf", "src"]})
        ⛔ 被拒：不在白名单：['rm', '-rf', 'src']
           只能跑 python check.py, python3 check.py, ls, cat, node --check
[step 5] → run_check({})
        → code=1
[step 6] → write_file({"path": "index.html", ...})
  [审批] 写入文件  index.html（773 → 931 字符）
        ✓ index.html 963
[step 8] → run_check({})
        → code=0
```

## 演示「agent 改自己白名单」

```bash
WORKSPACE=. python3 main.py --check-safety
```

会打印：

```
⚠️  危险：harness 在 agent 可写的范围内
    agent 可以改写 tools.py，把 rm 加进白名单，然后你就没有白名单了。
    正确做法：把 harness 放在工作区之外，或只读挂载。
```

**这是全场最值钱的一次警告**：闸门的前提是「闸门本身改不到」。

## 本 Sample 故意没做的事

多模型、压缩、子智能体、并发、UI、重试退避——**都不做**。

> 400 行能跑，才是这套材料的意义。代码越长，学员越不信自己能复刻。
