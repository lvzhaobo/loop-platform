# 番茄钟 · Spec 形态全链路跑通记录

> 记录时间：2026-07-22
> 一句话：只给 LLM **「番茄钟」三个字**，全自动跑完「编译规格 → 门禁 → 生成产物 → 验收 → 部署到 ECS:5300 → 公网验证」，中途零人工改代码。
>
> 线上地址：`http://<ECS-IP>:5300/`（真·交互计时器，非列表站；<ECS-IP> 见部署环境）

---

## 0. 背景与目标

Harness-4 原本只会生成「列表页 + 详情页 + 数据集」这类 **catalog 形态**内容站。
番茄钟这种**交互工具**不该套这个模子（否则会被编译成「番茄图鉴」列表站）。

本次要验证的能力：**新增 Spec 形态链路，让门禁「读 Spec 里声明的验收标准(TC/AC)」，而不是穷举应用类型**。

两条核心原则贯穿始终：

1. **additive（加选项，不推倒）**：新增 `--archetype spec` 分支，catalog 原路径一行未改。
2. **裁判 ≠ 运动员**：验收标准(TC/AC)由上游（人 / step2 的 LLM 在编译阶段）写好并冻结，
   生成器只负责「建到能过门禁」，不能自己发明验收标准。

---

## 1. 形态对比：catalog vs spec

| 维度 | catalog 形态（原有） | spec 形态（本次新增） |
|---|---|---|
| 判定依据 | `cases/<name>/case.json` 存在 | 无 case.json，但有 `spec/manifest.json` |
| 生成 prompt | `prompt.md`（焊死列表站） | `prompt.spec.md`（交互工具，明确"不是列表站"） |
| 编译器出口 | `compile_spec.derive` + `contract_gate` | `acceptance_gate` |
| 门禁 | `tools/verify.py`（硬读 catalog 字段） | `tools/verify_ac.py`（逐条执行 TC/AC） |
| 典型产物 | 博客/电商/教育内容站 | 番茄钟/计算器/画板等交互工具 |

形态由目录内容自动分流，互不干扰。

---

## 2. 涉及的模块与职责

### 2.1 编译层（step2：模糊需求 → 结构化规格）

**`harness-4/tools/spec_compiler.py`** —— 本次新增 `--archetype spec` 分支
（catalog 分支完全保留）。关键函数：

| 函数 | 职责 |
|---|---|
| `build_prompt_spec(free_text, name)` | 教 LLM 把自由文本编译成 spec 形态三件套；acceptance 只准用 verify_ac 支持的断言原语闭集；TC 引用的文件必须列进 manifest.required_files |
| `MOCK_SPEC`（番茄钟内置样例） | `--mock` 离线自证，不烧额度 |
| `gen_spec_blocks_spec(free_text, name, mock)` | 调 LLM（或取 mock）产出三件套文件块 |
| `write_case_spec(name, blocks)` | 写入 `cases/<name>/spec/`；两个 JSON 先解析校验再规范化落盘（挡非法 JSON） |
| `acceptance_gate(cdir, name)` | **非退化门禁**（见 §2.4） |
| `main()` | 按 `--archetype` 分流：spec 形态跳过 catalog 专用的 `compile_spec.derive`/`contract_gate` |

复用了：`run_model.call_deepseek`（LLM 调用）、`run_model.FILE_RE`（文件块解析）。

### 2.2 生成层（规格 → 可运行产物）

**`harness-4/tools/run_model.py`** —— 本次新增 Spec 形态生成路径。

| 函数 | 职责 |
|---|---|
| `build_context_spec(manifest, cdir, constraints)` | 拼接 `prompt.spec.md` + 全局硬约束节选 + `rules/base/*.md` + `spec/spec.md` + `spec/acceptance.json`（喂给模型"照着门禁去建"）+ manifest.required_files 清单 |
| `main()` 形态分流 | 有 `case.json` 走 catalog（原样）；否则有 `spec/manifest.json` 走 Spec 形态（`build_context_spec` → `call_deepseek` → `write_files` → `write_meta`） |

注意：Spec 形态**不支持 sample 离线模式**（交互产物无法模板化确定性生成），必须 `HARNESS_MODE=real`。

### 2.3 验收层（Spec 门禁）

**`harness-4/tools/verify_ac.py`** —— Spec 门禁，不认应用类型，只做两件事：

1. **通用安全护栏**：`banned_deps`（禁用依赖）+ `banned_code_patterns`（危险调用），与产物形态无关。
2. **逐条执行 TC/AC**：读 `cases/<case>/spec/acceptance.json`，按断言类型执行。

