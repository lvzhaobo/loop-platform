# 平台后端骨架（验证用）

四个模块，验证"页面 → 后端"这条路能不能走通。**零第三方依赖。**

## 跑

```bash
python3 app.py          # http://127.0.0.1:8899   ← 浏览器打开这个
./run-all.sh            # 三份自检（39 项）
```

**界面已接上真后端**：六个页面（我的待办 / Spec / WBS / 约束 / 执行 / 验收）+ 一个**功能地图**。
执行页用 SSE 收事件流，审批框真的会阻塞后端线程。

详细操作见 **[使用说明.md](使用说明.md)**。

`verify.py` 当前 **10/10 通过**：

```
[1] 健康检查
[2] 建需求            → REQ-003
[3] 起运行            → RUN-fc2cded6
[4-6] 边跑边批        → 批准 ap-001(index.html) / ap-002(app.js)
      status=done gate=0 steps=9 denied=1
[7] 门禁 7/7 绿
[8] 产物里有 clampMinutes / MAX_MINUTES
[9] 事件落盘 133 条
[10] SSE 能补发历史事件
```

## Spec 生成：模板 or DeepSeek

| | 模板 | DeepSeek |
|---|---|---|
| 字数 | 160–210 | **1,350–2,270** |
| 耗时 | 秒出 | 14 份约 2 分钟 |
| 流式 | — | ✅ 逐字推送（SSE `spec_delta`） |
| 什么时候用 | 跑自检、讲流程 | 真评审、真交给 agent |

自动选：有 key 且非 MOCK → DeepSeek；否则退回模板并标注。

自检固定用 `engine=template`（快、确定、不烧钱），LLM 引擎手工验。

## 为什么菜单这么少

平台只有 **6 个能真跑的页面**，因为**只放真的，不放画的**。

原型 `prototype/v12.html` 有 29 页，那是"应该长什么样"；这里有真接口的只有 6 页。

平台里有一页 **「功能地图」**，把 29 页逐条对照：已接后端 / 有接口无页面 / 仅原型，
每条都能点进原型对应页。

原型文件也挂在服务里：

| 地址 | 是什么 |
|---|---|
| `/proto.html` | 原型 v12 · 29 页，全部可点（设计视图） |
| `/proto2.html` | 原型 v13 · 同上 + **右上角可切「真实平台视图」**，未接后端的菜单变灰带 🔒 |

`proto2.html` 的真实模式只亮 6 项（我的待办 / Spec / WBS / 约束 / 执行 / 验收），
其余 22 项置灰，点了会提示"还没有真实后端"——**这一页就是用来回答"你们做到哪了"的**。

## 为什么是这四个模块

不是按页面对齐（24 页 → 24 个模块会烂），是**按机制对齐**：

| 模块 | 验证什么 | 支撑的页面 |
|---|---|---|
| `core/bus.py` | 一份事件同时喂 SSE / 回放 / 落盘 | 执行、长程、上下文、审计 |
| `core/store.py` | 零依赖 JSON 存储，可读可 git | 需求、Spec、WBS、验收 |
| `modules/approvals.py` | **工作线程真的停下来等 HTTP** | 权限、执行、我的待办 |
| `modules/runs.py` | 长任务线程 + 复用 demo 的 loop | 执行、时间轴、门禁 |

另外 `modules/reqs.py` 是最普通的 CRUD，用来定 REST 约定。

