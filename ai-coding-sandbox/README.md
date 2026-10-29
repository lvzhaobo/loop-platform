# ai-coding-sandbox · MumuLoop 注入套件

一条命令复现 AI Coding 治理闭环：生成 → 确定性检查 → 判定账本 → 可回放 trace。

- 后端可替换：DeepSeek / Bedrock 实现同一 `MakerClient`，切换只改 `--maker`。
- 判定确定性：`platform/checker/check.py` 六条规则（ERR001/ERR002/SEC001/SEC002/SEC003/CFG001）。
- 口径一致：逐轮 JSONL + diff 账本（fixed/regressed/still_red）。

## 快速开始

```bash
python3 -m venv .venv && .venv/bin/pip install --upgrade pip
.venv/bin/pip install requests          # Bedrock 路径另需 boto3

export DEEPSEEK_API_KEY=<你的 key>

python3 platform/cli/sandbox_run.py \
  --suite platform/suites/injection-suite.json \
  --maker deepseek --max-rounds 3

python3 platform/cli/mumuloop.py stats
```

切换 Bedrock：`--maker bedrock --region us-west-2 --model <模型ID>`（需 AWS 凭据）。
实时画布：`python3 platform/server/app.py` 后打开 http://127.0.0.1:8787（浅色主题）。
