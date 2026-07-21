# step6 · 换上真实的 Maker/Checker：跑 mathkit（单次，不循环）

到 step5 为止，节点都是玩具（往 `text` 后面接字符串）。从这里开始接**真实组件**：把 step2/step3 的图形状（直线 + 一个前置门禁）原样搬过来，只把节点内部换成 harness-5 里现成的 Maker 和 Checker —— 它们**一行都不用改**。

| 节点 | 复用的真实组件 | 干什么 |
|---|---|---|
| `consistency` | `gates.check_consistency` | 生成前门禁：facts 声明的函数在规格里有落点 |
| `maker` | `model.generate` | 真实生成 `mathkit.py` 到 `output/` |
| `checker` | `gates.verify` | 结构 / 安全 / 行数 + 跑固定单测 |

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step6_real_makercheck/main.py
```

> 默认 `HARNESS_MODE=sample`：离线、不烧额度。复用 `harness-5/lib` 与 `harness-5/spec` 的 mathkit 规格。产物写到本目录 `output/`。

## 关键点：本步故意"只跑一次"

sample 模式第 1 轮会故意写一个有 bug 的 `factorial`，所以验收 `[FAIL] 测试:unittest 全绿`。**这不是错误，是设计**——它说明"单次生成不够"，正好引出 step7：

> 只要把 `checker` 后面那条 `add_edge("checker", END)` 改成一条**未过就回 `maker`** 的回边（就是 step4 学的回边 + step3 学的条件边），就变成会自愈的 Loop：第 1 轮失败→回喂→第 2 轮修对。

## 预期输出（节选）

```
[step6] 自洽性门禁通过 ✓
[model] sample 生成 mathkit.py (attempt=1, BUGGY)
验收 4/5：
  [PASS] 结构:模块文件存在 / 函数定义齐全 / 安全 / 行数
  [FAIL] 测试:unittest 全绿
[step6] 结论:fail:验收未过(单次不够,见 step7)
```
