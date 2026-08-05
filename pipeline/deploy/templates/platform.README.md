# loop-platform

> **自主交付流水线平台** —— 一句话需求进，可上线应用出。
> 飞书/自由文本需求 → LLM 生成代码 → 契约验收 → 推 GitHub → 部署 ECS，全链路无人值守。

本仓是「系统本身」。生成的应用产物在 `loop-sample`，需求规格在 `loop-specs`。

## 目录结构

```
loop/engine/        契约驱动的确定性代码生成 + 验证引擎（黑盒，命令行调用）
  ├─ cases/       各领域用例（spec 契约 + 样例数据 + case.json）
  ├─ tools/       compile_spec / verify / build_schema / run_model …
  ├─ studio/      配置界面原型
  └─ generate.sh  引擎入口（子进程调用）
loop/pipeline/    编排层（Loop Engine）
  ├─ orchestrator.py  主循环：取需求 → 调引擎 → 发布 → 部署 → 回写
  ├─ publisher.py     发布到 GitHub（子目录 + B 方案自动递增 sampleN）
  ├─ deployer.py      拉取式部署到 ECS（pty 驱动 ssh，零依赖）
  ├─ adapters/        需求来源（local / feishu）
  ├─ ci/              GitHub Actions 通用多样例部署 workflow
  ├─ docs/            全流程 / 方案 / 执行手册
  └─ config.env       运行配置（非机密，逐段开关）
.env.example      密钥模板（复制为 .env 后填值；.env 永不提交）
```

## 快速开始

```bash
cp .env.example .env          # 填入 DeepSeek / 飞书 / GitHub / ECS 密钥
python3 -m venv .venv && source .venv/bin/activate
pip install -r loop/engine/requirements.txt 2>/dev/null || true

# 离线跑通闭环（零密钥，sample 模式）
HARNESS_MODE=sample HARNESS_CASES=education bash loop/engine/generate.py

# 端到端交付（real 模式 + B 方案自动递增 + 部署），详见 docs/自主交付流水线-全流程与改进.md
HARNESS_MAX_TASKS=1 HARNESS_AUTOCOMMIT=1 bash loop/pipeline/run_backlog.sh
```

## 设计原则

- **引擎黑盒**：`loop/pipeline` 只通过命令行 + 退出码 + `output/runs.jsonl` 调引擎，不 import 其内部。
- **确定性验收**：每个产物过 20 项硬校验才发布，失败反馈重试。
- **密钥安全**：所有密钥仅存本机 `.env` / CI Secrets / 服务器环境变量，**绝不进仓**。

## 文档

- [自主交付流水线-全流程与改进](loop/pipeline/docs/自主交付流水线-全流程与改进.md)
- [Spec 编译层与动态模板方案](loop/pipeline/docs/Spec编译层与动态模板方案.md)
- [GitHub 多仓发布方案](loop/pipeline/docs/GitHub多仓发布方案.md)
