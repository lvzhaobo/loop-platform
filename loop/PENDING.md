# 待实现功能

---

## 推理型约束（LLM-as-Judge）

**状态**：接口已定义 (guardrails.py: reasoning_review, reasoning_style_check)，Mock 实现

---

## 推理型约束（前馈 inject-infer）

**状态**：接口已定义 (checker.py: infer-01, infer-02)，Mock 实现

---

## 已完成（2026-07-25）

- ✅ **LangGraph 多 Agent 协作**：`langgraph_orchestrator.py`，五 Agent 管道（分析→生成→审查→测试→集成），Mock 模式通过
- ✅ **MumuSpec 集成**：`mumuspec_compiler.py` R1-R6 六轮 Skill 调度器 + `mumuspec_grade.py` 四维评分，Mock 模式通过
- ✅ **语言分层规则**：Python/Java/HTML-CSS 条件加载
- ✅ **AGENTS.md**：最高优先级 Agent 指令
