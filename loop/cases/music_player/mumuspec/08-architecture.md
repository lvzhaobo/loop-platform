# 架构选型与设计

## 1. 技术栈

- **后端**：Python 3.10+，Flask 框架，提供 RESTful API
- **前端**：原生 HTML5 + CSS3 + Vanilla JavaScript，单页应用（SPA）风格
- **数据存储**：JSON 文件（播放列表 `playlist.json`、设置 `settings.json`）
- **音频处理**：利用浏览器原生 `<audio>` 元素控制，后端仅管理状态与文件信息
- **开发/调试**：Flask 内置服务器（开发），生产部署可选用 Gunicorn
- **测试**：unittest/pytest 用于 API 测试，前端手动测试 + 性能监测

## 2. 系统组件图

```
[用户浏览器]
      |
      | HTTP
      v
[Flask 应用 (app.py)]   ←→  [JSON 文件存储]
   ├── api/playback      ←→  [音频状态管理]
   ├── api/library       ←→  [文件扫描与列表管理]
   └── api/settings      ←→  [设置读写]
```

- **Flask 路由层**：接受请求、参数校验、调用业务逻辑，返回 JSON 响应。
- **播放状态模块**：维护当前播放状态（当前曲目、播放/暂停、位置、音量等），不实际解码音频，仅作为前端音频控制的状态镜像。
- **文件管理模块**：扫描指定目录，过滤支持格式（`.mp3`, `.wav`, `.flac`, `.ogg`, `.aac`），提取元数据（若可用），生成 Track 对象并持久化到 `playlist.json`。
- **配置模块**：读取配置文件（如音乐根目录、支持格式），提供全局设置。

## 3. 目录结构

```
music-player/
├── app.py                  # Flask 入口，路由注册
├── config.yaml             # 配置文件（音乐目录、支持格式等）
├── data/
│   ├── playlist.json       # 播放列表持久化
│   └── settings.json       # 应用设置（主题等）
├── modules/
│   ├── playback.py         # 播放状态管理（内存中状态+一些字段持久化如音量）
│   ├── library.py          # 音乐库扫描与播放列表管理
│   └── settings.py         # 设置读取与保存
├── static/
│   ├── index.html          # 前端主页面
│   ├── css/
│   │   └── style.css       # 深色主题样式
│   └── js/
│       ├── player.js       # 音频控制，API调用
│       ├── playlist.js     # 播放列表渲染与交互
│       └── settings.js     # 主题应用等
└── tests/
    ├── test_playback.py
    ├── test_library.py
    └── ...
```

## 4. 关键设计决策

- **后端不直接处理音频流**：Flask 仅作为状态与资源管理服务器，实际音频播放由前端 `<audio>` 元素根据后端提供的文件路径（本地 URL）完成。这简化了流媒体处理，适合本地桌面环境。
- **JSON 文件存储**：适合单用户、本地应用场景，无需安装数据库。读写加锁（使用文件锁或线程锁）防止并发损坏。
- **无用户认证**：本应用为本地单用户音乐播放器，无需认证体系；安全性重心在文件访问沙箱。
- **深色主题固定**：需求只要求深色主题，故内置固定 CSS 变量，无需动态主题切换接口（仍可通过设置 API 保存状态以便未来扩展）。