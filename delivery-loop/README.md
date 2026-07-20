# delivery-loop:自主交付编排层

在 `harness-4`(生成+验证引擎)之上的**编排层**:从需求池自主取任务 → 子进程调用
harness-4 生成并验证 → 把结果回写到来源。harness-4 被当作**黑盒引擎**调用,本层
**不修改 harness-4 的任何代码或产物**。

涵盖「进阶路线」的 **L1(通过即发布 GitHub) / L2(需求池自主取任务) / L4(拉取式部署到 ECS)**。

---

## 快速开始(零密钥)

```bash
# 需先准备好 harness-4 的环境(创建 .venv + Flask)
bash harness-4/setup.sh
source .venv/bin/activate

# 从需求池自主取任务并跑通闭环(默认 sample 离线模式,不烧额度)
bash delivery-loop/run_backlog.sh
```

跑完后:
- 产物在仓库根 `output/<时间戳>-<用例>/`(由 harness-4 生成);
- 任务状态已回写到 `delivery-loop/backlog/backlog.jsonl`(pending → done/failed)。

真实生成(调用 DeepSeek):在仓库根 `.env` 写 `DEEPSEEK_API_KEY=sk-xxx`,再:
```bash
HARNESS_MODE=real bash delivery-loop/run_backlog.sh
```

---

## 架构:两层解耦

```
需求来源(适配器)          编排层                       引擎(不改)
backlog.jsonl ─┐
GitHub Issue ─┤   adapters/ ──▶ orchestrator.py ──子进程──▶ harness-4/generate.sh
Jira/禅道/TB ─┘   (归一化Task)   取任务→调引擎→回写         (生成+验证闭环)
                                      ▲                          │
                                      └──── 回读 output/runs.jsonl ┘
```

- **适配器** `adapters/`:每个来源实现 `list_pending()`(读待办)+ `report()`(回写结果),
  翻译成归一化 `Task`。新增来源=加一个子类,主循环一行不改。
- **主循环** `orchestrator.py`:按优先级取 pending 任务 → `HARNESS_CASES=<case> bash
  harness-4/generate.sh` → 用退出码 + `output/runs.jsonl` 判定结果 → 回写状态。

---

## 目录结构

```
delivery-loop/
├── config.env              # 来源/模式/开关(非机密;密钥走仓库根 .env)
├── run_backlog.sh          # 主入口(source config.env + .env → orchestrator)
├── orchestrator.py         # 主循环(子进程调 harness-4 + 发布 + 部署 + 回写)
├── publisher.py            # L1 发布到 GitHub(子目录/分支两种布局)
├── deployer.py             # L4 拉取式 SSH 部署到 ECS
├── adapters/
│   ├── base.py             # Task 结构 + Adapter 契约
│   ├── local_adapter.py    # local:读写 backlog.jsonl
│   ├── feishu_adapter.py   # feishu:直连开放 API 读 docx/wiki 正文
│   └── __init__.py         # load_adapter():按 HARNESS_BACKLOG_SOURCE 选择
└── backlog/
    ├── backlog.jsonl       # 本地需求池(每行一个任务)
    └── feishu_docs.json    # 飞书需求清单(doc_token/wiki_token)
```

---

## 发布到 GitHub(L1)

产物通过验收后,在其目录内单独 `git init` → 建分支 → 提交 → 推送到目标仓库
(每个产物是一个独立可运行应用,不污染主仓库)。自动写 `.gitignore` 排除验证
元数据/缓存/报告,发布的只是干净的应用。

### 1. 零密钥自测(仅本地提交,不推送)
```bash
HARNESS_AUTOCOMMIT=1 HARNESS_GIT_PUSH=0 bash delivery-loop/run_backlog.sh
```
在产物目录生成一个本地 git 仓库与提交,验证整条链路,无需任何密钥。

### 2. 真实推送到 GitHub
仓库根 `.env`(已 gitignore)配细粒度 PAT(只勾目标仓 Contents 写权限):
```bash
GITHUB_TOKEN=github_pat_xxx
```
`config.env` 或环境变量指定目标仓(需先在 GitHub 建好该仓):
```bash
export HARNESS_GIT_REMOTE="github.com/你/你的仓.git"
HARNESS_AUTOCOMMIT=1 bash delivery-loop/run_backlog.sh
```

**两种布局**(由 `HARNESS_GIT_SUBDIR` 决定):
- **子目录模式**(推荐,一个仓库收纳多个样例):克隆目标仓 → 应用写到
  `<subdir>/` → 提交推到 `HARNESS_GIT_BRANCH`(默认 main)。
  ```bash
  export HARNESS_GIT_REMOTE="github.com/lvzhaobo/loop-sample.git"
  export HARNESS_GIT_SUBDIR="sample1"
  HARNESS_AUTOCOMMIT=1 bash delivery-loop/run_backlog.sh
  ```
- **分支模式**(未设 `HARNESS_GIT_SUBDIR`):每个产物推到独立分支 `harness/<任务id>-<时间戳>`。

> 安全:token 仅作为一次性 clone/push URL 参数,**不写入持久 .git/config、不打印日志**;报错时也会把 token 替换为 `****`。

---

## 需求格式(local)

`backlog/backlog.jsonl` 每行一个任务:

```json
{"id": "REQ-001", "title": "教育课程站", "case": "education", "priority": 1, "status": "pending"}
```

- `case`:映射到 harness-4 的用例(`ecommerce` / `blog` / `education`)。**结构化任务直接给。**
- `status`:`pending → running → done/failed`,由编排层自动流转并回写(含 `output_dir`/`reason`)。
- `spec_text`:自由文本需求。当前最小版**暂不处理**(会标 failed 并注明),留给后续
  「spec 编译 + 自洽门禁」增量。

---

