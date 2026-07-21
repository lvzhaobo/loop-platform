# step4 · 回边：把"打回"指回上游，分支就变成了循环

只比 step3 多**一个概念：回边**。step3 判"打回"时走向 END；这里把它改成走回 `maker`——于是形成一个【生成→检查→不达标就回去重生成】的循环，直到达标才 END。

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step4_loop/main.py
```

## 要点

- **循环 = 图里的一条回边**。LangGraph 不写 `while`，而是让某条边指回上游节点：`{"retry": "maker"}`。
- ⚙️ 有循环就可能跑不停，LangGraph 用 `recursion_limit`（默认 25）兜底。真正"该不该停"的判据（达标/超限）写在节点+路由里 —— 那是 step8 的护栏。

## 预期输出

```
[maker] 第 1 轮 ... [check] 打分 = 6 → 回 maker
[maker] 第 2 轮 ... [check] 打分 = 10 → 达标结束
[共循环] 2 轮后达标
```
