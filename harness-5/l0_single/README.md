# L0 · 单次调用 —— 以及它生成的那份"带病产物"

> 这一层刻意什么保障都没有。它存在的意义,是让你**亲眼看到"没有验收"有多危险**:
> 生成出来的代码可能是错的,而 L0 既不知道、也不关心。后面的 L1→L4 就是逐层给它上保险。

## 1. 这是什么 / 怎么运行

```bash
python3 harness-5/l0_single/run.py     # 默认 sample 离线模式,无需网络/密钥
```

`run.py`(20 行)做的就是最朴素的三步:

1. `common.load_spec()` 读取规格 `spec/spec.md` + 事实源 `spec/facts.json` + 硬约束 `constraints.json`;
2. `model.generate(...)` 拼提示词 → 调模型 → 把产物写到 `output/l0/`;
3. 打印一句"完成"。**没有任何检查。**

## 2. 产物在哪,为什么**不要手改**

生成物是 [`output/l0/mathkit.py`](../output/l0/mathkit.py),但请注意:

- `output/` 已在 [`.gitignore`](../.gitignore) 中,**不进版本库**;
- 每次运行 `run.py` 都会**整文件覆盖重写**它(内容来自 [`lib/model.py`](../lib/model.py) 的 `_BUGGY` / `_CORRECT` 模板)。

所以**在 `mathkit.py` 里手写注释是无效的**——下次一跑就没了。它是"产物",不是"源码"。想改它的行为,要改的是**生成它的模板/约束**,而不是产物本身(这正是 Harness 的核心思想:约束上游,而非修补下游)。

## 3. 代码到底哪里有问题

sample 模式下,L0 的第 1 次尝试(`attempt=1`)故意产出**带 bug 的 `factorial`**:

```python
def factorial(n):
    result = 0          # ← BUG:阶乘的累乘初值应为 1,这里写成 0
    for i in range(2, n + 1):
        result *= i     # 0 乘任何数恒为 0
    return result
```

后果:

| 调用 | 期望 | 实际(bug 版) |
|------|------|--------------|
| `factorial(0)` | `1` | `0` |
| `factorial(5)` | `120` | `0` |

`add` / `is_prime` / `fib` 三个函数是对的——**只有 `factorial` 错**。这是刻意设计的教具(见 `lib/model.py` 顶部注释),用来演示"验收如何精确抓出唯一的坏点"。

> 注:这是 `sample` 离线模式的**确定性教具**,不是真模型的随机输出。切 `HARNESS_MODE=real`(需 DeepSeek key)时,产物由真实模型生成。

## 4. 哪个检查会抓到它 —— 而 L0 为什么抓不到

会抓到它的是验收测试 [`tests/test_mathkit.py`](../tests/test_mathkit.py) 里的 `test_factorial`:

```python
def test_factorial(self):
    self.assertEqual(mathkit.factorial(0), 1)     # bug 版返回 0 → FAIL
    self.assertEqual(mathkit.factorial(5), 120)   # bug 版返回 0 → FAIL
```

**但 L0 根本没有跑这些测试**——它生成完就结束了。于是"对不对没人知道"。这就是 L0 要暴露的问题,引出下一层。

## 5. 后续如何改进与约束(L1 → L4)

| 层 | 做什么 | 对这个 bug 的效果 |
|----|--------|-------------------|
| **L1 Harness** [`../l1_harness/gate.py`](../l1_harness/gate.py) | 生成后跑 `gates.verify`(结构/安全/行数/`unittest`) | **发现** `test_factorial` 失败,退出码 1——但只发现,不修复 |
| **L2 Loop** [`../l2_loop/loop.py`](../l2_loop/loop.py) | 失败报告回喂,重试到通过 | 第 1 轮失败 → 回喂 → 第 2 轮换成 `_CORRECT`,**修好** |
| **L3 护栏** [`../l3_guardrails/loop_guarded.py`](../l3_guardrails/loop_guarded.py) | 迭代上限 / 花费上限 / sha256 卡死检测 | 万一"怎么修都修不好"(`HARNESS_SAMPLE_STUCK=1`),**不会无限烧钱**,会被护栏拦停 |
| **L4 确定性** [`../l4_determinism/determinism.py`](../l4_determinism/determinism.py) | temp0+seed 跑两遍,比对哈希 | 保证"同样输入 → 同样产物",结果**可复现可审计** |

一句话:**L0 让你看到问题,L1 发现问题,L2 修复问题,L3 保证修复不失控,L4 保证结果可信。**

## 6. 重新生成 / 对照正确版

```bash
python3 harness-5/l0_single/run.py          # 重生成本层(仍是 bug 版,attempt=1)
python3 harness-5/l2_loop/loop.py           # 看闭环把它修好(对照 output/l2/mathkit.py)
```

正确版长什么样,见 `lib/model.py` 里的 `_CORRECT`(`factorial` 的 `result` 初值为 `1`)。
