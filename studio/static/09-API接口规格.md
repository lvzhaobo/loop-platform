# API 接口规格

## GET /
返回播放器页面（HTML）

## GET /api/status
返回当前播放状态（JSON）

```json
{"playing": false, "current_track": 0, "volume": 80, "position": 0}
```

## GET /api/settings
返回播放器设置

## POST /api/play
切换播放/暂停

## POST /api/next / POST /api/prev
切换曲目

## POST /api/volume
设置音量
