# GitHub 多仓发布方案（Spec / 配置界面 / Harness 约束 / Loop Engine）

> 目标：把「需求规格、配置界面与参数、Harness 约束、Loop Engine」发布到 GitHub，
> 与已有的产物仓 `loop-sample` 一起，形成可版本化、可协作、可复现的完整工程资产。
> 本文只做方案设计，不含代码改动。

---

## 0. 可行性结论

**可行，且推荐做。** 现在所有组件都已经是纯文件（Python + Markdown + JSON + Shell + HTML），
天然适合进 Git。唯一要严守的红线是**机密不进仓**（`.env` 已 gitignore，继续保持）。
本方案给出「放哪个仓、怎么分、怎么推、怎么防泄密、分几步落地」。

---

## 1. 现状盘点（谁在哪、是不是机密）

| 组件 | 当前位置 | 性质 | 能否进仓 |
|---|---|---|---|
| Loop Engine（编排层） | `delivery-loop/`（orchestrator/adapters/publisher/deployer/trigger） | 代码 | ✅ 可 |
| 配置参数（非机密） | `delivery-loop/config.env`、`harness-4/config.env` | 配置 | ✅ 可 |
| 配置界面 | `harness-4/studio/`（prototype.html/server.py 原型） | 代码 | ✅ 可 |
| Harness 约束 | `harness-4/`（constraints.json、rules/、cases/、schemas/、checklist.md、tools/） | 代码+约束 | ✅ 可 |
| Spec 文档 | `delivery-loop/specs/`（飞书落地）、`harness-4/cases/*/spec/`（业务规格） | 文档 | ✅ 可 |
| 生成的应用 | GitHub `loop-sample`（sampleN/） | 产物 | ✅ 已在 |
| **机密** | 仓库根 `.env`（DEEPSEEK/FEISHU/GITHUB_TOKEN/ECS 密码） | **机密** | ❌ **永不进仓** |
| 大量实验目录 | `harness/`、`harness-2/3/5`、`*copy*`、`langgraph-1/`、根目录若干 `.md` | 探索/草稿 | ⚠️ 需筛选，不建议整体发布 |

---

## 2. 仓库拓扑（推荐方案）

采用**「三仓分离」**——按关注点切分，既解耦又不过度碎片化：

```
┌─────────────────┐   读需求    ┌──────────────────┐  推产物   ┌────────────────┐
│  loop-specs      │ ─────────▶ │  loop-platform    │ ───────▶ │  loop-sample    │
│ (需求 / 规格仓)   │            │ (平台仓 = 系统本身) │          │ (产物仓, 已有)   │
│ · specs/*.md     │ ◀───────── │ · harness-4/      │          │ · sampleN/      │
│ · cases 业务规格 │  归档回写   │ · delivery-loop/  │          │ · .github/wf    │
└─────────────────┘            │ · studio/ 配置界面 │          └────────────────┘
                               └──────────────────┘
```

| 仓库 | 装什么 | 可见性建议 |
|---|---|---|
| **loop-platform**（新建，平台 monorepo） | Harness 引擎+约束（harness-4）、Loop Engine（delivery-loop）、配置界面（studio）、`.env.example`、文档 | **私有**（含运维/部署逻辑） |
| **loop-specs**（新建，规格仓） | 需求 Spec 文档、各 case 业务规格；产品/非开发可直接改 | 私有或内部 |
| **loop-sample**（已有，产物仓） | 生成的 sampleN 应用 + 通用部署 workflow | 公开（Actions 拉取免 token） |

**为什么不选另外两种：**
- ❌ 每个组件一个仓（多 repo）：初期过度碎片，跨仓联动成本高。
- ❌ 全塞一个大仓：产物/规格/平台混在一起，CI 触发范围、协作权限、可见性都不好分（产物想公开、平台想私有就矛盾）。

---

## 3. Spec 推送到独立仓：两种数据流

**流 A —— 归档流（平台 → specs，推荐先做）**
飞书拉到 Spec 后，除落地本地 `specs/`，再推送一份到 `loop-specs` 仓归档。
价值：需求留痕、可评审、可回溯「哪版需求生成了哪版应用」。低风险，复用现有 publisher 的推送能力。

**流 B —— 源头流（specs → 平台，作为后续增量）**
需求直接写在 `loop-specs` 仓的 md 里，新增一个 `github-specs` 适配器（与现有 feishu 适配器平级），
orchestrator 从该仓读取 pending 需求。等于**把 GitHub 仓变成需求来源**，替代/补充飞书。

