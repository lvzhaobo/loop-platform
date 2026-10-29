# 六个实验 · 直接复现

> 每个实验 **5 分钟**，全部用真实代码，不依赖 LLM，不花一分钱。
> 目的：让「跑 → 判定 → 差分 → 停止」变成看得见、摸得着的东西。

```bash
cd experiments
python3 safety.py                      # 试验 4-6（安全三件套）
bash run-all.sh                        # 试验 1-3（loop 三条停止条件）
```

---

## 实验地图

| # | 实验 | 验证什么 | 一句话判据 |
|---|---|---|---|
| 1 | 正常收敛 | loop 能停下来 | 4 轮后 `✅ A 通过` |
| 2 | 制造回归 | **回归要立即停** | 第 2 轮 `⛔ B 回归` |
| 3 | 假修 | 不收敛要停 | 第 3 轮 `⛔ C 连续 3 轮无变化` |
| 4 | 门禁判据 | 退出码才是判据 | `returncode == 0` |
| 5 | 权限约束 | 同一能力两个入口 | `cat` 和 `read_file` 都堵 |
| 6 | 终止判定 | 三重预算 | 步数/重试/超时 |

---

## 试验 1：正常收敛

```bash
cat > target.txt <<'TXT'
def handle(x):
    if not x:
        raise Exception("bad")
    print("debug", x)
    return {"key": "sk-demo-123456"}
TXT
rm -f out/ledger.jsonl
FIX_MODE=good python3 mumuloop-mini.py run \
  --checker "python3 checker_demo.py" --fixer "python3 fixer.py" --max-rounds 5
```

**真实输出：**

```
轮  退出码  error  fixed  regressed  still_red  判定
1   1       3      0      0          0          → 继续修
2   1       2      1      0          2          → 继续修
3   1       1      1      0          1          → 继续修
4   0       0      1      0          0          ✅ A 通过
```

**看什么**：`regressed` 一直是 0，所以一路修到底。

---

## 试验 2：制造回归（最重要的一条）

```bash
cat > target.txt <<'TXT'
def handle(x):
    if not x:
        raise Exception("bad")
    return {"key": "sk-demo-123456"}
TXT
FIX_MODE=crash python3 mumuloop-mini.py run \
  --checker "python3 checker_demo.py" --fixer "python3 fixer.py" --max-rounds 5
```

**真实输出：**

```
轮  退出码  error  fixed  regressed  still_red  判定
1   1       2      0      0          0          → 继续修
2   1       2      1      1          1          ⛔ B 回归 ['ERR002']
```

**关键**：`error` 从 2 到 2 没变，但 `fixed=1` `regressed=1` ——
**修好一条的同时弄坏了一条**。

> 如果只看 `error` 总数，你会以为"没进展，继续跑"。
> 实际上这一轮**变坏了**，必须停下来让人判断。

这是最容易被忽略、也最贵的一条。

---

## 试验 3：假修 / 不收敛

```bash
cat > target.txt <<'TXT'
def handle(x):
    print("debug", x)
    return {"key": "sk-demo-123456"}
TXT
FIX_MODE=noop python3 mumuloop-mini.py run \
  --checker "python3 checker_demo.py" --fixer "python3 fixer.py" --max-rounds 6
```

**真实输出：**

```
1   1       2      0      0          0          → 继续修
2   1       2      0      0          2          → 继续修
3   1       2      0      0          2          ⛔ C 连续 3 轮无变化
```

**看什么**：`error` 三轮都是 2 → 触发 C。**再跑下去只是烧 token。**

---

## 试验 4：门禁判据

```bash
python3 safety.py
```

```
fixture 初始状态 → 退出码 1（1 = 红）
判据：returncode == 0     ← 这就是全部，没有别的解释空间
```

**带走的认知**：agent 说"我做完了"是**声明**，退出码是**判据**。
两者不一致时，以退出码为准。

---

## 试验 5：权限约束（同一能力两个入口）

```bash
python3 safety.py
```

```
✅ rm -rf src          → 拒绝   （命令名不在白名单）
✅ cat ../../check.py  → 拒绝   （参数路径越界）
✅ cat /etc/passwd     → 拒绝   （绝对路径越界）
✅ cat index.html      → 放行   （工作区内）
✅ python check.py     → 放行   （白名单内）
```

**这一条我们真踩过**：

```
→ read_file ../../check.py   ⛔ 被拒（路径越界）
→ cat       ../../check.py   ✅ 放行 ← 换了个工具就过去了
```

**判据**：不要问"我堵了 read_file 没有"，要问「**同一个能力有几个入口**」。

| 能力 | 入口 |
|---|---|
| 读文件 | `read_file` / `cat` / `head` / `less` / `grep` |
| 写文件 | `write_file` / `tee` / `sed -i` / `>` |
| 执行 | `run_command` / `bash -c` / `eval` |

只堵一个，等于没堵。

---

## 试验 6：终止判定

```
MAX_STEPS=30   MAX_RETRIES=2   CMD_TIMEOUT=120
```

**判据**：不是"跑到绿"，是「**跑到绿 或 撞预算**」——
**两个出口都必须有**。只有"跑到绿"的 loop，会在不收敛时无限跑。

---

## 三个文件是什么

| 文件 | 行数 | 作用 |
|---|---|---|
| `mumuloop-mini.py` | ~150 | **核心**：跑 → 判定 → 差分 → 停止 |
| `checker_demo.py` | 30 | 门禁：4 条规则，退出码 0/1 |
| `fixer.py` | 40 | 模拟"修一轮"，三种模式对应三个实验 |

`mumuloop-mini.py` 只做四件事，没有任何框架代码：

```python
code, fails = run_checker(cmd)        # 跑
fixed     = prev - fails              # 差分
regressed = fails - prev
if len(fails) <= 0:           停止 A    # 通过
elif prev and regressed:      停止 B    # 回归
elif same_sig >= N:           停止 C    # 不收敛
```

**这 15 行就是 loop 工程的全部内核。**

---

## 怎么用到自己的项目

```bash
# 1. 把你的门禁换成自己的
python3 mumuloop-mini.py run \
  --checker "pytest -q --tb=no | tail -1" \
  --fixer   "claude -p '修到测试全绿，不许改测试'" \
  --max-rounds 5

# 2. 看账本
python3 mumuloop-mini.py stats
```

**注意**：`--checker` 的输出格式要能被解析出"哪些规则红了"。
如果你的门禁是 pytest，中间加一层：

```bash
pytest -q 2>&1 | grep FAILED | awk -F'::' '{print "RED", $2}' | sort -u
```
