# 通用基座 · 安全规范(跨任务,强制)

- 禁止硬编码任何密钥 / 口令 / Token 到代码或数据文件
- 用户输入(路由参数、查询串)必须校验类型;不存在的资源返回 4xx,禁止 500 泄露堆栈
- 不得引入未在 `task/tech-stack.md` 中声明的第三方依赖
- 不得访问外网、不得读取项目目录之外的文件
- 禁止出现危险调用(见 `constraints.json.banned_code_patterns`,如 `eval(` / `exec(` / `os.system(` / `subprocess.` / `__import__(` / `pickle.load`)
- 生产禁止 `debug=True`;示例可用但需可通过环境变量关闭