**断言原语闭集**（可判定的自动执行，主观的落人工）：

| 类型 | 参数 | 含义 |
|---|---|---|
| `file_exists` | `file` | 文件存在 |
| `text_contains` | `file, needle, regex?` | 文件含子串/正则 |
| `text_absent` | `file, needle, regex?` | 文件不含 |
| `http_status` | `route, expect` | 起服务后 GET，状态码匹配 |
| `http_body_contains` | `route, needle, status?` | 响应体含子串（默认要求 200） |
| `http_json_min` | `route, min` | 响应 JSON 数组长度 ≥ min |
| `unit_test` | `test?` | 跑 unittest（指定文件或 discover） |
| `manual` | — | 人工抽检，不影响退出码，报告单列 |

http 类断言会**真起一次服务**批量跑（`run_http_batch`），端口由 `HARNESS_VERIFY_PORT` 控制。
退出码：全部可自动判定项通过=0，否则=1（manual 不影响）。

### 2.4 acceptance_gate 的非退化校验规则

防止 LLM 编出「橡皮图章」式的验收标准。任何一条不满足即拦截：

- `manifest.archetype == "spec"`、`manifest.name == --name`、`title` 非空；
- `manifest.tech` 含 `framework`/`language`；`required_files` 是列表且含 `app.py`；
- `acceptance` ≥ 4 条；`acceptance.name == --name`；`ready_route` 以 `/` 开头；
- 每条 TC 的 `type` 在断言闭集内、必填键齐全；
- `file_exists`/`text_*`/`unit_test` **引用的文件必须在 `manifest.required_files` 内**（否则无法保证会被生成）；
- **可自动判定的 TC ≥ 3 条**（除 manual 外），否则判"门禁形同虚设"。

### 2.5 静态配置与提示词

| 文件 | 作用 |
|---|---|
| `harness-4/prompt.spec.md` | Spec 形态生成 prompt：Flask 薄后端、监听 `PORT`、**不是列表站**、把纯逻辑抽成可单测的 Python 模块、TC/AC 会被逐条自动检查 |
| `harness-4/constraints.json` | 全局硬约束：`banned_deps`（django/react/pytest…）、`banned_code_patterns`（eval/exec/os.system/subprocess…）、`max_inline_style`、`tech` |
| `harness-4/config.env` | `HARNESS_MODE`、`HARNESS_VERIFY_PORT`、`HARNESS_VERIFY_SOURCE=fixed\|spec\|auto` 等开关 |
| 根 `.env` | `DEEPSEEK_API_KEY`、`ECS_HOST`、`ECS_SSH_PASSWORD` 等凭据（gitignore，禁止提交） |

### 2.6 本次产出的 case 与产物

| 路径 | 内容 |
|---|---|
| `harness-4/cases/pomo_auto/spec/spec.md` | LLM 编译出的需求规格（专注/休息循环、纯逻辑模块建议、非目标） |
| `harness-4/cases/pomo_auto/spec/manifest.json` | 构建约定：archetype/name/title/tech/required_files（8 个文件） |
| `harness-4/cases/pomo_auto/spec/acceptance.json` | 6 条 TC/AC（5 条可自动判定 + 1 条 manual） |
| `output/pomo_auto/` | 生成的可运行产物（app.py / templates / static / pomo_core.py / tests…） |

> 说明：手写的 golden `cases/pomodoro/` 保留不动，`pomo_auto` 是「全自动编译」的独立样例，二者并存互证。

---

## 3. 全链路执行步骤（含实际命令）

> 所有命令在仓库根目录 `/Users/lvzhaobo/code/20260728/demo-2` 下执行。
> 输出中的真实 IP 用 `sed` 脱敏；密码只通过 `.env` 环境变量传递，从不落盘明文。

### Step 0 · 环境

```bash
# 密钥/凭据从根 .env 读取
set -a && source .env && set +a
# 关键变量：DEEPSEEK_API_KEY、ECS_HOST、ECS_SSH_PASSWORD
```

ECS 环境确认：Python **3.11.13**、Flask **3.0.3**、端口 5300 空闲。

### Step 1 · 门禁离线自证（不烧额度，验证 acceptance_gate 会"咬人"）

对 golden pomodoro（正例，应通过）与退化 acceptance（负例，应拦截）各跑一次：

```bash
python3 - <<'PY'
import os, sys, json, shutil
sys.path.insert(0, "harness-4/tools")
import spec_compiler as sc
# 正例：golden pomodoro
ok_pos = sc.acceptance_gate(os.path.join(sc.HARNESS_DIR,"cases","pomodoro"), "pomodoro")
# 负例：只有 manual + 引用未声明文件 → 应被挡
# （构造临时 case，跑完删除）
...
PY
```

