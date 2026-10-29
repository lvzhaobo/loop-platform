# DSH 接入 · 验收链 · 审计 · 人工审核

四条能力，一条命令验证：

```bash
python3 pipeline/full_flow.py --maker dsh        # 用 DSH 生成
python3 pipeline/full_flow.py --maker sample     # 离线，不花钱
python3 pipeline/full_flow.py --maker deepseek   # 用 DeepSeek
```

---

## 一、DSH / 非 DSH 可切换

`engine/makers/dsh_maker.py` 实现和 `deepseek_api` / `cli_adapter` **同一个接口**：

```python
class DshMaker(Maker):
    name = "dsh"
    def generate(self, workdir, prompt, feedback=None) -> MakerResult
```

切换只改一个参数：

```bash
python3 pipeline/full_flow.py --maker dsh
python3 pipeline/full_flow.py --maker deepseek
```

或改 profile 里的 `"maker": "dsh"`（见 `profiles/dsh-local.json`）。
**Checkers 固定不动**——这是原有的设计原则。

### ⚠️ 必须知道的一个坑

DeepSeek 给 DSH 走的是 **Messages（Anthropic 兼容）协议**，不是 `/chat/completions`：

| base URL | 结果 |
|---|---|
| `https://api.deepseek.com` | ❌ `HTTP_404: DeepSeek Messages request failed` |
| `https://api.deepseek.com/anthropic` | ✅ 正常 |

`DshMaker` 默认就用后者，可用 `DSH_BASE_URL` 覆盖。

**另一个坑**：不要用 `DSH_PROFILE` 传 profile——那是用户全局的桌面 profile（值是 `desktop`），
会撞车。用 `DSH_MAKER_PROFILE`（默认 `headless`）。

### 环境变量

```bash
DSH_BIN=dsh                                 # 可执行文件
DSH_MAKER_PROFILE=headless                  # 用的 profile
DSH_BASE_URL=https://api.deepseek.com/anthropic
DSH_TIMEOUT=600
DEEPSEEK_API_KEY=sk-...                     # DSH 通过 credentials service 读
```

### 实测结果

用 `--maker dsh` 跑番茄钟任务，DSH 生成 6 个文件、3,676 行：

```
output/RUN-6bcb4c5e/
├── index.html        325 行
├── styles.css      1,991 行
├── app.js          1,103 行
├── timer-core.js     247 行   ← 纯逻辑，可单测
├── tests/core.test.js          ← 它自己写的测试
└── package.json
```

**它生成的测试能跑通 9/9：**

```
$ node tests/core.test.js
ℹ pass 9
ℹ fail 0
```

---

## 二、验收：AC → TC → 门禁结果

`engine/core/acceptance.py`

```json
{
  "acs": [
    {"id": "AC-001", "desc": "页面包含倒计时元素", "tc": "has_timer"},
    {"id": "AC-002", "desc": "页面包含开始按钮", "tc": "has_button"}
  ],
  "tcs": [
    {"id": "has_timer",  "ac_id": "AC-001"},
    {"id": "has_button", "ac_id": "AC-002"}
  ]
}
```

**向后兼容**：老格式 `{"checks":[{"name","desc"}]}` 会自动升级成 AC 编号。

链的完整性检查（`check_chain`）会报出：

| 问题 | 报什么 |
|---|---|
| 没有 AC | 「没有任何 AC —— 门禁无据可依」 |
| AC 没挂 TC | 「AC-001 没有关联 TC —— 这条标准无法验证」 |
| AC 提到的 TC 不存在 | 「AC-001 关联的 TC tc-1 不存在」 |
| TC 挂在未知 AC | 「TC tc-9 挂在未知 AC AC-999 上（孤儿用例）」 |

每条验证结果写 `data/evidence/acceptance.jsonl`，按 run 汇总。

**为什么要有这条链**：没有链，门禁是黑盒，客户问"你凭什么叫通过"答不上来。

---

## 三、审计

复用 `engine/core/event_store.py`（append-only JSONL，拒绝改写、跳号、跨 run）。

`pipeline/full_flow.py` 里的 `AuditLog` 按 `RunEvent` 合同写事件：

```
序号  stage    status   evidence  digests
1    source   passed   1         1
2    maker    passed   1         4
3    checker  passed   1         4
4    checker  passed   1         4
```

合同很严，但严得有道理：

- `passed` 事件**必须带至少一条 evidence**（不能空口说通过）
- `digests` 必须包含该阶段要求的所有摘要（source 要 input；maker 要 input/spec/acceptance/artifact）
- `evidence.scope` 必须有 `run_id` / `plan_digest` / `kind`

**这是"审计不能造假"的代码化。**

---

## 四、人工审核

`engine/core/review.py` —— **真的停下来**，不是在日志里写一行"需要审核"。

三种放行方式：

| 方式 | 怎么用 | 谁 |
|---|---|---|
| 交互（默认） | 终端 y/n | 人 |
| 自动 | `REVIEW_AUTO=allow\|reject` | CI / demo |
| 超时 | `REVIEW_TIMEOUT=60`，超时**默认拒绝** | 无人值守 |

**关键设计：超时默认拒绝，不是默认通过。** 没人签字就不放行。

每次决策写审计事件（`type=review_decision`，带 by / reason / ts）。

### 实测

```bash
$ python3 pipeline/full_flow.py --maker sample --auto-review allow
[4] 人工审核…
    ✅ 放行（auto:REVIEW_AUTO）
→ 退出码 0

$ python3 pipeline/full_flow.py --maker sample --auto-review reject
[4] 人工审核…
    ⛔ 驳回（auto:REVIEW_AUTO）
→ 退出码 2
```

