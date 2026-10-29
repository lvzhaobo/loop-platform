# Sample B · DSH

和 Sample A **同一个任务、同一个门禁**，只换装置。

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | 工作区约定（概率层：它会被遵守，但不保证） |
| `cordis.patch.yml` | 装配覆盖（确定性：disabled / 审批 / 网关） |
| `run.sh` | 一条命令：先跑门禁 → 跑 agent → 再跑门禁 |

## 跑法

```bash
./run.sh
```

输出三段：

```
① 先看门禁现状（裁判先说话）      → 红
② 用 DSH headless 跑 tasks.md    → agent 退出码
③ 再跑门禁 —— 这才是合并依据      → 绿/红
```

## 三个装置里，差别只有这一行

```bash
dsh --profile headless "$(cat shared/tasks.md)"
# 换成 IDE：人在编辑器里点开始
# 换成 A-python：python3 A-python/main.py
```

**`shared/tasks.md` 与 `shared/check.py` 一个字都没改。**

## 需要按你本机调整的地方

`cordis.patch.yml` 里的 **插件 id** 和 **包名** 是模板：

```bash
dsh --dump-config | grep -A2 permission   # 查真实 id
```

id 写错**不会报错，只会静默不生效** —— 这是配置层最常见的坑，课上要讲。
