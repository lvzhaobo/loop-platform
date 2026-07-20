# Spec 编译层 + 动态模板方案（MumuSpec × Harness）

> 目标：让系统从「3 个手写固定 case」进化为「一句话/一份 Spec → LLM 编译出契约 → 引擎按契约动态生成任意领域应用」。
> 一句话定位：**把 LLM 放在"模糊→结构化"这一步，把"结构化→契约→验收"继续交给已验证的确定性工具。**
> 本文只做方案设计，不含代码改动。

---

## 0. 核心判断：编译层已经有一半

`harness-4/tools/compile_spec.py` 已经在做**确定性编译**：

```
cases/<case>/spec/data-model.md   ┐
cases/<case>/spec/api-contract.md ├─(compile_spec.py 正则/表格解析)─► case.json 规格字段
cases/<case>/spec/ui-spec.md      ┘   （带 --check 门禁，防 spec↔契约漂移）
```

**缺的不是"编译"，是编译器的上游**——「自由文本 / MumuSpec 文档 → 结构化 spec md」。
这一段是"模糊→结构化"，正是 LLM 的强项；而"结构化→契约"是确定性解析，继续交给 `compile_spec.py`。

> 这样 LLM 的不确定性被**关在最上游一格**，下游（契约、验收、生成）全是已验证的确定性链路。

---

## 1. 目标架构（Spec 全流程嵌入）

```
MumuSpec 14 文档 / 飞书自由文本 Spec（不完善也 OK）
      │  ① 【新增】spec_compiler（LLM）：抽取 06/09/10/13 等"AI 要读的"部分
      ▼
结构化 spec md 三件套（严格表格格式，写进 cases/<新case>/spec/）
      │  ② 【已有】compile_spec.py：确定性派生
      ▼
case.json 契约（entity/routes/field_rules/markers/colors…）
      │  ③ 【门禁】compile_spec.py --check：不合规 → 反馈重试（复用 harness 反馈循环）
      ▼
harness-4 引擎（real 模式，DeepSeek 按契约生成）
      │  ④ 【已有】verify.py 20 项验收 + 确定性校验
      ▼
Flask 应用 → 发布 → ECS 上线（沿用 B 方案）
```

**MumuSpec 怎么嵌入**：14 文档里真正"AI 读了要生成/验收"的是 06/07/09/10/11/13/14 这 7 篇（见 [MumuSpec-vs-Harness对比.md](../../MumuSpec-vs-Harness对比.md) 结论 #1）。
spec_compiler 只需从 Spec 里抽出这 7 篇对应的信息，落成结构化 md。**14 文档不完善不阻塞**——先能抽多少抽多少，抽不到的字段给安全默认值，流程先跑通。

---

## 2. "打破 case 边界" = 动态生成 case

**现在 case 为什么是"固定"的？** 三处硬绑：

| 硬绑点 | 现状 | 动态化后 |
|---|---|---|
| case 名单 | `constraints.json.cases` + `orchestrator.VALID_CASES` 写死 3 个 | 改为**动态注册**：新 case 生成后自动登记（或运行时扫描 `cases/`） |
| case 资产 | 每个 case 手写 spec md 三件套 + sample 数据 + case.json 非规格字段 | 由 spec_compiler **一次性生成整套资产** |
| 产物形状 | verify.py 硬绑「列表 + 详情」（list_marker/detail_markers） | Phase 3 放开：按契约声明的 markers 驱动校验 |

> 澄清一个易混点：**real 模式下模板本就是 LLM 动态生成的**（DeepSeek 按契约现写 templates/CSS，不是套死模板）。
> 真正"固定"的是**契约必须来自预写 case** + **产物假定为 list+detail**。破边界主要就是打掉这两点。

动态 case 落地后，来一个新领域（医院预约 / 招聘 / 工单…）**不用改任何引擎代码**：
Spec → spec_compiler 生成 `cases/<hospital>/` 整套 → compile_spec → 引擎跑。这正好接上
`orchestrator.py` 现在那个诚实的断点（第 129–136 行，`fetched` 分支：「真实生成待 spec 编译步骤」）。

---

## 3. spec_compiler 要产出什么（LLM 的输出契约）

