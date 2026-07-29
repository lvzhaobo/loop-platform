# 数据模型: test_mumu

无持久化数据。计时状态由前端 JS 管理。

- `seconds`: int 剩余秒数
- `running`: bool 是否运行中
- `mode`: 'focus' | 'break'