# Music Player - 项目契约概述

**一句话概述**：一个本地单用户音乐播放器，通过 Flask REST API 提供播放控制（播放/暂停/上下曲）、进度跳转、音量调节、播放列表管理与深色主题界面，所有操作均基于安全、清晰的 API 契约实现。

**核心交互**：
- 用户通过 Web UI（或 Electron 前端）触发播放控制 → 前端调用 `/api/playback/play`、`/api/playback/pause` 等端点。
- 进度与音量调节：滑块/点击 → `POST /api/playback/seek`、`POST /api/playback/volume`、`POST /api/playback/toggleMute`，后端调整音频引擎并返回实时状态。
- 音乐库管理：应用启动扫描默认目录（`POST /api/library/scan`）或用户拖放添加文件（`POST /api/library/playlist/add`），播放列表持久化为 JSON。
- 健康检查：`GET /api/health` 用于监控应用运行状态。
- 异常处理：音频设备缺失返回 503，权限不足返回 403，损坏文件自动跳过并提示。

**结构建议**（推荐项目文件组织）：
```
music_player/
├── app.py                # Flask 主入口，注册蓝图
├── config.yaml           # 音乐根目录、支持格式等配置
├── requirements.txt      # Python 依赖（Flask、PyYAML 等）
├── data/
│   ├── settings.json     # 音量、主题等持久化设置
│   └── playlist.json     # 当前播放列表（Track 数组）
├── api/                  # 可选：拆分蓝图路由
│   ├── __init__.py
│   ├── playback.py
│   ├── library.py
│   └── settings.py
├── static/               # 前端静态资源
│   ├── index.html
│   ├── style.css
│   └── script.js
└── README.md
```
后端核心逻辑应集中于 `app.py`（或模块化为 `api/`），音频处理使用 `pygame` 或类似库，严格遵循 API 契约；前端通过 Fetch 调用 API 并渲染界面。

**非目标**：
- 不实现用户认证、多用户管理或远程访问。
- 不提供流媒体广播或网络播放功能。
- 不支持在线音乐商店或元数据自动下载。
- 不负责处理超过 5000 个文件的音乐库（性能目标上限）。
- 不提供播放列表的复杂规则（如智能播放列表）或均衡器。