# 数据模型

## 1. Track（曲目）

用于播放列表和扫描结果。

| 字段名 | 数据类型 | 约束 | 描述 |
|--------|----------|------|------|
| id | string | 唯一，自动生成（UUID） | 曲目唯一标识 |
| title | string | 非空，长度 ≤ 200 | 曲目标题，若无元数据则使用文件名 |
| artist | string | 可空，长度 ≤ 200 | 艺术家，若无元数据则为“Unknown Artist” |
| duration | number (float) | ≥ 0，单位秒 | 总时长 |
| format | string | 枚举：`mp3`, `wav`, `flac`, `ogg`, `aac` | 音频格式 |
| filePath | string | 绝对或相对路径，非空 | 文件在磁盘的位置 |

**示例**：
```json
{
  "id": "a1b2c3d4-...",
  "title": "Song Name",
  "artist": "Artist Name",
  "duration": 245.3,
  "format": "mp3",
  "filePath": "/music/album/song.mp3"
}
```

## 2. PlaybackState（播放状态，内存 + 部分持久化到 settings）

| 字段名 | 数据类型 | 约束 | 描述 |
|--------|----------|------|------|
| currentTrackId | string / null | 曲目 ID 或 null | 当前播放曲目的 ID |
| status | string | 枚举：`playing`, `paused`, `stopped` | 播放状态 |
| currentTime | number (float) | ≥ 0，单位秒 | 当前播放位置 |
| duration | number (float) | ≥ 0 | 当前曲目总时长 |
| volume | integer | 0-100 | 当前音量 |
| muted | boolean | true/false | 是否静音 |

这些状态在内存中维护，通过 API 返回。音量及静音状态可持久化到 `settings.json` 以便重启恢复。

## 3. Settings（设置）

存储于 `data/settings.json`。

| 字段名 | 数据类型 | 约束 | 描述 |
|--------|----------|------|------|
| theme | string | 固定值 `"dark"` | 界面主题 |
| lastVolume | integer | 0-100 | 上次使用的音量，用于恢复 |
| lastMuted | boolean | true/false | 上次静音状态 |

## 4. Playlist（播放列表）

存储于 `data/playlist.json`，表现为 Track 数组。

```json
{
  "tracks": [ ... ]
}
```

字段 `tracks` 是 Track 对象的列表。后端提供完整列表的读取与增删接口。

## 5. API 响应通用格式

成功响应：
```json
{
  "status": "success",
  "data": { ... }
}
```

失败响应：
```json
{
  "status": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "可读消息"
  }
}
```