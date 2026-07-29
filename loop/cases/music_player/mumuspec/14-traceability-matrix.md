# 追溯矩阵：需求 → 用户故事 → API → 测试用例

| 需求ID | 需求描述 | 用户故事 | API 端点 | 测试用例 (TC) |
|--------|----------|----------|----------|---------------|
| REQ-01 | 音乐播放控制 | US-01 基础播放控制 | POST /api/playback/play<br>POST /api/playback/pause<br>POST /api/playback/next<br>POST /api/playback/previous<br>GET /api/playback/state | TC-001, TC-002, TC-003, TC-004, TC-005, TC-006, TC-007, TC-008 |
| REQ-02 | 进度条跳转 | US-02 进度条拖拽与跳转 | GET /api/playback/state<br>POST /api/playback/seek | TC-009, TC-010, TC-011, TC-012, TC-013 |
| REQ-03 | 音量调节 | US-03 音量调节与静音 | GET /api/playback/state<br>POST /api/playback/volume<br>POST /api/playback/toggleMute | TC-014, TC-015, TC-016, TC-017, TC-018 |
| REQ-04 | 播放列表与文件管理 | US-04 播放列表与文件管理 | GET /api/library/playlist<br>POST /api/library/scan<br>POST /api/library/playlist/add<br>POST /api/playback/play (含 trackId) | TC-019, TC-020, TC-021, TC-022, TC-023, TC-024 |
| REQ-05 | 深色主题与界面适配 | US-05 深色主题与界面适配 | GET /api/settings<br>POST /api/settings/theme | TC-025, TC-026, TC-027, TC-028 |
| REQ-06 | 错误与边界处理 | US-06 错误与边界状态处理 | POST /api/playback/play<br>POST /api/library/scan<br>GET /api/playback/state (稳定性)<br>GET /api/health | TC-029, TC-030, TC-031, TC-032, TC-033 |

**说明**：每个需求（REQ）映射到一个用户故事（US），再映射到该用户故事涉及的 REST API 端点，最终对应验收标准衍生出的测试用例。部分测试用例涉及多个 API（如播放状态获取），已完整列出。