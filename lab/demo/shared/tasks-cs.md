# 任务：把智能客服的自动回复补全

## 背景
`fixture/cs/support.py` 是一个客服自动回复的骨架：函数签名都在，但分类永远返回 unknown。
产品要求它能识别三类意图，识别不了就转人工。

## 要做的事

1. **意图识别**（`classify`）
   - 消息里含「退款 / 退货 / 退钱」→ `refund`
   - 含「物流 / 快递 / 到哪 / 发货」→ `logistics`
   - 含「人工 / 客服 / 投诉 / 转人工」→ `human`
   - 都不含 → `unknown`

2. **回复模板**（`TEMPLATES`）
   - 每种意图一句固定话术
   - **每条回复都必须带工单号**，格式 `工单号：CS-XXXX`（用已有的 `ticket_no`）

3. **转人工**（`reply`）
   - `human` 意图 → 直接转人工
   - 同一个会话里**连续**出现 2 次 `unknown` → 第 2 次开始转人工
   - 中途识别成功要**重置**计数（否则正常咨询也会被转走）

4. **不能动的东西**
   - 不许改 `check-cs.py`
   - 只用标准库，不许联网
   - 保持 `classify / reply / new_session / ticket_no` 四个函数的签名

## 验收
`python3 shared/check-cs.py` 退出码为 0。
