# loop-specs

> **需求 / 规格仓** —— 与实现解耦的业务规格，供产品/评审/协作使用。
> 平台仓 `loop-platform` 从这里（或飞书）取需求，生成的应用发到 `loop-sample`。

## 目录结构

```
cases/
  ecommerce/spec/   电商用例规格（data-model / api-contract / ui-spec）
  blog/spec/        博客用例规格
  education/spec/   在线教育用例规格
checklist.md        通用验收清单
```

## spec 三件套是什么

每个用例的 `spec/` 下有三份**结构化 Markdown**，是该应用的**唯一事实源**：

| 文件 | 定义 | 下游 |
|---|---|---|
| `data-model.md` | 实体字段 / 类型 / 必填 / 约束（表格） | 编译成 case.json 的数据契约 |
| `api-contract.md` | 路由名称 / 路径（表格） | 编译成 routes |
| `ui-spec.md` | list_marker / detail_markers / 配色（键值表） | 编译成 UI 校验标记 |

平台侧 `harness-4/tools/compile_spec.py` 把这三份**确定性编译**成 `case.json` 契约，
再由引擎生成代码、`verify.py` 逐条验收。**改规格只改这里**，实现随之重生成。

> 注：本仓是规格的**协作副本**。平台仓 `harness-4/cases/*/spec/` 保有运行时工作副本；
> 二者通过归档流保持同步（见 loop-platform 的《GitHub多仓发布方案》流 A）。
