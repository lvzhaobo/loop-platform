# delivery-loop / trigger —— 自动触发器(把批处理升级为自驱动 Loop)

`delivery-loop` 本身已经能"取任务 → 调 harness-4 生成+验证 → 回写 →(可选)发布",
但它仍需**人手动**跑一次 `run_backlog.sh`。本目录补上 Loop Engineering 里唯一真正新增的
能力 —— **Self-Triggering(系统自触发)**:让系统自己决定何时启动,无人值守持续运转。

> 补上 trigger 后,delivery-loop 才从"人工启动的工具"正式跨入"自主运行的 Agent"。

## 纯外挂,零侵入

trigger 只做一件事:**子进程调用 `run_backlog.sh`**。

```
                        ┌──────────────────────────────────────────┐
  ⏰ cron / while       │           trigger(本目录)                 │
  📩 webhook 事件  ───▶ │  poll.sh(轮询) / webhook.py(事件)        │──┐
                        └──────────────────────────────────────────┘  │ 纯子进程调用
                                                                       ▼
                              run_backlog.sh → orchestrator.py → harness-4 引擎
                              （以下全部一行未改：需求怎么取、引擎怎么跑、状态怎么回写）
```

- 不 import `orchestrator.py`,不碰 `harness-4/5` 的任何代码或产物。
- 删掉整个 `trigger/` 目录,`delivery-loop` 回到原样,零副作用。

## 两种触发方式

### 1) 轮询式 `poll.sh`(Polling-based:系统主动扫描)

适合"周期性扫需求池"。两种用法:

```bash
# A. 守护进程模式(前台长驻,自己 while 循环):默认每 300s 一批,Ctrl-C 停止
bash delivery-loop/trigger/poll.sh

# 改扫描间隔(比如 60s)
HARNESS_TRIGGER_INTERVAL=60 bash delivery-loop/trigger/poll.sh

# B. 单次模式(交给系统 crontab 定时拉起)
bash delivery-loop/trigger/poll.sh --once
```

crontab 示例(每 5 分钟一次):

```cron
*/5 * * * * cd /绝对路径/demo-2 && bash delivery-loop/trigger/poll.sh --once >> /tmp/dl-poll.log 2>&1
```

### 2) 事件式 `webhook.py`(Event-driven:外部事件推送)

适合"有新 issue/PR/CI 完成就触发"。零依赖(仅 stdlib):

```bash
# 启动(默认绑 127.0.0.1:8787,sample 离线模式,零密钥)
python delivery-loop/trigger/webhook.py

# 另开终端手动踢一脚
curl -X POST http://127.0.0.1:8787/trigger
curl      http://127.0.0.1:8787/health     # 健康检查
```

对接 GitHub/GitLab/飞书:把它们的 webhook 指向 `POST /trigger` 即可(生产环境请套反向代理)。

## 并发保护

两个触发器都带**并发锁**:上一批还没跑完时,新的触发会被**跳过**(poll 打印跳过日志、
webhook 返回 `409 busy`),而**不是排队堆积**——避免同一 case 被并行生成、产物互相踩踏。

- `poll.sh`:基于 `mkdir` 的原子锁 `delivery-loop/.trigger.lock`(异常退出用 trap 自动清理)。
- `webhook.py`:进程内 `threading.Lock`。

## 配置(见 `../config.env`,均可被环境变量覆盖)

| 变量 | 默认 | 说明 |
|---|---|---|
| `HARNESS_TRIGGER_INTERVAL` | `300` | poll 守护进程两次扫描的间隔秒数 |
| `HARNESS_TRIGGER_HOST` | `127.0.0.1` | webhook 监听地址(默认只绑本机) |
| `HARNESS_TRIGGER_PORT` | `8787` | webhook 监听端口 |
| `HARNESS_TRIGGER_TOKEN` | (空) | webhook 共享密钥;设了则请求头需带 `X-Trigger-Token`。真实值写仓库根 `.env` |

> 其余开关(`HARNESS_MODE` / `HARNESS_BACKLOG_SOURCE` / `HARNESS_AUTOCOMMIT` …)
> 由 `run_backlog.sh` 自行读取,触发器原样透传当前环境,不重复定义。

## 端到端自测(零密钥)

```bash
# 1) 往需求池丢一条 pending 任务(结构化,直接给 case)
echo '{"id":"REQ-T1","title":"电商站","case":"ecommerce","priority":1,"status":"pending"}' \
  >> delivery-loop/backlog/backlog.jsonl

# 2) 起 webhook,另一终端触发一批;或直接跑一次 poll --once
python delivery-loop/trigger/webhook.py &
curl -X POST http://127.0.0.1:8787/trigger
# 或
bash delivery-loop/trigger/poll.sh --once
```

跑完后任务状态在 `backlog.jsonl` 由 `pending → done/failed`,产物在仓库根 `output/`。
