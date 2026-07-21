# 编码约定(前馈 + 推理型 · 示范文件)

> 这是 harness-5 里唯一的**「前馈 + 推理型」**约束示范。
>
> - **前馈**:它在生成【之前】被拼进 prompt(和 spec/facts/constraints 一起注入)。
> - **推理型**:它靠模型**理解并遵循**,而**没有脚本机械校验**它——这正是它和
>   `facts.json`/`constraints.json`(前馈+计算型,能被 `gates.py` 逐条 assert)的本质区别。
>
> ⚠️ 权威背景:Martin Fowler 在《An example of LLM prompting for programming》里,
>   Xu Hao 的 prompt 大部分就是这种"implementation strategy + design guidelines"——
>   生成前注入、靠模型推理遵循、无法自动验。这类约束**有用且常用**,只是**焊不死下限**,
>   所以必须配合计算型门禁兜底。

## 约定条目(靠模型理解遵循)

- 函数用**动词开头**命名(`load_*` / `is_*` / `compute_*`),语义自解释。
- 关键函数上方写**一行中文注释**说明意图(不是复述代码)。
- 单一职责:一个函数只做一件事;超过约 20 行考虑拆分。
- 错误信息面向使用者、可读;不要吞异常(`except: pass`)。
- 命名一致性优先于个人偏好——同一概念在整个模块里用同一个词。

## 为什么这些不进 constraints.json

因为它们**无法用一行代码判定**:
- "命名语义自解释"——没有客观 assert。
- "注释说明意图而非复述代码"——需要理解,不是字符串匹配。
- "单一职责"——是判断,不是规则。

凡是能写成 `assert` 的(禁用模式、行数上限、字段范围),都该进 `constraints.json`(计算型);
凡是只能"靠理解遵循"的,才放这里(推理型)。**判据就一句:这条能不能写成 assert?**

## 如何接入(目前未接入,一行即可激活)

harness-5 的 `lib/model.py::build_prompt` 目前只注入 spec/facts/constraints。
要激活本文件,在 `build_prompt` 的 `sys_parts` 里加一段读取即可,例如:

```python
# 读取本文件并拼进系统提示(前馈注入)
conv = common.read(os.path.join(common.ROOT, "rules", "conventions.md"))
sys_parts.append("\n===== 编码约定(尽量遵循) =====\n" + conv)
```

> 注意:注入后会改变 prompt,进而影响 L4 的确定性哈希基线——激活前先重建基线。
> 这也说明"推理型约束"的代价:它进了上下文,但**生效与否是概率的**,且**不可自动验证**。