## 配置(config.env,均可被环境变量覆盖)

| 变量 | 默认 | 说明 |
|---|---|---|
| `HARNESS_BACKLOG_SOURCE` | `local` | 来源:`local`/`feishu`(已实现);`github/jira/teambition/bitable`(待接) |
| `HARNESS_BACKLOG_FILE` | `delivery-loop/backlog/backlog.jsonl` | local 需求池路径 |
| `HARNESS_FEISHU_DOCS` | `delivery-loop/backlog/feishu_docs.json` | feishu 需求清单(非机密) |
| `HARNESS_FEISHU_STATE` | `delivery-loop/backlog/feishu_state.json` | feishu 状态回写文件(本地) |
| `HARNESS_MODE` | `sample` | 传给引擎:`sample`(零密钥)/ `real`(DeepSeek) |
| `HARNESS_MAX_TASKS` | `0` | 单批最多处理条数,0=不限 |
| `HARNESS_AUTOCOMMIT` | `0` | 1=产物通过后发布到 GitHub;0=不发布 |
| `HARNESS_GIT_REMOTE` | (空) | 目标仓(不含 token/https):如 `github.com/lvzhaobo/loop-sample.git` |
| `HARNESS_GIT_SUBDIR` | (空) | 非空=子目录模式,应用放 `<subdir>/` 推到 main;如 `sample1` |
| `HARNESS_GIT_BRANCH` | `main` | 子目录模式的目标分支 |
| `HARNESS_GIT_BRANCH_PREFIX` | `harness` | 分支模式前缀,最终 `<前缀>/<任务id>-<时间戳>` |
| `HARNESS_GIT_PUSH` | `1` | 1=真实推送(需 GITHUB_TOKEN);0=仅本地提交(无密钥自测) |
| `ECS_DEPLOY` | `0` | 1=推送成功后 SSH 到 ECS 拉取式部署;0=不部署 |
| `ECS_HOST` | (空) | ECS 公网 IP(密码 `ECS_SSH_PASSWORD` 走 .env) |
| `ECS_SSH_USER` / `ECS_SSH_PORT` | `root` / `22` | SSH 登录用户/端口 |
| `ECS_REMOTE_DIR` / `ECS_APP_PORT` | `~/apps` / `5000` | ECS 上代码根目录 / 应用对外端口 |

---

## 飞书云文档来源(feishu)

从飞书 docx 读取需求 Spec。**运行时直连飞书开放 API**(不走 lark-mcp,因为编排层是独立进程)。

### 1. 配凭证(不要贴进任何对话/仓库)
仓库根 `.env`(已 gitignore):
```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```
飞书开放平台需给应用开通「查看新版文档」权限,并把目标文档共享给该应用。

### 2. 列需求文档
编辑 `backlog/feishu_docs.json`。支持两种来源 token(二选一):
- `doc_token`:普通云文档,取自 URL `.../docx/<这段>`;
- `wiki_token`:知识库节点,取自 URL `.../wiki/<这段>`(适配器会先解析为底层 docx)。
```json
{"docs": [
  {"id": "FS-001", "title": "在线学习平台", "wiki_token": "Ft7...", "case": "education", "priority": 1}
]}
```
可选给 `case`(education/ecommerce/blog)提示——给了就直接走引擎真实生成。

### 3. 运行
```bash
HARNESS_BACKLOG_SOURCE=feishu bash delivery-loop/run_backlog.sh
```
- 拉到的正文落到 `delivery-loop/specs/<id>.md`;
- 状态回写到 `backlog/feishu_state.json`(docx 无法改字段,故落本地);
- **无 `case` 的文档 → 标 `fetched`**(Spec 已获取);「自由文本 Spec → case → 真实生成」需 spec 编译步骤(下一增量)。

> 说明:docx 状态只能落本地。等转**多维表格 Bitable**做需求池,`report()` 换成 record 更新即可真正写回飞书,且天然带 status 字段。

---

## 部署到阿里云 ECS(L4,拉取式)

代码已发布到 GitHub 后,ECS 侧直接 `git` 拉取运行(不 scp 源码)。`deployer.py`
SSH 进 ECS 执行:clone/pull 目标仓 → 进 `<subdir>/` → `pip install` → 杀旧进程 →
`nohup` 起 `app.py`(按 `app.pid` 隔离,不误杀其它样例)。

### 1. 配凭证(不要贴进任何对话/仓库)
仓库根 `.env`:
```bash
ECS_SSH_PASSWORD=你的ECS密码
# 若 loop-sample 为私有仓,ECS 拉取也需 GITHUB_TOKEN(已在 GitHub 发布那步配过)
```
本机需装 `sshpass`(密码认证):macOS `brew install sshpass`。

### 2. 配目标机器并开关
```bash
export ECS_HOST="47.76.211.100"
export ECS_DEPLOY=1
HARNESS_AUTOCOMMIT=1 bash delivery-loop/run_backlog.sh
```
部署成功后应用在 `http://<ECS_HOST>:<ECS_APP_PORT>/`(默认 5000)。

> 需在阿里云**安全组**放行 `ECS_APP_PORT`;ECS 预装 `python3`/`git`。token 与密码在日志中均替换为 `****`。

---

## 演进挂点

- **L1 发布到 GitHub**:✅ 已实现(子目录/分支两种布局)。`publisher.py` 负责 git 提交/推送。
- **接真实来源**:新增 `adapters/<source>_adapter.py` 实现 `Adapter`,在 `__init__.py`
  的 `load_adapter()` 登记。已实现 local / feishu。
- **spec 编译**:把 `fetched`(飞书自由文本 Spec)打通到真实生成。
- **L4 部署**:✅ 已实现(拉取式 SSH 部署到 ECS)。`deployer.py` 负责远端拉取+重启。