结果：

```
== 正例 golden pomodoro ==
✅ [acceptance_gate] pomodoro 合规: 8 条 TC/AC(可自动判定 7 条), required_files 8 个, ready_route=/

== 负例 退化 acceptance ==
❌ [acceptance_gate] _gatecheck_neg 验收标准不合规:
    - acceptance 过少(<4),验收太弱: 2 条
    - TC1: 引用文件 not_declared.js 不在 manifest.required_files
    - 可自动判定的 TC 过少(<3),门禁形同虚设: 1 条

结果: 正例通过=True (应 True), 负例通过=False (应 False)   → EXIT=0
```

### Step 2 · 编译：「番茄钟」→ spec 三件套（真实 LLM）

```bash
set -a && source .env && set +a
python3 harness-4/tools/spec_compiler.py --name pomo_auto --archetype spec --text "番茄钟"
```

输出：

```
Spec 编译层 Phase 1 | name=pomo_auto | archetype=spec | mode=LLM
[spec_compiler] 调用 LLM 把自由文本编译为 Spec 三件套 (name=pomo_auto) ...
[spec_compiler] 已写 cases/pomo_auto/spec/(spec.md + manifest.json + acceptance.json)
✅ [acceptance_gate] pomo_auto 合规: 6 条 TC/AC(可自动判定 5 条), required_files 8 个, ready_route=/
🎉 编译成功(Spec 形态):cases/pomo_auto/spec/ 已产出 spec.md + manifest.json + acceptance.json。
```

LLM 编出的 TC/AC（要点）：TC1 首页 200；TC2 首页含"番茄钟"；TC3 `pomo_core.py` 单测；
TC4 `pomo_core.py` 存在；TC5 `app.py` 不含 `detail`（不是列表站）；TC6 manual（界面/交互人工抽检）。

### Step 3 · 生成产物（真实 LLM）

```bash
set -a && source .env && set +a
rm -rf output/pomo_auto
HARNESS_MODE=real python3 harness-4/tools/run_model.py pomo_auto output/pomo_auto
```

输出：写入 `app.py / requirements.txt / README.md / templates/index.html /
static/js/pomo.js / static/css/style.css / pomo_core.py / tests/test_pomo.py`（+ 附带 `tests/test_app.py`），
`生成完成(real, spec)`。

### Step 4 · 本地 Spec 门禁 verify_ac

```bash
HARNESS_VERIFY_PORT=5071 python3 harness-4/tools/verify_ac.py pomo_auto output/pomo_auto
```

输出：

```
[OK] 护栏:无禁用依赖
[OK] 护栏:无危险调用
[OK] TC3:pomo_core.py的纯逻辑单元测试通过
[OK] TC4:核心逻辑模块pomo_core.py存在
[OK] TC5:app.py中不包含'detail'字样，确保不是列表站
[MANUAL] TC6:需人工抽检…
[OK] 运行时:服务可启动
[OK] TC1:首页返回200状态码 - status=200 期望 200
[OK] TC2:首页页面包含'番茄钟'文案 - status=200 含'番茄钟'=True

=== Spec 验收 通过: 自动 8/8，1 项待人工 ===
```

### Step 5 · 部署到 ECS，端口 5300

因本地无 `sshpass`、ECS 无 `rsync`，采用 **OpenSSH `SSH_ASKPASS` 免交互 + tar-over-ssh**：

```bash
# 5.1 一次性 askpass 助手（用完即删，不落盘明文密码）
#     内容仅一行：echo "$ECS_SSH_PASSWORD"（读环境变量，非硬编码）
printf '#!/bin/sh\necho "$ECS_SSH_PASSWORD"\n' > output/.askpass.sh
chmod +x output/.askpass.sh

set -a && source .env && set +a
export ECS_SSH_PASSWORD
export SSH_ASKPASS="$PWD/output/.askpass.sh" SSH_ASKPASS_REQUIRE=force

# 5.2 打包上传（tar 打流 → ssh → 远端解包），排除本地垃圾
COPYFILE_DISABLE=1 tar czf - -C output/pomo_auto \
  --exclude reports --exclude _verify.log --exclude __pycache__ \
  --exclude app.log --exclude app.pid --exclude _run_meta.json . \
| ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 22 root@"$ECS_HOST" \
  'rm -rf /root/apps/pomo_auto && mkdir -p /root/apps/pomo_auto && tar xzf - -C /root/apps/pomo_auto'

# 5.3 拉起服务（PORT=5300，setsid nohup 常驻），并本机自测
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 22 root@"$ECS_HOST" \
  'cd /root/apps/pomo_auto && pip3 install -q -r requirements.txt;
   [ -f app.pid ] && kill "$(cat app.pid)" 2>/dev/null; fuser -k 5300/tcp 2>/dev/null; sleep 1;
   PORT=5300 setsid nohup python3 app.py > app.log 2>&1 & echo $! > app.pid; sleep 3;
   curl -s -o /dev/null -w "HTTP=%{http_code}\n" http://127.0.0.1:5300/'

# 5.4 用完删除凭据助手
rm -f output/.askpass.sh
```

