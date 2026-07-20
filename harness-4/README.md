# Harness-4:契约驱动的确定性代码生成与验证框架

Harness-4 是在 harness-3(单一事实源驱动)之上的成熟化版本。核心命题不变:
**用确定性的脚手架,约束非确定性的大模型输出,并用可执行的验证闭环兜底。**

相较 harness-3,本版本:
1. **修复场景污染 bug**:`prompt.md` 与全部 `rules/` 彻底场景中立,多用例不再相互干扰;
2. **量化验证**:验证从"字段存在 + 类型"深化到 `field_rules`(长度 / 数值范围 / id 连续性);
3. **就绪轮询**:运行时验证轮询服务就绪,替代固定 `sleep`,显著降低 CI flaky;
4. **安全一等公民**:扫描产物源码是否出现 `banned_code_patterns` 危险调用;
5. **离线样例模式**:`HARNESS_MODE=sample` 无需 API 即可跑通整条流水线(冒烟 / CI / 确定性基线);
6. **run 隔离报告**:每次验收产出 `reports/verify-report.json` 与 `summary.md`,逐项可追溯;
7. **派生 Schema**:从事实源 `case.json` 派生 JSON Schema(派生物,**不构成第二事实源**,永不漂移)。

---

## 一分钟上手

```bash
# 1) 准备环境(创建 .venv 并安装 Flask)
bash harness-4/setup.sh
source .venv/bin/activate

# 2) 离线自检(不烧额度):自洽性 → 派生 Schema → 全用例离线闭环
HARNESS_MODE=sample bash harness-4/gate.sh

# 3) 真实生成(需密钥):在仓库根 .env 写 DEEPSEEK_API_KEY=sk-xxx
source .env
bash harness-4/gate.sh
```

产物在 `output/<时间戳>-<用例>/`,验收报告在其 `reports/` 子目录。

---

## 架构:三层绑定,单一事实源

```
             人读规格                     机器事实源                    执行器
cases/<c>/spec/*.md  ←── check_consistency.py ──→  cases/<c>/case.json  ──┬──→ tools/run_model.py (生成)
                                                   + constraints.json     └──→ tools/verify.py    (验证)
```

- **唯一事实源**:`constraints.json`(全局骨架 / 技术栈 / 禁用项)+ `cases/<c>/case.json`(用例专属:字段、量化约束、路由、标记、配色)。生成与验证同吃这一份,天然不漂移。
- **自洽门禁** `check_consistency.py`:强制 `case.json` 每条事实都能在 `spec/*.md` 找到落点,防止"改了事实源忘了改规格"。
- **验证器** `verify.py`:真起 Flask、真渲染断言、真跑 unittest、真打 404,并把结果落成报告。

---

## 目录结构

```
harness-4/
├── VERSION                     # 4.0.0
├── config.env                  # 确定性/用例集/模式开关
├── setup.sh                    # 环境准备
├── prompt.md                   # 场景中立的系统提示(无领域硬编码)
├── constraints.json            # 全局硬事实(技术栈/骨架/禁用依赖/危险模式)
├── rules/
│   ├── base/                   # 跨任务基座:安全/错误与日志/测试/文档
│   └── task/                   # 任务约束:技术栈/结构/规范(均场景中立)
├── cases/
│   ├── ecommerce/{case.json, spec/*}
│   └── blog/{case.json, spec/*}
├── schemas/                    # build_schema.py 派生的数据 Schema(生成物)
├── tools/
│   ├── run_model.py            # 生成器(real=DeepSeek / sample=离线参考)
│   ├── sample_generator.py     # 离线参考生成器(确定性、必过 verify)
│   ├── verify.py               # 深化验证 + run 隔离报告
│   ├── check_consistency.py    # 自洽性门禁
│   └── build_schema.py         # 从事实源派生 JSON Schema
├── generate.sh                 # 多用例闭环 + 反馈重试 + 确定性复跑
├── gate.sh                     # CI 门禁:自洽 → 派生 → 全用例闭环
├── ci/github-actions.yml       # CI 模板
└── checklist.md                # 验收清单
```

---

## 新增一个业务场景(只加数据,不改代码)

1. 建 `cases/<新场景>/`,写 `case.json`(唯一事实源)与 `spec/{data-model,api-contract,ui-spec}.md`;
2. 把 `<新场景>` 加进 `constraints.json.cases`;
3. `HARNESS_MODE=sample bash harness-4/gate.sh` 先离线自检自洽性与流水线;
4. `bash harness-4/gate.sh` 真实生成并验收。

无需改动任何 `tools/*.py`——因为标尺全部来自 `case.json`。

---

## 确定性说明

- 生成侧:`temperature=0` + `seed=42`(可在 `config.env` 调整),并在通过后**复跑比对产物哈希**(identical / drift 均记录到 `output/runs.jsonl`)。
- LLM 的 `seed` 非严格可复现,因此确定性由"验证层"兜底:漂移也必须仍然通过全部验收。
- `HARNESS_MODE=sample` 下产物由确定性参考生成器产出,复跑必然字节一致,可作为流水线自检基线。

---

## 适用边界(诚实声明)

Harness-4 泛化了"业务内容",锁定了"技术栈 + 结构":
- ✅ 适合:任意"列表 + 详情、读为主、Flask + Jinja + JSON 文件"的场景(电商 / 博客 / 新闻 / 菜谱 / 图库…);
- ⚠️ 不适合:更换技术栈(React/FastAPI/Django)、非列表-详情形态、含写操作/持久化、重业务逻辑的场景。

要覆盖更广场景,需把抽象边界从"内容"进一步上移到"技术栈 + 结构 + 验证策略"——那是后续演进方向。
