# L5 · 工业化编排(LangGraph 对照)

## 讲什么
L2/L3 是**手写 `while` 循环**——讲清了 Loop 的第一性原理(生成→验收→回喂→护栏)。
L5 换个视角:**同一个 Loop,用 LangGraph 的「状态图」重写一遍**,看生产里怎么把它做得
可恢复、可观测、可扩展。

> **关键点:Maker 和 Checker 一行不改。** `lib/model.py`(Maker)、`lib/gates.py`(Checker)、
> `lib/common.py` 全部复用——因为当初就把它们和循环解耦了。L5 只新增一个"编排壳"。

## 这是不是自创写法?——不是,是 LangGraph 的招牌用法
"生成 → 验收 → 带反馈重试 + 护栏"就是 LangGraph 官方 code-gen 教程(灵感来自
CodiumAI/AlphaCodium)的模式,业界常叫 **Generator-Critic / self-correction loop**。
我们只是把 Checker 做得更严(自洽性 + lint + 单测 + 字段规则 + UI 标记 + 行数)。

## 组件映射
| 手写 L3 | LangGraph(L5) |
|---|---|
| `while True:` | 图的回边(`route` 返回 `"maker"`) |
| 传来传去的 `attempt/feedback/cost/prev_hash` | **State**(`LoopState` TypedDict),节点读写它 |
| `gates.check_consistency()` | 节点 `consistency` |
| `model.generate()` | 节点 `maker`(不改,直接调) |
| `gates.verify()` + `format_report()` | 节点 `checker`(不改,直接调) |
| 三条护栏 + 收敛判据 | 节点内定结论 + 条件边 `route` 纯读取 |
| `state.json` 终态 | **Checkpointer**(每一步可回放/可恢复) |

## 图结构
```
START → consistency ─(自洽性失败)→ END
             │通过
             ▼
           maker ──▶ stuck_check ─(产物==上轮)→ END(卡死)
             ▲            │有变化
             │回喂         ▼
             └──────── checker → route ┬─ 全绿 ────────→ END(pass)
                                       ├─ 超迭代/超预算 → END(abort)
                                       └─ 否则回喂 ─────→ maker
```
跑 `run.py --mermaid` 可直接导出 Mermaid 图。

## 组件(相对 L3 新增)
- `graph.py`:`LoopState` + 四个节点(`n_consistency/n_maker/n_stuck/n_checker`)+ 三条
  路由边(`after_consistency/after_stuck/route`)+ `build()` 组装并挂 `MemorySaver`。
- `run.py`:入口,`load_spec → build → invoke`,仍受 `HARNESS_TASK` 控制。

## 动手
```bash
# 装依赖(仅 L5 需要;L0~L4 仍零依赖)
pip install langgraph

# mathkit:2 轮收敛,退出码 0
python harness-5/l5_langgraph/run.py

# mall:2 轮收敛(换任务只改环境变量,图/Maker/Checker 全复用)
HARNESS_TASK=mall python harness-5/l5_langgraph/run.py

# 演示卡死检测护栏:让 sample 永远修不好 → 第 2 轮产物同上轮 → 秒停
HARNESS_SAMPLE_STUCK=1 python harness-5/l5_langgraph/run.py

# 顺带打印图的 Mermaid
python harness-5/l5_langgraph/run.py --mermaid
```

## 两个"踩坑点"(现场值得讲)
1. **决策要写在节点里,不能写在条件边里。** LangGraph 只持久化**节点**的返回值;
   条件边(路由函数)对 state 的赋值**不会保存**。所以 `stop_reason/feedback` 都在
   `n_checker` 里定好,`route` 只做纯读取——这是初学最容易踩的坑。
2. **卡死检测要 hash 整个产物,不能只 hash 单个模块。** mall 是多文件任务,变化的是
   `products.json` 而非 `app.py`。L5 的 `_product_hash()` 对整目录按字节取指纹,比 L3
   只看 `facts["module"]` 更健全(L3 在多文件任务上会误报卡死)。

## 收益 vs 成本
| | 手写 while(L2/L3) | LangGraph(L5) |
|---|---|---|
| 可恢复(断点续跑) | ❌ | ✅ Checkpointer |
| 每步可观测/可回放 | ⚠️ 仅终态 | ✅ 每节点快照 |
| 人审 / 并行 / 子图 | ❌ 越加越乱 | ✅ 原生支持 |
| 可视化(Mermaid) | ❌ | ✅ 一行导出 |
| 依赖 | **零** | 引入 langgraph |

**结论**:讲原理用手写版(零依赖、逐行可讲);讲工业化用 L5 做对照。二者并存,
Maker/Checker 完全复用,只是 Loop 编排从"函数里的 while"升级成"显式状态图"。

## 下一步(方案里有,尚未做)
- 把 `MemorySaver` 换 `SqliteSaver`,演示"跑一半 kill 掉能从断点恢复"。
- 用 LangGraph `interrupt` 在 checker 后插入人审节点。
- 把每轮 state + Mermaid 喂给 `console/` 玻璃盒视图。

> 完整设计见 `doc/langgraph-集成方案.md`。