结果：`PID=382192`、监听 `0.0.0.0:5300`、ECS 本机 `HTTP=200` 且页面含"番茄钟"。

### Step 6 · 公网验证

```bash
set -a && source .env && set +a
curl -s -m 12 -o /tmp/ext.html -w "EXTERNAL_HTTP=%{http_code}\n" "http://$ECS_HOST:5300/"
grep -o "番茄钟" /tmp/ext.html
```

结果：`EXTERNAL_HTTP=200`，页面含"番茄钟"。安全组已放行 5300，浏览器可直接访问。

---

## 4. 结果汇总

| 环节 | 命令入口 | 结果 |
|---|---|---|
| 门禁自证（正/负例） | `spec_compiler.acceptance_gate` | 正例过、负例拦，EXIT=0 ✅ |
| 编译「番茄钟」 | `spec_compiler.py --archetype spec --text` | 6 TC/AC（5 自动），过 gate ✅ |
| 生成产物 | `run_model.py`（Spec 形态） | 8+1 文件 ✅ |
| 本地门禁 | `verify_ac.py` | 自动 8/8 + 1 人工 ✅ |
| 部署 ECS:5300 | tar-over-ssh + `PORT=5300 nohup` | PID 382192，本机 200 ✅ |
| 公网访问 | `curl http://<ECS>:5300/` | 200，含"番茄钟" ✅ |

**LLM 调用次数：2 次**（Step2 编译 + Step3 生成），其余均为确定性代码/门禁，不烧额度。

---

## 5. 一键复现清单

```bash
cd /Users/lvzhaobo/code/20260728/demo-2
set -a && source .env && set +a

# 1) 编译 + 门禁
python3 harness-4/tools/spec_compiler.py --name pomo_auto --archetype spec --text "番茄钟"
# 2) 生成
rm -rf output/pomo_auto
HARNESS_MODE=real python3 harness-4/tools/run_model.py pomo_auto output/pomo_auto
# 3) 本地验收
HARNESS_VERIFY_PORT=5071 python3 harness-4/tools/verify_ac.py pomo_auto output/pomo_auto
# 4) 部署 + 公网验证：见 §3 Step 5 / Step 6

# 离线自证（不烧额度，验证链路本身）：
python3 harness-4/tools/spec_compiler.py --name pomodoro --archetype spec --mock
```

---

## 6. 踩过的坑与注意事项

| 现象 | 原因 | 处理 |
|---|---|---|
| `zsh: command not found: python` | macOS 无 `python`，只有 `python3` | 一律用 `python3` |
| ssh 报 `keyword stricthostkeychecking extra arguments` | zsh **不对未加引号的变量分词**（`$SSHOPT` 当成一个词） | ssh 选项写字面量，别塞变量 |
| 本地/远端 `rsync: command not found` | ECS 未装 rsync | 改用 `tar czf - … \| ssh 'tar xzf -'` |
| 无 `sshpass` | macOS 默认不带 | 用 OpenSSH `SSH_ASKPASS` + `SSH_ASKPASS_REQUIRE=force`（免装） |
| `Could not stat ~/.ssh` / xattr 警告 | 沙箱限制 + macOS 扩展属性 | 加 `-o UserKnownHostsFile=/dev/null`；tar 警告无害（文件已正常归档） |
| 安全 | 密码/Token 泄漏风险 | 凭据只走 `.env` 环境变量；askpass 助手用完即删；日志输出脱敏 IP |

> ⚠️ 遗留安全项：根 `.git/config` 中曾发现 GitHub Token 泄漏（`ghp_…`），推送前请先吊销重发。

---

## 7. 结论

**「番茄钟」三个字 → 线上可访问的交互计时器**，全程零人工改代码、仅 2 次 LLM 调用跑通。
证明 Spec 形态链路成立：门禁只认 Spec 声明的 TC/AC，不穷举应用类型；
验收标准由编译阶段冻结、生成器只负责建到能过（裁判≠运动员）；catalog 原路径零回归。
