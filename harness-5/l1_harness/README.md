# L1 · Harness(环境 + 门禁)

## 讲什么
**Harness = 给一次生成套上一个可控环境**:生成前有约束和自洽性检查,生成后有验收。
这一层回答:"怎么知道生成对不对?"

## 组件(相对 L0 新增)
- `constraints.json`(根目录):**宪法**,硬约束(禁用模式、行数上限)。
- `lib/gates.py::check_consistency`:**生成前**门禁,最便宜——facts 与 spec 不许漂移。
- `lib/gates.py::verify`:**生成后**验收——结构/安全/行数/跑测试,一次收集所有问题。
- `gate.py`:把三步串起来(consistency → generate → verify)。

## 三关顺序为什么这样排
从**便宜到贵**:自洽性(纯文本比对,0 成本)→ 生成(花钱)→ 验收(跑测试)。
便宜的关卡先跑,能省钱就省钱——这是 harness 设计的核心直觉。

## 动手
```bash
python harness-5/l1_harness/gate.py; echo "退出码=$?"
```
sample 模式下会看到:自洽性 ✓ → 生成(BUGGY)→ 验收在"测试全绿"处 **FAIL**,退出码 1。

## 观察到的问题(引出 L2)
- L1 **只发现、不修复**。发现 factorial 错了,然后呢?人肉改?
- **教学点**:把"失败报告"回喂给模型让它自己修,再验收——重复到过为止,就是 **Loop**。→ L2。
