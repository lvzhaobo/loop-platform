# 规格:mathkit 数学工具模块

> 这是**人读规格**(自然语言契约)。机器可读的唯一事实源见 `spec/facts.json`。
> 门禁会检查:facts.json 里声明的每个函数,都必须能在本文件里找到落点(自洽性)。

## 目标

生成一个纯标准库、无第三方依赖的 Python 模块 `mathkit.py`,实现以下 4 个函数。

## 函数契约

### add(a, b)
返回两个数之和。
- `add(2, 3)` → `5`
- `add(-1, 1)` → `0`

### is_prime(n)
判断 n 是否为素数,返回 `bool`。
- 小于 2 的一律为 `False`。
- `is_prime(2)` → `True`,`is_prime(4)` → `False`,`is_prime(13)` → `True`。

### fib(n)
返回第 n 个斐波那契数(0 索引):`fib(0)=0`,`fib(1)=1`。
- `fib(7)` → `13`,`fib(10)` → `55`。

### factorial(n)
返回 n 的阶乘。
- `factorial(0)` → `1`(**注意:0 的阶乘是 1,常见 bug 是这里返回 0**)。
- `factorial(5)` → `120`。

## 约束(与 constraints.json 一致)

- 只用 Python 标准库,不得出现 `eval(` / `exec(` / `os.system` / `import os`。
- 模块行数不超过 120 行。