LLM 不是自由发挥，而是**填一个严格模板**，产出下列文件到 `cases/<name>/spec/`：

| 文件 | 目标格式（compile_spec.py 能解析的） | 关键约束 |
|---|---|---|
| `data-model.md` | `entity: xxx` + `min_items: N` + 表格`\|字段\|类型\|必填\|约束\|说明\|` | 数值字段带 `gt/gte/lt/lte`；字符串带 `max_len/min_len` |
| `api-contract.md` | 表格 `\|名称\|路径\|` | 至少含 list 路由 `/` 与 detail 路由 `/<entity>/<id>` |
| `ui-spec.md` | 表格 `\|键\|值\|`：list_marker / list_card_children / detail_markers / required_colors | 配色 ≥2、marker 命名合法 |

外加 `case.json` 的**非规格字段**（name/title/data_file/loader_function/route_functions/needs_images…）——
这些是"代码结构约定"，可由 spec_compiler 用固定模板+少量 LLM 填充生成。

**质量兜底**：LLM 产出后立即跑 `compile_spec.py --check`；不通过就把错误回喂给 LLM 重试（≤3 次），
和 harness 现有的"生成→验收→回喂"反馈循环同构。**结构化 md 是 LLM 与确定性工具的清晰边界。**

---

## 4. 分阶段落地（务实，先跑通）

### Phase 1 · 最小闭环（先用 LLM 解析跑通流程）
- 新增 `delivery-loop/spec_compiler.py`（或 `harness-4/tools/`）：自由文本 Spec → 生成 spec md 三件套 → 落到新 case 目录 → 跑 compile_spec → `--check` 门禁。
- 接上 orchestrator 的 `fetched` 断点：有 spec_text 且无 case 时，调 spec_compiler 造出临时 case，再走既有 real 生成链路。
- **验收标准**：随便给一个"新领域"的 Spec（如"图书借阅"），端到端跑出可上线应用，不写一行 case 专属代码。

### Phase 2 · 动态注册 + 样例数据
- spec_compiler 同时生成 **sample 数据**（满足 data-model 约束）并**落盘固化**（避免每次漂移，之后当事实源）。
- 去掉 `VALID_CASES` / `constraints.cases` 硬编码，改为**运行时扫描 `cases/`** 或生成后自动登记。

### Phase 3 · 打破 list+detail 形状假设（最大一步，单列）
- 让契约能表达列表+详情之外的结构（多实体、表单提交、仪表盘…）。
- verify.py 的 UI 校验从「硬绑 list/detail」改为「按契约声明的 markers 驱动」。**此步牵动最多硬校验，风险最高，独立推进。**

### Phase 4 · 配置界面（稍后，基于现有 studio 更新）
- web 化"输入一句话 + 参数配置"，复用 `harness-4/studio/` 与《配置界面-必要性与设计.md》。

---

## 5. 风险与注意

| 风险 | 说明 | 缓解 |
|---|---|---|
| LLM 产出的 md 格式不合规 | compile_spec 解析失败 | `--check` 门禁 + 反馈重试（≤3），结构化 md 作硬边界 |
| 样例数据每次漂移 | LLM 生成数据不确定性 | Phase 2 生成一次即**落盘固化**，之后当唯一事实源 |
| 去 case 硬编码的副作用 | 动态注册/清理、脏 case 目录 | 运行时扫描 + 命名规范 + 生成失败即回滚目录 |
| 破形状假设代价大 | verify.py 大量硬校验绑 list/detail | 单列 Phase 3，先保 list+detail 形状能自动扩域 |
| 引擎黑盒契约 | delivery-loop 不 import harness 内部 | spec_compiler 产物只写 `cases/`，仍走 `generate.sh` 黑盒调用 |

---

## 6. 一句话总结

**编译层缺的只是最上游"自由文本→结构化 spec md"一格**——补上这个 LLM 步骤（下游全走已验证的确定性链路），
就能把 MumuSpec 的 Spec 流程完整嵌进来（14 文档不完善也先跑通），并让 case 从"手写 3 个固定模板"
变成"任意领域动态生成"。建议先做 **Phase 1 最小闭环**：给一个新领域 Spec，端到端跑出可上线应用、零引擎改动。
