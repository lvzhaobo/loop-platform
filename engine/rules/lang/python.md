# Python 编码规范

> 适用条件: manifest.tech.language == "python"
> 状态: ✅ 生效（当前项目默认语言）

## 代码风格
- 使用 4 空格缩进，不用 Tab
- 函数名 snake_case，类名 PascalCase
- 所有函数带 type hints（Python 3.10+ 语法）
- docstring 用 """ 三引号，描述参数和返回值

## Flask 特定
- 路由函数命名: 动词_名词（如 `show_list`、`get_detail`）
- 错误处理用 `@app.errorhandler`，不要裸 try/except 吞异常
- 配置从环境变量读取（`os.environ.get("KEY", default)`）
- 生产环境 `debug=False`

## 文件组织
- `app.py` 只放路由 + 启动逻辑，不放业务逻辑
- 纯逻辑模块（如 `core.py`、`models.py`）独立文件，方便单测
- 数据加载封装为单一函数（如 `load_items()`），全局只调用一次

## 安全
- 不硬编码密钥、密码、token
- 文件路径用 `os.path.join`，不用字符串拼接
- 禁止 `eval()`、`exec()`、`os.system()`、`subprocess` 调用
- 禁止 `pickle` 反序列化