## 接口约定

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/reqs` | 需求列表（`?q=` 搜索） |
| POST | `/api/reqs` | 建需求 `{title, source, priority, acceptance}` |
| GET | `/api/reqs/:id` | 单条 |
| PATCH | `/api/reqs/:id` | 改字段 |
| POST | `/api/runs` | 起运行 `{task, req_id?, prompt?}` → 202 |
| GET | `/api/runs/:id` | 运行状态（轮询） |
| POST | `/api/runs/:id/stop` | 停止 |
| GET | `/api/approvals` | 待批列表 |
| POST | `/api/approvals/:id` | 决定 `{decision:"allow"\|"reject"}` |
| GET | `/api/events` | **SSE**，连上先补发最近 50 条 |

## 三个设计决定

**① 不重写 loop**
`modules/runs.py` 直接 `sys.path` 引 `demo/A-python` 的 loop/tools/policy/session。
平台层和 harness 层必须能干净分开——这一条验证过了，才敢往下做。

**② 审批用 Event 阻塞，不轮询**
`HttpApprover.__call__` 里 `ev.wait(timeout)`。工作线程真的挂起，
HTTP 那边一 POST 就唤醒。轮询会导致"看起来批了其实没批"。

**③ 事件三去处**
`bus.publish()` 同时做三件事：推给所有 SSE 订阅者、存进内存环形缓冲（回放用）、
追加到 `data/events.jsonl`（审计用）。慢订阅者满了就丢，不拖累别人。

## 数据落在哪

```
data/
├── reqs.json        需求
├── runs.json        运行记录
├── events.jsonl     事件流（仅追加，审计源）
└── sessions/*.jsonl 与 DSH 同构的会话日志
```

全是纯文本，能直接 `cat`、能进 git、能 grep。

## Spec 模块（modules/specs.py）

需求 → **14 份 Spec**，带 DAG、状态机、失效传播。

```
[1] 生成 14 份（batch）              ✅
[2] 依赖顺序被遵守                   ✅  先证
[3] 审核 3 份（通过/打回/重复审被拒） ✅
[4] 改上游 S03 → 下游 11 份标 stale   ✅  这是 DAG 的意义
[5] 逐份审模式：生成 1 份就停下等人   ✅  真的阻塞
[6] 审完才继续生成第二份             ✅
```

`verify_specs.py` 当前 **14/14 通过**。

三个关键设计：

**① 14 份是有依赖的 DAG，不是平铺清单**
`S03 PRD` 改了 → `S04~S14` 共 11 份自动标 `需修改`。
表格里那列「依赖」不是装饰，它驱动真实的失效传播。

**② 三种审核模式，逐份真的阻塞**
`batch` / `group` / `stepwise`。stepwise 下生成完一份就 `Event.wait()`，
人审完才继续——和审批模块同一套机制。

**③ 生成走模板，可换 LLM**
零依赖可跑（模板生成结构化 markdown，字数/依赖都真实）；
有 key 时可把 `_gen_content` 换成 LLM 调用，接口不变。

| 方法 | 路径 |
|---|---|
| POST | `/api/specs/generate` `{req_id, mode}` → 202 |
| GET | `/api/specs?req_id=` |
| GET | `/api/specs/progress?req_id=` |
| GET | `/api/specs/graph?req_id=` → `{nodes, edges}` |
| GET | `/api/specs/:id` |
| POST | `/api/specs/:id/review` `{decision: approve\|request_change}` |
| POST | `/api/specs/:id/regenerate` → 返回受影响的下游 |

## 门禁模块（modules/gates.py）

**从「一个 exit code」变成「N 条具体断言」。**

exit code 只告诉你"没过"；断言列表告诉你"哪一条没过、为什么、hint 是什么"。

实现上直接 `import` 门禁脚本里的 `checks` 列表逐条跑，比解析 stdout 可靠——
不跟输出格式耦合。同时兼容两种写法（`CHECKS`/`checks`、2 元组/3 元组）。

```
pomodoro  → 4/7   mode=import
cs        → 5/9   mode=import
```

| 方法 | 路径 |
|---|---|
| POST | `/api/gates/run` `{task}` |
| GET | `/api/gates/latest?task=` |
| GET | `/api/gates?task=` |
| GET | `/api/gates/tasks` |

## 约束模块（modules/constraints.py）

扫描 `demo/` 里**真实的**约束文件，按四象限归类：

```
8 个文件 / 4 象限 / 822 tok（确定性的不计）
  全局·概率 1   全局·确定 1   任务·确定 4   任务·概率 2
```

注意最后一条：**确定性文件（check.py 等）不算 token**——它不进上下文。
这个细节让"四象限"从概念变成可计算的数字。

冲突检测会真的读 AGENTS.md，看有没有写「可以执行任意命令」而权限层会拦。

## WBS 模块（modules/wbs.py）

Spec → 任务卡 → 回写 Jira。两条硬规矩：

1. **每个任务挂「来源 Spec 章节」**——半年后能找回它为什么存在
2. **回写 Jira 只放引用**（`description_ref`），不复制全文——避免两处不一致

还有一个容易被忘的功能：**Spec 变了，卡要重拆**。

```
GET /api/wbs/stale?req_id=REQ-009
→ 8 张卡受影响：['S04 已重新生成 v2', ...]
```

判定规则是比时间戳：`spec.generated_at > card.created_at` → 卡就旧了。
比"状态是需修改"更准，因为重新生成的那份状态是 `待审`，不是 `需修改`。

## 一键回归

```bash
./run-all.sh
```

| 脚本 | 覆盖 | 结果 |
|---|---|---|
| `verify.py` | 需求 → 执行 → 审批 → 门禁 → SSE | 10/10 |
| `verify_specs.py` | 14 份 Spec → DAG → 审核 → 失效传播 → 逐份阻塞 | 14/14 |
| `verify_pipeline.py` | 门禁逐条 / 四象限 / WBS / Jira / 重拆 | 15/15 |
| `verify_workspace.py` | 需求绑工作区 → 真改对应仓库 | 10/10 |

**49/49 全绿。**

## 下一步（按价值排序）

| # | 做什么 | 为什么 |
|---|---|---|
| 1 | ~~`modules/specs.py`~~ | ✅ 已完成 |
| 2 | ~~`modules/gates.py`~~ | ✅ 已完成 |
| 3 | ~~`modules/wbs.py`~~ | ✅ 已完成 |
| 4 | ~~`modules/constraints.py`~~ | ✅ 已完成 |
| 5 | `web/` 接真前端 | 把 v9 的页面换成真数据 |
| 6 | `modules/traces.py` | 会话回放 |
| 7 | 权限中间件 | 谁能调哪个接口 |

## 没做的

- 认证 / 权限（现在谁都能调）
- 并发上限（同时起 100 个 run 会炸）
- 数据迁移（JSON 换 DB 的那天要写）
