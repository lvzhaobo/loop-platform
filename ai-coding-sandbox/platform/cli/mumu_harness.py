#!/usr/bin/env python3
"""
MumuHarness CLI — init / doctor / calibrate / prune / report

五段职责：
  init       按 M1 / M2 / M3 生成四区骨架与 H01-H08 文档
  doctor     体检：四区是否齐、有没有破界、文档是否可判定
  calibrate  红绿测：检查器是否真能拦住、真能放行
  prune      减法：哪些规则可退场、哪些登记了检查却没实现
  report     聚合：一次看多个 harness 的结构体检与跨项目同号规则

定位（与另两个 CLI 的分工）：
  mumuloop.py        跑一条任务线：check → 工单 → trace
  ticket_bridge.py   把收敛失败的本地工单推到禅道 / Jira
  mumu_harness.py    作用于项目本身：生骨架、查结构、验检查器、砍冗余规则

用法：
  python3 platform/cli/mumu_harness.py init --profile M2 --dir ./my-project
  python3 platform/cli/mumu_harness.py doctor --dir ./my-project [--json]
  python3 platform/cli/mumu_harness.py calibrate --dir ./my-project [--json]
  python3 platform/cli/mumu_harness.py prune --dir ./my-project [--json]
  python3 platform/cli/mumu_harness.py report --all [--depth 4] [--json]
  python3 platform/cli/mumu_harness.py report --dirs ./a ./b [--json]

退出码：
  init       0 = 生成完成
  doctor     0 = 无 FAIL；1 = 有 FAIL；2 = 目录不可用
  calibrate  0 = 红测全中且绿测无误报；1 = 红测漏检；2 = 绿测误报
  prune      0 = 无悬空规则；1 = 有 DANGLING（登记了检查器没实现）；2 = 目录不可用
  report     0 = 全部项目 OK；1 = 有项目 FAIL；2 = 没找到项目
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

CLI_DIR = Path(__file__).resolve().parent
PLATFORM = CLI_DIR.parent
MUMULOOP = PLATFORM.parent
TODAY = datetime.now().strftime("%Y-%m-%d")

class ProfileSpec(TypedDict):
    name: str
    docs: list[str]
    bridge: bool


PROFILES: dict[str, ProfileSpec] = {
    "M1": {"name": "个人", "docs": ["H03", "H08"], "bridge": False},
    "M2": {"name": "沙箱", "docs": ["H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08"], "bridge": False},
    "M3": {"name": "团队", "docs": ["H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08"], "bridge": True},
}

# 门禁资产文件名特征：出现在执行区即判破界
GATE_ASSET_NAMES = {"check.py", "exempt.json", "exemptions.json"}
GATE_ASSET_SUFFIX = (".rules.md",)
EXEC_DIRS = ("src", "app", "lib", "backend", "service", "services")


# ============================================================
# 模板
# ============================================================

def tpl_agents(profile: str, project: str) -> str:
    return f"""# AGENTS.md — 注入入口

> 项目：{project}
> 只放路由与硬约束。规则正文在 `rules/`，检查实现在 `scripts/check.py`。
> 装配级别 {profile} · 由 mumu_harness init 生成于 {TODAY}

## 一、这个项目是什么

（一句话。AI 每次会话都读到这里，超过三行说明该拆到 rules/）

## 二、动手前读哪份

| 场景 | 读哪份 |
|:---|:---|
| 改业务代码 | `rules/` 下对应规则文件 |
| 加规则 / 改检查 | `governance/H03-约束清单.md`、`governance/H05-检查层规格.md` |
| 交付前 | `governance/H04-注入层规格.md` 的 DoD |

## 三、硬约束（违反即拦截）

- 密钥 / 密码 / Token 不落代码，走环境变量
- 生产配置不进仓库
- 门禁资产（`rules/`、`scripts/check.py`、豁免清单）不得由被检代码顺手改掉

## 四、命令

```bash
python3 scripts/check.py <target>                      # 退出码 0=通过 1=违规
python3 platform/cli/mumu_harness.py doctor --dir .    # 结构体检
python3 platform/cli/mumu_harness.py calibrate --dir . # 红绿测
```

## 五、完成判据（DoD）

- [ ] `check.py` 退出码 0
- [ ] 变更对应的规则已登记在 H03
- [ ] 新增规则已过红绿测，H08 有记录
"""


def tpl_h01(project: str) -> str:
    return f"""# H01 · Harness 总则与索引

- 项目：{project}
- 建立：{TODAY}
- 状态：Draft

## 一、编号规则

| 类型 | 格式 | 示例 |
|:---|:---|:---|
| 规则 | `HS-<域>-<三位>` | HS-SEC-001 |
| 检查 | `HC-<域>-<三位>` | HC-SEC-001 |
| 审查项 | `HR-<域>-<三位>` | HR-SEC-001 |
| 豁免 | `HE-<域>-<三位>` | HE-CFG-001 |
| 校准用例 | `HU-<域>-<三位>` | HU-SEC-001 |
| finding | `HF-<日期>-<两位>` | HF-20261017-01 |

域取：ERR / SEC / CFG / ARCH / TEST / DOC。

## 二、文档索引

| 编号 | 文档 | 回答的问题 |
|:---|:---|:---|
| H01 | 本篇 | 规则约定与索引 |
| H02 | 场景与边界单 | 约束落在哪个区、风险半径多大 |
| H03 | 约束清单 | 有哪些约束、锚点在哪、谁负责 |
| H04 | 注入层规格 | AI 动手前必须知道什么 |
| H05 | 检查层规格 | 什么必须机器拦、怎么拦、怎么豁免 |
| H06 | 审查层规格 | 机检抓不住的谁兜底 |
| H07 | 闭环层规格 | 拦下来之后怎么办、什么时候停 |
| H08 | 校准与追踪 | 每条门禁真红过吗、改过什么、谁签的 |

## 三、写作四律

1. 一文一职：每份文档只回答一个问题
2. 引用不复制：规则正文只在 H03
3. 可判定优先：写不出判定方式的话不进清单
4. 留白要显式：缺的写"待定 + 触发条件"，不留空

