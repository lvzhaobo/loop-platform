# step_debug · "写乱了会怎样"——LangGraph 的检查机制

这不是主线 step，而是一个**排错演示**：故意把图写错，看 LangGraph 在哪个阶段、报什么错。自己搭图混乱时，就知道去哪儿找问题。

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step_debug/main.py
```

## 三道防线 + 一个肉眼利器

| # | 故意犯的错 | 何时报 | 报什么 |
|---|---|---|---|
| ① | 悬空边（边指向没 `add_node` 的节点） | **compile 时** | `ValueError: Found edge ending at unknown node` |
| ② | 没有入口（忘了 `add_edge(START, ...)`） | **compile 时** | `ValueError: Graph must have an entrypoint` |
| ③ | 路由返回映射表里没有的名字 | **invoke 运行时** | `KeyError: 'typo'` |
| ④ | 死循环（回边永远成立） | **运行时兜底** | `GraphRecursionError`（默认 25 步，可调） |
| ⑤ | —— | 随时 | `draw_mermaid()` 画出结构，连线错一眼看穿 |

## 一句话

**结构错 → compile 报；路由错/循环失控 → 运行时报；看不清 → `draw_mermaid` 画出来。** 三道网基本兜住"写乱"。

再加编辑器的 `pyrightconfig.json`（`State` 用 `TypedDict`），返回错字段、类型不对在写的时候就会被标出来。
