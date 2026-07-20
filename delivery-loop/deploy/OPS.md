# loop-platform 运维手册

> 一键交付平台的日常运维速查。部署形态:阿里云 ECS + systemd 常驻 webhook。
> 生产地址:`47.76.211.100` · 代码目录:`/root/loop-platform` · 服务名:`loop-platform`

---

## 1. 这套系统是什么

点一个按钮,飞书需求自动变成线上应用。整条链路:

```
点按钮 (POST /trigger)
  → 飞书 Wiki 拉需求 (feishu_docs.json 里的文档)
  → LLM 编译成规格契约 (case)
  → 真实 LLM 生成代码 + 20 项验收 (跑两次校验产物一致性)
  → 推 loop-sample 仓 (sampleN @ main)
  → GitHub Actions「Deploy samples to ECS」自动部署
  → 线上 http://47.76.211.100:100N 上线
```

- **配置态**:`harness-4/studio`(Flask :5100)——编辑约束/用例、一致性预检,页面上也有「🚀 开始交付」按钮。
- **运行态**:`delivery-loop/trigger/webhook.py`(:8787)——常驻按钮服务,systemd 托管的就是它。

---

## 2. 服务运维(systemd)

服务单元:`/etc/systemd/system/loop-platform.service`,常驻的是 webhook(:8787,默认绑 `127.0.0.1`)。

```bash
# 状态 / 实时日志
systemctl status loop-platform
journalctl -u loop-platform -f

# 起 / 停 / 重启
systemctl start   loop-platform
systemctl stop    loop-platform
systemctl restart loop-platform

# 反复重启失败时,先清失败计数再重启
systemctl reset-failed loop-platform && systemctl restart loop-platform
```

服务在 `ExecStart` 里先 `source .env + config.env` 再启动 webhook,所以触发出来的每一批都拿得到
DEEPSEEK / FEISHU / GITHUB 凭证。开关(feishu/real/push 等)写在 unit 的 `Environment=` 段,密钥只从 `.env` 读。

---

## 3. webhook 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/` | 按钮页(HTML) |
| GET | `/health` | 健康检查,返回 `{"ok": true}` |
| POST | `/trigger` | 跑一批(同步阻塞到整条流水线结束) |

- 并发:进程内 `threading.Lock`,同一时刻只允许一批在跑;正在跑时再触发 → **HTTP 409 busy**(不排队)。
- 鉴权:未设 `HARNESS_TRIGGER_TOKEN` 时不校验(仅限本机/隧道);对外暴露**必须**设 token,请求头带 `X-Trigger-Token`。

```bash
# 本机自测(在 ECS 上)
curl -s http://127.0.0.1:8787/health
curl -sS -X POST http://127.0.0.1:8787/trigger -w "\n[HTTP %{http_code}]\n"
```

---

## 4. 三种触发方式

**A. 按钮页(推荐,零公网暴露)** —— 在你自己电脑上开隧道:
```bash
ssh -L 8787:127.0.0.1:8787 root@47.76.211.100
# 浏览器打开 http://127.0.0.1:8787/ ,点「跑一批」
```

**B. 一条命令(SSH 到 ECS 直接跑)**:
```bash
cd /root/loop-platform && bash delivery-loop/run_backlog.sh
```

**C. studio 配置平台 + 🚀 按钮**:
```bash
ssh -L 5100:127.0.0.1:5100 root@47.76.211.100
# ECS 上:
cd /root/loop-platform && set -a && . ./.env && . delivery-loop/config.env && set +a \
  && STUDIO_PORT=5100 ./.venv/bin/python harness-4/studio/server.py
# 浏览器打开 http://127.0.0.1:5100
```

---

## 5. 加 / 改需求

需求清单:`delivery-loop/backlog/feishu_docs.json`。追加一个飞书文档条目即可:

```json
{
  "docs": [
    { "id": "FS-001", "title": "在线学习平台(飞书Wiki Spec)", "wiki_token": "Ft7mwzra4iI57IkfYR7cRAvwnwe", "priority": 1 },
    { "id": "FS-002", "title": "新需求标题", "wiki_token": "<飞书Wiki token>", "priority": 2 }
  ]
}
```

- **去重**:`delivery-loop/backlog/feishu_state.json` 记录已处理的文档,`status=done` 的**不会重复跑**。
- **重跑某文档**:把该条目从 state 里删掉;或整体重来 → `echo '{}' > delivery-loop/backlog/feishu_state.json`。
- 每成功一批,`sample_n` 自增(sample1→2→3…),对应线上端口 `1000+N`。

---

## 6. 更新代码

私有仓 `loop-platform` 有新提交后,在 ECS 上幂等重跑安装脚本(已有 `.git` 走 `git fetch/reset`,不会重复 clone):

```bash
cd /root/loop-platform && bash delivery-loop/deploy/setup_ecs.sh --with-service
```

脚本会:更新代码 → 重建 venv/依赖 → 校验 `.env` 必需密钥 → 自检关键文件 → 重装并重启 systemd 服务。

---

## 7. 密钥与安全

- `.env`(600 权限)在 `/root/loop-platform/.env`,含 `DEEPSEEK_API_KEY` / `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `GITHUB_TOKEN`。
- **`.env` 永不进仓**;`build_repos.sh` / `.gitignore` 已排除,推送前有密钥复检。
- webhook 默认绑 `127.0.0.1`,只能本机或 SSH 隧道访问。要对外暴露:改 `HARNESS_TRIGGER_HOST=0.0.0.0` + 设 `HARNESS_TRIGGER_TOKEN` + 安全组只放行你的 IP。
- GitHub token:classic PAT(`ghp_` 开头),需 `repo` scope(私有仓读写 + 建仓)。

---

## 8. 常见故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 服务反复重启 `Address already in use` | 8787 被占。查 `ss -ltnp \| grep 8787`,清占用 `fuser -k 8787/tcp`,再 `systemctl restart loop-platform`。常见元凶:遗留的 `ssh -L 8787:...` 隧道。 |
| 触发返回 **409 busy** | 已有一批在跑,不排队。等它跑完(看 `journalctl -u loop-platform -f`)。 |
| 触发无任务 / 空跑 | `feishu_docs.json` 缺失或为空;或文档都已 `done`。检查清单与 state。 |
| 生成/验收失败 exit≠0 | 看 `output/<时间戳>-<case>/` 目录与日志;真实 LLM 有 `MAX_RETRY`(默认 5)次自动重试。 |
| 推送失败 403 | GITHUB_TOKEN 无权:确认是 classic PAT 且勾了 `repo`;注意变量名是全大写 `GITHUB_TOKEN`。 |
| 线上端口打不开 | 确认 Actions「Deploy samples to ECS」为 success;确认安全组放行 `100N` 端口。 |

---

## 9. 关键路径速查

| 用途 | 路径 |
|---|---|
| 代码根 | `/root/loop-platform` |
| 密钥 | `/root/loop-platform/.env` |
| 需求清单 | `delivery-loop/backlog/feishu_docs.json` |
| 去重状态 | `delivery-loop/backlog/feishu_state.json` |
| 一批入口 | `delivery-loop/run_backlog.sh` |
| webhook | `delivery-loop/trigger/webhook.py` |
| 部署脚本 | `delivery-loop/deploy/setup_ecs.sh` |
| systemd 模板 | `delivery-loop/deploy/loop-platform.service` |
| 产物输出 | `output/<时间戳>-<case>/` |
| 配置默认值 | `delivery-loop/config.env`(`${VAR:-default}`,systemd/env 覆盖优先) |