## 四、状态流转

`Draft → Review → Approved → Active → Retired`

没有校准过的 Approved 规则不许当门禁。
"""


def tpl_h02(project: str) -> str:
    return f"""# H02 · 场景与边界单

- 项目：{project}
- 状态：Draft

## 一、四区落点

| 区 | 放什么 | 谁能写 | 机器判据 |
|:---|:---|:---|:---|
| Z-G 治理区 | H03 规则真源、H08 校准记录、豁免清单、findings | 人签（AI 只能起草到临时文件） | 每次变更必须有 `signedBy` |
| Z-A 装配区 | AGENTS.md、rules/*.md、审查清单、check.py、loop 配置 | AI 可写，合入前人审 | 不得 import 业务模块；不得出现连接串/密钥 |
| Z-E 执行区 | 源码、测试、非生产配置、项目文档 | AI 主写 | 出现门禁资产文件名即报 |
| Z-O 观测区 | trace JSONL、工单、验证报告、指标 | 机器追加；人只读 | 只允许 append |

红线：密钥 / 生产配置 / H08 历史版本 / 门禁自身。

## 二、关键切分

红测样本（违规样例）属于门禁资产，放 Z-A；被测代码放 Z-E。
期望值不与代码同区——堵"改期望值让门禁变绿"。

## 三、风险半径

| 问题 | 答案 |
|:---|:---|
| 这个项目改坏了影响谁 | 待定 |
| 有没有生产数据/资金链路 | 待定 |
| 需要几层门禁（注入/检查/审查/闭环） | 待定 |

## 四、挂载级别

- 装配级别：见 `.harness/config.json` 的 `profile`（M1 个人 / M2 沙箱 / M3 团队）
- 升级条件：待定
"""


def tpl_h03(project: str) -> str:
    return f"""# H03 · 约束清单（规则真源）

- 项目：{project}
- 状态：Draft

> 规则只在本文件出现一次，其他文档只引用 ID。
> 每条规则四要素齐：锚点（AI 之外）+ 检查（机器或审查项）+ 失败后路径 + owner。

| 规则ID | 规则陈述（可判定） | 判据锚点 | 类型 | 层 | 检查/审查 | 豁免 | 状态 | Owner |
|:--|:--|:--|:--:|:--:|:--|:--|:--:|:--|
| HS-SEC-001 | 密钥/密码/Token 禁止以字面量硬编码，统一走环境变量 | 待补：历史事故文档位置 | 历史bug | 2-检查 | HC-SEC-001 | 无 | backlog | 待定 |

## 填写规则

- **规则陈述**：必须可判定。出现"合理""尽量""优雅"直接退回
- **判据锚点**：只有三类合法值——历史 bug（带文档位置）/ 上游契约（带文档编号）/ 线上结果（带数据来源）
- **层**：1-注入 / 2-检查 / 3-审查 / 4-闭环，一层只能一条主归属
- **状态**：`active`（红测通过）/ `dormant`（从未红过）/ `backlog`（锚点未定）/ `retired`（已下线，保留行）
- **Owner**：具体人或角色，不写"团队"
"""


def tpl_h04(project: str) -> str:
    return f"""# H04 · 注入层规格

- 项目：{project}
- 状态：Draft

## 一、注入结构

| 层级 | 文件 | 加载时机 | 放什么 |
|:---|:---|:---|:---|
| L1 常驻 | AGENTS.md | 每次会话 | 路由 + 硬约束，控制在 100 行内 |
| L2 规则 | rules/*.md | 改对应域时 | 规则 / 正例 / 反例 / 为什么 / 检查方式 / 边界说明 |
| L3 按需 | governance/*.md | 改门禁时 | H02-H08 |

## 二、规则表（只列 ID）

| 规则ID | 一句话 | 规则文件 |
|:--|:--|:--|
| HS-SEC-001 | 密钥不落代码 | rules/security.md |

## 三、命令

（与 AGENTS.md §四 保持一致，不重复定义）

## 四、DoD

- [ ] 变更范围内的规则文件已更新
- [ ] 新增依赖/配置已在 H03 登记
"""


def tpl_h05(project: str) -> str:
    return f"""# H05 · 检查层规格

- 项目：{project}
- 状态：Draft

## 一、Check 定义

| 检查ID | 对应规则 | 检查方式 | 命中样例 | 豁免 |
|:--|:--|:--|:--|:--|
| HC-SEC-001 | HS-SEC-001 | 正则扫字面量 | 待补 | 无 |

## 二、退出码语义

| 码 | 含义 | 调用方动作 |
|:--:|:---|:---|
| 0 | 全部通过 | 进下一阶段 |
| 1 | 存在违规 | 生成工单 / 触发反馈 |
| 2 | 检查器自身错误 | 停下修检查器，不算业务通过 |

## 三、豁免清单

| 豁免ID | 范围 | 理由 | 期限 | 替代控制 |
|:--|:--|:--|:--|:--|
| HE-CFG-001 | config.py | 配置集中点 | 长期 | 审查项 HR-CFG-001 |

## 四、检查器约束

- 检查器不检查自己（跳过 scripts/）
- 检查器不 import 业务模块
- 检查器不读生产配置
"""


def tpl_h06(project: str) -> str:
    return f"""# H06 · 审查层规格

- 项目：{project}
- 状态：Draft

> 只收机检抓不住的部分。机检能查的归 H05。

## 一、机检盲区清单

| 审查项ID | 对应规则 | 为什么机检抓不住 | 抽查比例 |
|:--|:--|:--|:--|
| HR-DOC-001 | HS-DOC-001 | 回滚步骤是否可执行需人判断 | 100% |

## 二、审查动作

| 审查项 | 谁审 | 何时 | 不过怎么办 |
|:--|:--|:--|:--|
| HR-DOC-001 | 交付负责人 | 合并前 | 退回补写 |
"""


def tpl_h07(project: str) -> str:
    return f"""# H07 · 闭环层规格

- 项目：{project}
- 状态：Draft

## 一、闭环四要素

| 要素 | 取值 | 本项目 |
|:---|:---|:---|
| 触发 | 检查退出码 1 | 是 |
| 评分 | 违规条数 / 按规则计数 | 是 |
| 修正 | feedback 文本喂回 AI | 是 |
| 终止 | 违规归零 / 达轮次上限 / 人工接管 | 是 |

## 二、终止三态

| 状态 | 条件 | 后续 |
|:---|:---|:---|
| closed | 违规归零 | 记 trace，结束 |
| pending_fix | 仍有违规且未达上限 | 下一轮 |
| escalate | 达上限仍有违规 | 开票 → 工单桥 |

## 三、trace schema

```json
{{"round": 1, "ts": "2026-10-17T10:00:00", "target": "backend/app", "violations": 3, "byRule": {{"HS-SEC-001": 2}}, "score": 40, "action": "feedback", "result": "pending_fix"}}
```

## 四、重试上限

默认 3 轮。达上限仍不收敛 → escalate，不静默重试。
"""


def tpl_h08(project: str) -> str:
    return f"""# H08 · 校准与追踪矩阵

- 项目：{project}
- 状态：Draft

## 一、规则追踪

| 规则ID | 检查ID | 红测用例 | 红测结果 | 绿测结果 | 关联 finding | 最近校准 | H03 校验和 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| HS-SEC-001 | HC-SEC-001 | HU-SEC-001 | 未跑 | 未跑 | — | — | — |

判据：
- `active` 规则必须同时有红测与绿测结果，缺一降级为 `dormant`
- 同一规则连续两个周期 0 命中 → 触发复核
- H03 校验和与当前文件不一致 → 规则改了没重测

## 二、变更记录

| 日期 | 规则ID | 方向 | 变更内容 | 触发来源 | 红绿测 | 替代控制 | 签名 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| — | — | — | — | — | — | — | — |

方向四值：`new / tighten / loosen / delete`。
`loosen` 与 `delete` 必须有替代控制与签名，缺一视为无效变更。
"""


def tpl_rule_template() -> str:
    return """# 规则：<域名>

> 六段结构。一条规则一个文件，放 `rules/`。

## 规则

（一句话，可判定。出现"合理""尽量"就是没写完）

## 正例

```python
# 正确写法
```

## 反例

```python
# 会被拦下来的写法
```

## 为什么

（锚点：历史 bug / 上游契约 / 线上结果，指向具体位置）

## 检查方式

- 检查 ID：HC-<域>-<三位>
- 机器判定：`python3 scripts/check.py <target>`
- 人工判定：（机检抓不住的部分才写）

## 边界说明

（什么时候不适用，写清楚，否则会被静默豁免）
"""


def tpl_check_py() -> str:
    return '''#!/usr/bin/env python3
"""
规则检查器骨架 — 一条规则一个 Check。

用法：
  python3 scripts/check.py <target>
  python3 scripts/check.py --feedback      # 失败时输出 AI 修正指令

退出码：0 = 全部通过；1 = 存在违规；2 = 检查器自身错误
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".venv", "venv", ".git", "node_modules", "scripts", "tests"}


@dataclass
class Check:
    id: str
    desc: str
    pattern: str
    rule_file: str
    fix: str
    exempt_files: set = field(default_factory=set)


# 在这里登记检查项：一条规则一条 Check
CHECKS = [
    Check(
        "HC-SEC-001",
        "密钥/密码/Token 禁止硬编码",
        r"(password|passwd|secret|token)\\s*=\\s*[\\"'][^\\"']{6,}",
        "rules/security.md",
        "改为从环境变量读取：os.environ['XXX']",
        exempt_files={"config.py"},
    ),
]


def iter_files(target: Path):
    if target.is_file():
        yield target
        return
    for p in target.rglob("*"):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
            yield p


def run(target: Path):
    violations = []
    for f in iter_files(target):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for c in CHECKS:
            if f.name in c.exempt_files:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(c.pattern, line):
                    violations.append((c, f, i, line.strip()))
    return violations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=str(PROJECT_ROOT / "src"))
    ap.add_argument("--feedback", action="store_true", help="输出 AI 修正指令")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"[ERROR] 目标不存在：{target}", file=sys.stderr)
        return 2

    violations = run(target)
    if not violations:
        print(f"[OK] 0 违规（{target}）")
        return 0

    for c, f, line_no, evidence in violations:
        print(f"[FAIL] {c.id} {c.desc}")
        print(f"        {f}:{line_no} {evidence}")
    print(f"\\n[SUMMARY] {len(violations)} 处违规")

    if args.feedback:
        print("\\n## 修正指令")
        for i, (c, f, line_no, _) in enumerate(violations, 1):
            print(f"{i}. [{c.id}] {f}:{line_no} → {c.fix}（规则见 {c.rule_file}）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def tpl_tasks_readme() -> str:
    return """# 红绿测样本

## 目录

- `red/`   应当被拦住（红测）
- `green/` 应当放行（绿测）

## 样本格式

两种都支持：

1. **裸文件**：直接放 `.py` 等源码，默认期望与所在目录一致
2. **JSON 描述**（更精确）：

```json
{"target": "backend/app/db.py", "expect_rule": "HC-SEC-001"}
```

`target` 相对项目根；`expect_rule` 可选，指定时要求命中的正是这条规则。

## 判据

- 红测：checker 退出码 1，且（若指定）`expect_rule` 命中
- 绿测：checker 退出码 0
- 红测漏检 = 门禁有洞；绿测误报 = 规则过严

每次改规则都要重跑，结果写进 H08。
"""


def tpl_exemptions(project: str) -> str:
    return f"""# 豁免清单

- 项目：{project}
- 状态：Draft

> 每条豁免单独编号，带理由、期限、替代控制。豁免写在检查器注释里等于没人知道。

| 豁免ID | 规则ID | 范围 | 理由 | 期限 | 替代控制 | 签名 |
|:--|:--|:--|:--|:--|:--|:--|
| HE-CFG-001 | HS-SEC-001 | config.py | 配置集中点 | 长期 | 审查项 HR-CFG-001 | — |
"""


def tpl_review_log(project: str) -> str:
    return f"""# 季度复审记录

- 项目：{project}

> M3 团队模板要求季度复审：哪些规则从未命中、哪些豁免该收回、哪些 owner 已离岗。

| 日期 | 复审人 | 范围 | 结论 | 动作 |
|:--|:--|:--|:--|:--|
| — | — | 全量规则 | — | — |
"""


def tpl_bridge_config() -> str:
    return json.dumps({
        "provider": "zentao",
        "threshold": "escalate",
        "priority_map": {"escalate": "P1", "pending_fix": "P3"},
        "zentao": {
            "base_url": "http://127.0.0.1:8080",
            "api_base": "/api.php/v1",
            "account_env": "MUMULOOP_ZENTAO_ACCOUNT",
            "password_env": "MUMULOOP_ZENTAO_PASSWORD"
        },
        "_note": "凭据不落文件：只写环境变量名。"
    }, ensure_ascii=False, indent=2) + "\n"


# ============================================================
# init
# ============================================================

def cmd_init(args: argparse.Namespace) -> int:
    profile: str = args.profile.upper()
    force: bool = bool(args.force)
    if profile not in PROFILES:
        print(f"[ERROR] 未知级别 {profile}，可选：{', '.join(PROFILES)}")
        return 2

    root: Path = Path(args.dir).expanduser().resolve()
    project: str = args.name or root.name
    spec = PROFILES[profile]

    if root.exists() and any(root.iterdir()) and not force:
        print(f"[ERROR] 目录非空：{root}\n加 --force 才会覆盖已存在文件")
        return 2
    root.mkdir(parents=True, exist_ok=True)

    tpl = {
        "H01": tpl_h01, "H02": tpl_h02, "H03": tpl_h03, "H04": tpl_h04,
        "H05": tpl_h05, "H06": tpl_h06, "H07": tpl_h07, "H08": tpl_h08,
    }
    files: dict[str, str] = {}
    files["AGENTS.md"] = tpl_agents(profile, project)
    files["rules/_TEMPLATE.md"] = tpl_rule_template()
    files["scripts/check.py"] = tpl_check_py()
    files["EXEMPTIONS.md"] = tpl_exemptions(project)

    gov_dir = "governance" if profile != "M1" else "harness"
    for d in spec["docs"]:
        files[f"{gov_dir}/{d}.md"] = tpl[d](project)

    if profile != "M1":
        files["tasks/README.md"] = tpl_tasks_readme()
    if spec["bridge"]:
        files["bridge/bridge-config.json"] = tpl_bridge_config()
        files[f"{gov_dir}/REVIEW-LOG.md"] = tpl_review_log(project)

    created: list[str] = []
    skipped: list[str] = []
    for rel, content in files.items():
        p = root / rel
        if p.exists() and not force:
            skipped.append(rel)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        created.append(rel)

    for d in ("tasks/samples/red", "tasks/samples/green", "logs"):
        _ = Path(root / d).mkdir(parents=True, exist_ok=True)

    config = {
        "profile": profile,
        "profileName": spec["name"],
        "project": project,
        "created": TODAY,
        "zones": {
            "Z-G": [f"{gov_dir}/", "EXEMPTIONS.md"],
            "Z-A": ["AGENTS.md", "rules/", "scripts/"],
            "Z-E": list(EXEC_DIRS) + ["tests/"],
            "Z-O": ["logs/"],
        },
        "checker": "scripts/check.py",
        "gov_dir": gov_dir,
        "logs_dir": "logs",
        "samples_dir": "tasks/samples",
    }
    (root / ".harness").mkdir(exist_ok=True)
    (root / ".harness/config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"==== MumuHarness init · {profile} {spec['name']} · {project} ====")
    print(f"[目录] {root}")
    for rel in created:
        print(f"  + {rel}")
    for rel in skipped:
        print(f"  = {rel}（已存在，跳过）")
    print(f"\n[完成] 生成 {len(created)} 个文件，跳过 {len(skipped)} 个")
    print("[下一步]")
    print(f"  1. 填 {gov_dir}/H03 的规则表（锚点 + 检查 + owner 四要素）")
    print(f"  2. 在 scripts/check.py 登记对应 Check")
    print(f"  3. python3 platform/cli/mumu_harness.py doctor --dir {root}")
    return 0


# ============================================================
# doctor
# ============================================================

def _load_config(root: Path) -> dict[str, Any]:
    f = root / ".harness/config.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"gov_dir": "governance", "checker": "scripts/check.py",
            "logs_dir": "logs", "samples_dir": "tasks/samples"}


def _find_gate_assets_in_exec(root: Path) -> list[str]:
    hits: list[str] = []
    for d in EXEC_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and (p.name in GATE_ASSET_NAMES or p.name.endswith(GATE_ASSET_SUFFIX)):
                hits.append(str(p.relative_to(root)))
    return hits


def _parse_h03(path: Path) -> tuple[int, list[list[str]]]:
    """返回 (表头列数, 数据行列表)"""
    if not path.exists():
        return 0, []
    lines = path.read_text(encoding="utf-8").splitlines()
    header = 0
    rows: list[list[str]] = []
    in_table = False
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not in_table and "规则ID" in "".join(cells):
            header = len(cells)
            in_table = True
            continue
        if in_table and not re.match(r"^[:\-\s|]+$", s):
            rows.append(cells)
    return header, rows


def _run_doctor(root: Path) -> dict[str, Any]:
    """跑 D01-D10，返回结构化结果。doctor 与 report 共用同一份判据。"""
    cfg = _load_config(root)
    gov = root / cfg.get("gov_dir", "governance")
    results: list[dict[str, str]] = []

    def add(level: str, code: str, msg: str, detail: str = "") -> None:
        results.append({"level": level, "code": code, "msg": msg, "detail": detail})

    # D01 四区齐备（执行区缺失只 WARN：刚 init 时业务目录还不存在）
    missing = []
    if not gov.is_dir():
        missing.append(cfg.get("gov_dir", "governance") + "/")
    if not (root / "scripts").is_dir():
        missing.append("scripts/")
    if not (root / cfg.get("logs_dir", "logs")).is_dir():
        missing.append(cfg.get("logs_dir", "logs") + "/")
    if missing:
        add("FAIL", "D01", "治理/装配/观测区不全", "缺：" + "、".join(missing))
    elif not any((root / d).is_dir() for d in EXEC_DIRS):
        add("WARN", "D01", "执行区尚未建立", "建 " + " 或 ".join(EXEC_DIRS[:3]) + " 后复查")
    else:
        add("PASS", "D01", "四区齐备")

    # D02 执行区出现门禁资产
    hits = _find_gate_assets_in_exec(root)
    if hits:
        add("FAIL", "D02", "执行区出现门禁资产", "、".join(hits))
    else:
        add("PASS", "D02", "执行区无门禁资产")

    # D03 规则正文双写（启发式）
    agents = root / "AGENTS.md"
    dup = []
    if agents.exists():
        for i, line in enumerate(agents.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"HS-[A-Z]+-\d{3}", line) and len(line) > 90:
                dup.append(f"AGENTS.md:{i}")
    if dup:
        add("WARN", "D03", "AGENTS.md 疑似贴了规则正文", "、".join(dup))
    else:
        add("PASS", "D03", "AGENTS.md 未双写规则正文")

    # D04 装配区引用业务模块
    checker = root / cfg.get("checker", "scripts/check.py")
    imp = []
    if checker.exists():
        for line in checker.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:from|import)\s+([\w.]+)", line)
            if m and m.group(1).split(".")[0] in EXEC_DIRS:
                imp.append(line.strip())
    if imp:
        add("FAIL", "D04", "检查器 import 了业务模块", "；".join(imp))
    else:
        add("PASS", "D04", "检查器未污染业务模块")

    # D05 / D06 H03 结构与规则要素
    h03 = gov / "H03.md"
    header, rows = _parse_h03(h03)
    if header == 0:
        add("FAIL", "D05", "H03 缺失或表头不含「规则ID」", str(h03.relative_to(root)))
        active_bad = []
    else:
        add("PASS", "D05", f"H03 表头 {header} 列")
        active_bad = []
        for r in rows:
            if len(r) < header:
                continue
            rid, status = r[0], r[7] if len(r) > 7 else ""
            if status.lower() != "active":
                continue
            checker_id = r[5] if len(r) > 5 else ""
            owner = r[8] if len(r) > 8 else ""
            if not checker_id or checker_id in ("—", "-", "无"):
                active_bad.append(f"{rid} 缺检查ID")
            if not owner or owner in ("待定", "—", "-"):
                active_bad.append(f"{rid} 缺 owner")
    if active_bad:
        add("FAIL", "D06", "active 规则要素不全", "；".join(active_bad))
    elif header:
        add("PASS", "D06", "active 规则要素齐全")

    # D07 校准记录
    cal = root / cfg.get("logs_dir", "logs") / "calibration.jsonl"
    has_active = any(len(r) > 7 and r[7].lower() == "active" for r in rows)
    if has_active and not (cal.exists() and cal.stat().st_size > 0):
        add("WARN", "D07", "有 active 规则但没有校准记录", "先跑 calibrate")
    else:
        add("PASS", "D07", "校准记录状态正常")

    # D08 凭据落文件（启发式）
    leaks = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in (".json", ".yaml", ".yml", ".env", ".ini"):
            continue
        if any(x in p.parts for x in ("node_modules", ".git", "logs")):
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"(password|passwd|token|secret|api_key)\s*[\"']?\s*[:=]\s*[\"'][^\"']{8,}[\"']",
                             line, re.IGNORECASE):
                    if re.search(r"_env\s*[\"']?\s*:", line):
                        continue
                    leaks.append(f"{p.relative_to(root)}:{i}")
        except (UnicodeDecodeError, OSError):
            continue
    if leaks:
        add("FAIL", "D08", "配置文件中疑似明文凭据", "、".join(leaks[:5]))
    else:
        add("PASS", "D08", "未见明文凭据")

    # D09 观测区被改写
    logs_rel = cfg.get("logs_dir", "logs")
    try:
        proc = subprocess.run(
            ["git", "log", "--diff-filter=M", "--name-only", "--pretty=format:", "--", logs_rel + "/"],
            cwd=root, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            add("SKIP", "D09", "非 git 仓库，跳过观测区改写检查")
        elif proc.stdout.strip():
            add("WARN", "D09", "观测区文件被改写", proc.stdout.strip().splitlines()[0])
        else:
            add("PASS", "D09", "观测区无改写记录")
    except (subprocess.SubprocessError, OSError):
        add("SKIP", "D09", "git 不可用，跳过观测区改写检查")

    # D10 红测样本
    red_dir = root / cfg.get("samples_dir", "tasks/samples") / "red"
    n_red = len([p for p in red_dir.glob("*") if p.is_file()]) if red_dir.is_dir() else 0
    if n_red == 0:
        add("WARN", "D10", "没有红测样本", "没有样本就没有校准证据")
    else:
        add("PASS", "D10", f"红测样本 {n_red} 条")

    fails = [r for r in results if r["level"] == "FAIL"]
    warns = [r for r in results if r["level"] == "WARN"]
    return {"dir": str(root), "name": root.name, "profile": cfg.get("profile"),
            "results": results, "fail": len(fails), "warn": len(warns)}


def cmd_doctor(args: argparse.Namespace) -> int:
    root: Path = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"[ERROR] 目录不存在：{root}")
        return 2

    out = _run_doctor(root)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"==== MumuHarness doctor · {root.name} ====")
        for r in out["results"]:
            mark = {"PASS": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[r["level"]]
            print(f"{mark} {r['code']} {r['msg']}" + (f" — {r['detail']}" if r["detail"] else ""))
        print(f"\n[小结] FAIL {out['fail']} · WARN {out['warn']} · 共 {len(out['results'])} 项")

    return 1 if out["fail"] else 0


# ============================================================
# calibrate
# ============================================================

def _collect_cases(case_dir: Path, root: Path, expect_exit: int) -> list[dict]:
    cases = []
    if not case_dir.is_dir():
        return cases
    for p in sorted(case_dir.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix == ".json":
            try:
                spec = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            cases.append({
                "name": p.name,
                "target": root / spec.get("target", ""),
                "expect_rule": spec.get("expect_rule"),
                "expect_exit": expect_exit,
            })
        else:
            cases.append({"name": p.name, "target": p, "expect_rule": None,
                          "expect_exit": expect_exit})
    return cases


def _run_checker(checker: Path, target: Path) -> tuple[int, list[str], str]:
    proc = subprocess.run([sys.executable, str(checker), str(target)],
                          capture_output=True, text=True)
    rules = re.findall(r"\[FAIL\]\s+(\S+)", proc.stdout)
    return proc.returncode, rules, proc.stdout


def cmd_calibrate(args: argparse.Namespace) -> int:
    root: Path = Path(args.dir).expanduser().resolve()
    as_json: bool = bool(args.json)
    cfg = _load_config(root)
    checker = Path(args.checker) if args.checker else root / cfg.get("checker", "scripts/check.py")
    if not checker.exists():
        print(f"[ERROR] 检查器不存在：{checker}")
        return 2

    base = root / cfg.get("samples_dir", "tasks/samples")
    red = _collect_cases(base / "red", root, expect_exit=1)
    green = _collect_cases(base / "green", root, expect_exit=0)
    if not red and not green:
        print(f"[ERROR] 没有样本：{base}/red、{base}/green")
        return 2

    missed, false_pos, red_detail, green_detail = [], [], [], []
    for c in red:
        if not c["target"].exists():
            missed.append(f"{c['name']}（目标不存在）")
            continue
        code, rules, _ = _run_checker(checker, c["target"])
        ok = code == 1 and (not c["expect_rule"] or c["expect_rule"] in rules)
        red_detail.append({"case": c["name"], "hit": ok, "exit": code, "rules": rules})
        if not ok:
            missed.append(c["name"])

    for c in green:
        if not c["target"].exists():
            false_pos.append(f"{c['name']}（目标不存在）")
            continue
        code, rules, _ = _run_checker(checker, c["target"])
        ok = code == 0
        green_detail.append({"case": c["name"], "hit": ok, "exit": code, "rules": rules})
        if not ok:
            false_pos.append(c["name"])

    n_red_hit = sum(1 for d in red_detail if d["hit"])
    n_green_ok = sum(1 for d in green_detail if d["hit"])

    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "checker": str(checker.relative_to(root)) if str(checker).startswith(str(root)) else str(checker),
        "red": {"total": len(red), "hit": n_red_hit, "missed": missed},
        "green": {"total": len(green), "pass": n_green_ok, "falsePositives": false_pos},
        "ok": not missed and not false_pos,
    }
    logs_dir = root / cfg.get("logs_dir", "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    cal_file = logs_dir / "calibration.jsonl"
    with open(cal_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if as_json:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    else:
        print(f"==== MumuHarness calibrate · {root.name} ====")
        print(f"[红测] {n_red_hit}/{len(red)} 命中" + (f"（漏 {len(missed)}：{'、'.join(missed)}）" if missed else "（无漏检）"))
        print(f"[绿测] {n_green_ok}/{len(green)} 放行" + (f"（误报 {len(false_pos)}：{'、'.join(false_pos)}）" if false_pos else "（无误报）"))
        print(f"[结果] {'PASS' if entry['ok'] else 'FAIL'}")
        print(f"[记录] 已追加 {cal_file.relative_to(root)}")

    if missed:
        return 1
    if false_pos:
        return 2
    return 0


# ============================================================
# prune — 减法：哪些规则该退场、该补证据、悬空
# ============================================================

PLACEHOLDER = ("", "—", "-", "无", "待定", "n/a", "na", "none")


def _hc_to_check_id(hc: str) -> str:
    """HC-ERR-001 -> ERR001；已是 ERR001 的原样返回"""
    s = hc.strip().strip("`")
    if s.upper().startswith("HC-"):
        s = s[3:]
    return s.replace("-", "").replace("_", "").upper()


def _load_check_ids(checker: Path) -> set[str]:
    """文本扫描 check.py 里的检查项 ID，不 import 被检项目代码"""
    ids: set[str] = set()
    if not checker.exists():
        return ids
    text = checker.read_text(encoding="utf-8")
    for m in re.finditer(r'\bCheck\(\s*["\']([A-Za-z][\w-]*)["\']', text):
        ids.add(_hc_to_check_id(m.group(1)))
    for m in re.finditer(r'^\s*["\']([A-Z]{2,6}[-_]?\d{3})["\']\s*,', text, re.MULTILINE):
        ids.add(_hc_to_check_id(m.group(1)))
    return ids


def _red_evidence(root: Path, cfg: dict[str, Any],
                  checker: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """返回 (专属证据, 顺带命中)。专属 = 样本声明 expect_rule 且实际命中。"""
    own: dict[str, list[str]] = {}
    loose: dict[str, list[str]] = {}
    base = root / cfg.get("samples_dir", "tasks/samples")
    for c in _collect_cases(base / "red", root, expect_exit=1):
        if not c["target"].exists():
            continue
        code, rules, _ = _run_checker(checker, c["target"])
        if code != 1:
            continue
        hit = {_hc_to_check_id(r) for r in rules}
        for r in hit:
            loose.setdefault(r, []).append(c["name"])
        if c["expect_rule"]:
            er = _hc_to_check_id(c["expect_rule"])
            if er in hit:
                own.setdefault(er, []).append(c["name"])
    return own, loose


def cmd_prune(args: argparse.Namespace) -> int:
    root: Path = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"[ERROR] 目录不存在：{root}")
        return 2

    cfg = _load_config(root)
    gov = root / cfg.get("gov_dir", "governance")
    checker = root / cfg.get("checker", "scripts/check.py")
    h03 = gov / "H03.md"
    header, rows = _parse_h03(h03)
    if header == 0:
        print(f"[ERROR] H03 缺失或表头不含「规则ID」：{h03}")
        return 2
    if not checker.exists():
        print(f"[ERROR] 检查器不存在：{checker}")
        return 2

    check_ids = _load_check_ids(checker)
    own, loose = _red_evidence(root, cfg, checker)

    verdicts: list[dict[str, str]] = []
    ref_count: dict[str, list[str]] = {}
    for r in rows:
        if len(r) < header:
            continue
        rid = r[0]
        layer = r[4] if len(r) > 4 else ""
        hc = (r[5] if len(r) > 5 else "").strip()
        status = r[7].strip().lower() if len(r) > 7 else ""
        if status != "active":
            continue
        if hc not in PLACEHOLDER:
            ref_count.setdefault(hc, []).append(rid)
        if layer and not layer.startswith("2"):
            verdicts.append({"kind": "MANUAL", "rid": rid, "hc": hc or "—",
                             "why": f"第{layer}层，由人或闭环兜底，不进机器减法"})
            continue
        if hc in PLACEHOLDER:
            verdicts.append({"kind": "DANGLING", "rid": rid, "hc": hc or "—",
                             "why": "第2层规则没有检查ID"})
            continue
        cid = _hc_to_check_id(hc)
        if check_ids and cid not in check_ids:
            verdicts.append({"kind": "DANGLING", "rid": rid, "hc": hc,
                             "why": f"检查器里找不到 {cid}"})
            continue
        if cid in own:
            verdicts.append({"kind": "KEEP", "rid": rid, "hc": hc,
                             "why": "专属红测：" + "、".join(own[cid])})
        elif cid in loose:
            verdicts.append({"kind": "WEAK", "rid": rid, "hc": hc,
                             "why": "红测命中但样本未声明 expect_rule：" + "、".join(loose[cid][:3])})
        else:
            verdicts.append({"kind": "RETIRE", "rid": rid, "hc": hc,
                             "why": "无任何红测样本命中"})

    bucket: dict[str, list[dict[str, str]]] = {}
    for v in verdicts:
        bucket.setdefault(v["kind"], []).append(v)
    dup = {k: v for k, v in ref_count.items() if len(v) > 1}

    out = {
        "dir": str(root), "name": root.name,
        "active": len(verdicts), "checks": len(check_ids),
        "verdicts": verdicts,
        "retire": [v["rid"] for v in bucket.get("RETIRE", [])],
        "dangling": [v["rid"] for v in bucket.get("DANGLING", [])],
        "weak": [v["rid"] for v in bucket.get("WEAK", [])],
        "duplicate": dup,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        def names(k: str) -> str:
            return "、".join(v["rid"] for v in bucket.get(k, [])) or "—"

        print(f"==== MumuHarness prune · {root.name} ====")
        print(f"[规模] active 规则 {len(verdicts)} 条 · 检查器 {len(check_ids)} 项")
        print("")
        for kind in ("KEEP", "WEAK", "RETIRE", "DANGLING", "MANUAL"):
            for v in bucket.get(kind, []):
                print(f"[{kind:8s}] {v['rid']:14s} {v['hc']:12s} {v['why']}")
        print("")
        print("[减法建议]")
        print(f"  可退场    {len(bucket.get('RETIRE', []))} 条  {names('RETIRE')}")
        print(f"  需补证据  {len(bucket.get('WEAK', []))} 条  {names('WEAK')}")
        print(f"  悬空      {len(bucket.get('DANGLING', []))} 条  {names('DANGLING')}")
        dup_txt = "、".join(f"{k}→{'/'.join(v)}" for k, v in dup.items()) or "—"
        print(f"  重复引用  {len(dup)} 组  {dup_txt}")
        print("")
        print("[判据]")
        print("  KEEP     有专属红测：样本声明 expect_rule 且实际命中，删掉这条会漏检")
        print("  WEAK     有命中但样本没声明 expect_rule，删这条不影响现有门禁证据")
        print("  RETIRE?  无任何红测命中，删掉它门禁不会变红")
        print("  DANGLING 规则登记了检查ID，检查器里没有对应实现（自我欺骗）")
        print("  MANUAL   非第2层规则，本就不该有机器检查，不进减法")

    return 1 if out["dangling"] else 0


# ============================================================
# report — 多项目聚合
# ============================================================

# 递归找项目时跳过的大目录：扫进去只会拖慢，不会有 .harness
WALK_SKIP = {"node_modules", ".git", "__pycache__", ".venv", "venv",
             "dist", "build", ".next", "target", "logs"}


def _find_projects(base: Path, depth: int) -> list[Path]:
    """递归找含 .harness/config.json 的目录，超过 depth 层不再下探"""
    out: list[Path] = []
    base = base.resolve()
    for dirpath, dirnames, _files in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP]
        cur = Path(dirpath)
        if len(cur.relative_to(base).parts) > depth:
            dirnames[:] = []
            continue
        if (cur / ".harness/config.json").is_file():
            out.append(cur)
    return sorted(out)


def _last_calibration(root: Path, cfg: dict[str, Any]) -> str:
    f = root / cfg.get("logs_dir", "logs") / "calibration.jsonl"
    if not f.exists() or f.stat().st_size == 0:
        return "—"
    last = ""
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last = line
    if not last:
        return "—"
    try:
        e = json.loads(last)
    except json.JSONDecodeError:
        return "—"
    red, green = e.get("red", {}), e.get("green", {})
    return f"{red.get('hit', 0)}/{red.get('total', 0)}·{green.get('pass', 0)}/{green.get('total', 0)}"


def _dw(s: str) -> int:
    """显示宽度：中文按 2 列算"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(0, n - _dw(s))


def cmd_report(args: argparse.Namespace) -> int:
    depth = max(1, int(args.depth))
    roots: list[str] = list(args.dirs or [])
    if args.root:
        roots.append(args.root)
    # --all 或什么都没给：从当前目录往下找全部项目
    if args.all or not roots:
        roots.append(".")

    found: list[Path] = []
    for d in roots:
        p = Path(d).expanduser().resolve()
        if (p / ".harness/config.json").exists():
            found.append(p)
        elif p.is_dir():
            found.extend(_find_projects(p, depth))

    projects: list[Path] = []
    seen: set[str] = set()
    for p in found:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        projects.append(p)
    if not projects:
        print("[ERROR] 没找到含 .harness/config.json 的项目")
        return 2

    rows: list[dict[str, Any]] = []
    rule_ids: dict[str, list[str]] = {}
    for p in projects:
        cfg = _load_config(p)
        doc = _run_doctor(p)
        gov = p / cfg.get("gov_dir", "governance")
        _, hrows = _parse_h03(gov / "H03.md")
        active = [r for r in hrows if len(r) > 7 and r[7].strip().lower() == "active"]
        for r in active:
            rule_ids.setdefault(r[0], []).append(p.name)
        verdict = "FAIL" if doc["fail"] else ("WARN" if doc["warn"] else "OK")
        rows.append({
            "name": p.name, "dir": str(p), "profile": cfg.get("profile", "?"),
            "active": len(active), "fail": doc["fail"], "warn": doc["warn"],
            "cal": _last_calibration(p, cfg), "verdict": verdict,
            "fails": [f"{r['code']} {r['msg']}" for r in doc["results"] if r["level"] == "FAIL"],
            "warns": [f"{r['code']} {r['msg']}" for r in doc["results"] if r["level"] == "WARN"],
        })

    shared = {k: sorted(set(v)) for k, v in rule_ids.items() if len(set(v)) > 1}
    summary = {
        "projects": len(rows),
        "ok": sum(1 for r in rows if r["verdict"] == "OK"),
        "warn": sum(1 for r in rows if r["verdict"] == "WARN"),
        "fail": sum(1 for r in rows if r["verdict"] == "FAIL"),
        "rules": sum(r["active"] for r in rows),
        "sharedRules": shared,
    }

    if args.json:
        print(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2))
    else:
        cols = [("项目", 22), ("级别", 6), ("规则", 6), ("FAIL", 6), ("WARN", 6), ("红绿测", 14), ("结论", 6)]
        head = "".join(_pad(c, w) for c, w in cols)
        print(f"==== MumuHarness report · {len(rows)} 个项目 ====")
        print(head)
        print("-" * _dw(head))
        for r in rows:
            print("".join([
                _pad(r["name"], 22), _pad(str(r["profile"]), 6),
                _pad(str(r["active"]), 6), _pad(str(r["fail"]), 6),
                _pad(str(r["warn"]), 6), _pad(r["cal"], 14), r["verdict"],
            ]))
        print("")
        print(f"[汇总] {summary['projects']} 项目 · 规则 {summary['rules']} 条 · "
              f"OK {summary['ok']} / WARN {summary['warn']} / FAIL {summary['fail']}")
        if shared:
            print(f"[跨项目同号规则] {len(shared)} 条，可能是组织级候选（需人工确认涵义一致）")
            for k, v in sorted(shared.items()):
                print(f"  {k} → {'、'.join(v)}")
        issues = [(r["name"], r["fails"], r["warns"]) for r in rows if r["fails"] or r["warns"]]
        if issues:
            print("[待处理]")
            for name, fails, warns in issues:
                for f in fails:
                    print(f"  {name}: [FAIL] {f}")
                for w in warns:
                    print(f"  {name}: [WARN] {w}")

    return 1 if summary["fail"] else 0


# ============================================================
# main
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mumu_harness",
        description="MumuHarness CLI：init 生骨架 / doctor 体检 / calibrate 红绿测 / prune 减法 / report 聚合")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="按 M1/M2/M3 生成四区骨架与 H01-H08")
    p_init.add_argument("--profile", default="M2", choices=["M1", "M2", "M3", "m1", "m2", "m3"])
    p_init.add_argument("--dir", default=".", help="生成目录")
    p_init.add_argument("--name", default=None, help="项目名，缺省用目录名")
    p_init.add_argument("--force", action="store_true", help="覆盖已存在文件")
    p_init.set_defaults(func=cmd_init)

    p_doc = sub.add_parser("doctor", help="体检：四区、破界、文档要素")
    p_doc.add_argument("--dir", default=".", help="被检项目目录")
    p_doc.add_argument("--json", action="store_true", help="输出 JSON")
    p_doc.set_defaults(func=cmd_doctor)

    p_cal = sub.add_parser("calibrate", help="红绿测：验证检查器真能拦住、真能放行")
    p_cal.add_argument("--dir", default=".", help="被检项目目录")
    p_cal.add_argument("--checker", default=None, help="检查器路径，缺省读 .harness/config.json")
    p_cal.add_argument("--json", action="store_true", help="输出 JSON")
    p_cal.set_defaults(func=cmd_calibrate)

    p_prune = sub.add_parser("prune", help="减法：找出可退场 / 需补证据 / 悬空的规则")
    p_prune.add_argument("--dir", default=".", help="被检项目目录")
    p_prune.add_argument("--json", action="store_true", help="输出 JSON")
    p_prune.set_defaults(func=cmd_prune)

    p_rep = sub.add_parser("report", help="多项目聚合：一次看多个 harness 的结构体检")
    p_rep.add_argument("--all", action="store_true",
                       help="从当前目录往下找全部项目（等同 --root .）")
    p_rep.add_argument("--root", default=None, help="从这里递归找项目")
    p_rep.add_argument("--dirs", nargs="*", default=None, help="指定项目目录（可多个）")
    p_rep.add_argument("--depth", type=int, default=4, help="递归深度，默认 4")
    p_rep.add_argument("--json", action="store_true", help="输出 JSON")
    p_rep.set_defaults(func=cmd_report)

    return ap


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
