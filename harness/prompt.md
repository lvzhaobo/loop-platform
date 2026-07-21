你是代码生成器。严格依据以下约束生成一个可运行的电商项目,不得自由发挥:

【必读约束】harness/rules/ 下全部文件
【必读规格】harness/spec/ 下全部文件

要求:
1. 完全遵守 tech-stack.md 的技术栈与禁用项。
2. 完全遵守 structure.md 的目录结构与命名。
3. data/products.json 按 data-model.md 生成 ≥8 条真实感数据。
4. 路由严格匹配 api-contract.md。
5. 页面样式严格匹配 ui-spec.md 的数值。
6. 生成完成后,项目必须能通过 harness/checklist.md 全部检查项。

只输出代码文件,不输出解释。