**退出码本身就是判据**，可以直接进 CI。

---

## 四点五、验收是真跑的（不是看 maker 成功）

`engine/core/acceptance.py` 的 `run_tcs()` 会**真的执行**每条 TC，支持 6 种检查：

| 类型 | 参数 | 判据 |
|---|---|---|
| `file_exists` | `file` | 文件在 |
| `text_contains` | `file`, `value` | 文本含 |
| `text_absent` | `file`, `value` | 文本不含 |
| `regex` | `file`, `pattern` | 正则匹配 |
| `command` | `command`, `expect_exit` | 退出码等于期望 |
| `unit_test` | `command` | 退出码 0 |

### 实测：sample maker 只生成单文件 → 3/5

```
✅ AC-001  有页面入口，且是 HTML        匹配 '(?i)<!doctype html>' → '<!doctype html>'
✅ AC-002  页面里有倒计时显示            匹配 '\d{2}:\d{2}' → '25:00'
✅ AC-003  有开始/暂停控制按钮           匹配 '<button[^>]*' → '<button id="start"'
❌ AC-004  倒计时逻辑与界面分离           文件不存在：timer-core.js
❌ AC-005  它自己写的单元测试必须通过      退出码 1
```

**这就是真验收的价值**：它明确告诉你"界面有了，但逻辑没分离、也没有测试"。

### 踩到两个真坑（都是写验收标准时最容易犯的）

#### 坑一：把实现细节当验收条件

第一版 `AC-004` 写的是「存在 `timer-core.js`」。DSH 第一次生成的文件叫 `timer-core.js`（通过），
第二次生成的文件叫 `core.js`（失败）——**同一份代码质量，验收结果不同**。

这说明 TC 验的是**文件名**，不是**性质**。

改成验性质：

```json
{"id": "tc-004", "check": {"type": "glob_exists", "pattern": "tests/*.test.js", "min": 1}}
{"id": "tc-005", "check": {"type": "node_test_glob", "pattern": "tests/*.test.js"}}
```

改完 DSH 产物 **5/5 全绿**（`core.test.js` 的 10 条测试全过）。

> **判据：如果换一种合法的实现方式就会失败，那这条 TC 写错了。**

#### 坑二：假阴性（检查器自己要被校准）

第一版 `AC-001` 的正则是 `<!DOCTYPE html>`（大写），而 sample 写的是 `<!doctype html>`（小写）
→ **正确的产物被判失败**。

改成 `(?i)<!doctype html>` 后通过。

**这就是 `mumu_harness.py calibrate` 红绿测要解决的问题**：
检查器自己也会有假阴性/假阳性，得用"必须变红的样本 + 必须通过的样本"双向校准。

## 四点六、审计查询

```bash
python3 pipeline/audit.py --list                 # 列出所有 run
python3 pipeline/audit.py --run RUN-65e53b88     # 看完整事件链
python3 pipeline/audit.py --run RUN-xxx --json   # 机器可读
```

实测输出：

```
run RUN-65e53b88 · 7 条事件

  1  source   passed  ev=1  maker=sample
  2  maker    passed  ev=1  files=2 round=1
  3  checker  passed  ev=1  ac_id=AC-001 detail=匹配 ... → '<!doctype html>'
  4  checker  passed  ev=1  ac_id=AC-002 detail=匹配 ... → '25:00'
  5  checker  passed  ev=1  ac_id=AC-003 detail=匹配 ... → '<button id="start"'
  6  checker  failed  ev=0  ac_id=AC-004 detail=文件不存在：timer-core.js
  7  checker  failed  ev=0  ac_id=AC-005 detail=退出码 1

⚠️ 2 条失败
```

**注意 `ev=0`**：失败的检查没有 evidence（因为没东西可举证），通过的必须带。
这正是审计合同的约束——**不能空口说通过**。

## 四点七、长程任务与上下文（已实测）

见 `长程任务与上下文实测.md`。核心两条：

- **上下文水位可观测**：session 日志每步记 `totalTokens`，平台读日志即可，不用改 DSH
- **断点续跑可行**：`--session-id` 续跑后缓存读从 13,312 接着走，
  已写文件 mtime 不变（没重复劳动），最终 45 个测试全绿

**未验证**：阈值压缩（需 >60k 上下文）与 tool-result 裁剪（需单个返回 >12.5k tokens）。

## 五、五件事的当前状态

| 能力 | 状态 | 文件 |
|---|---|---|
| 验收（AC→TC→结果） | ✅ 可用 | `engine/core/acceptance.py` |
| 审计 | ✅ 可用 | `engine/core/event_store.py` + `AuditLog` |
| 人工审核 | ✅ 可用，真阻塞 | `engine/core/review.py` |
| 完整流程 | ✅ 一条命令 | `pipeline/full_flow.py` |
| DSH / 非 DSH 切换 | ✅ 可用 | `engine/makers/dsh_maker.py` |

## 六、已知限制

| 限制 | 说明 |
|---|---|
| ~~验收判据是"产物存在"~~ | ✅ 已改成真执行 TC（6 种检查类型） |
| DSH 全量生成较慢 | 番茄钟任务 > 7 分钟，demo 建议用小任务或 `--maker sample` |
| 没有并发控制 | 现在一次只跑一个，规模化再补 |
| 审核没有界面 | 终端交互，Studio 页面是下一步 |