> 建议顺序：先 A（归档，几乎零风险），B 作为「GitHub 作需求源」的适配器增量再上。

---

## 4. 配置界面与参数怎么发布

- **配置界面代码**：随 `loop-platform` 仓发布（现有 `harness-4/studio/` 原型 + 后续按
  《配置界面-必要性与设计.md》打磨的正式版）。
- **配置参数（非机密）**：`config.env` 直接进仓——它本就是「可被环境变量覆盖的默认值」，无机密。
- **机密参数**：
  - 仓内只放 **`.env.example`** 模板（键名 + 注释 + 占位，**无真实值**）。
  - 真实机密：本地放仓库根 `.env`（gitignore）；CI 放 **GitHub Secrets**；服务器放环境变量。
  - 配置界面**只写非机密**到 config.env，机密项在界面里做「只写不回显」，落到本机 `.env`。

---

## 5. 安全红线（务必遵守）

1. **`.env` 永不进任何仓**——已 gitignore，发布前再确认一遍。
2. **发布前扫描密钥**：建议接 `gitleaks` 或 `pre-commit` 钩子，防止误提交 token/密码。
3. **Token 已在对话中多次明文出现 → 强烈建议 Regenerate**，新 token 只给最小权限：
   Contents(write) / Workflows(write) / Actions(write) 按需分配。
4. **可见性**：平台/规格仓建议**私有**；产物仓公开（否则 Actions 拉取需配 token）。
5. **历史清洗**：若从现有工作区直接 `git init` 发布，注意历史里别夹带过 `.env`；必要时用全新仓、干净首提交。

---

## 6. 落地步骤（分阶段，可逐步验证）

**Phase 0 · 准备**
- 建 `loop-platform`、`loop-specs` 两个空仓（私有）。
- 写 `.env.example`、各仓 `README.md`、`.gitignore`（收敛：忽略 `.env`/`.venv`/`__pycache__`/`output/`）。

**Phase 1 · 平台仓发布**
- 筛选：只发布 `harness-4/` + `delivery-loop/`（+ studio）这套「真系统」；
  `harness/`、`harness-2/3/5`、`*copy*`、`langgraph-1/` 等实验目录**不发布**（或另建 `experiments` 仓归档）。
- 干净首提交推到 `loop-platform`。

**Phase 2 · 规格仓 + 归档流（流 A）**
- 把现有 `specs/`、`cases/*/spec/` 整理进 `loop-specs`。
- publisher 增加「Spec 归档推送」：每次处理需求时把 Spec 推一份到 `loop-specs`（复用 Contents API / git 推送）。

**Phase 3 · （可选）GitHub 作需求源（流 B）**
- 新增 `github-specs` 适配器，orchestrator 从 `loop-specs` 读 pending 需求。

**Phase 4 · 配置界面纳入 + CI**
- 配置界面正式版进 `loop-platform`；给平台仓加 CI（lint / 冒烟：`HARNESS_MODE=sample` 跑通闭环）。

---

## 7. 与现有能力的关系（不冲突）

- **B 方案（多样例自动递增 + 端口 1000+N + 保留最近 5）**：属产物仓 `loop-sample` + 部署逻辑，本方案不改它。
- **双通道部署（本地 delivery-loop / GitHub Actions）**：照常工作；平台仓发布后，delivery-loop 代码也有了版本管理。
- **飞书需求来源**：保留；流 B 只是**新增**一个 GitHub 需求源，不替换飞书。

---

## 8. 风险与注意

| 风险 | 说明 | 缓解 |
|---|---|---|
| 密钥误提交 | `.env`/token 进仓 | gitignore + gitleaks + `.env.example` |
| 跨仓版本协同 | 平台改约束可能影响历史产物的可复现性 | 平台仓打 tag/VERSION，产物记录所用平台版本 |
| Token 权限 | 推 specs / 触发 Actions 需不同权限 | 最小权限矩阵，Regenerate 旧 token |
| 实验目录噪音 | 工作区大量草稿混入 | Phase 1 明确筛选清单，只发布真系统 |
| 可见性错配 | 私有逻辑发成公开 | 平台/规格私有，产物公开 |

---

## 9. 一句话总结

把「系统本身（平台仓）＋ 需求规格（规格仓）＋ 生成产物（产物仓）」三仓分离发布到 GitHub，
机密走 `.env`/Secrets 永不进仓——**完全可行**，建议按 Phase 0→1→2 先跑通「平台发布 + Spec 归档」，
流 B（GitHub 作需求源）与配置界面正式版作为后续增量。
