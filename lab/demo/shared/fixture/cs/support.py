"""智能客服 · 自动回复骨架

现在是空壳：所有意图都识别不出来，全部回退成 unknown。
要做的事见 ../tasks-cs.md
"""
import hashlib

# 关键词 → 意图 的规则表（待补）
RULES = []

TEMPLATES = {}

ESCALATE_AFTER = 2       # 连续几次识别失败就转人工


def classify(text: str) -> str:
    """返回 refund / logistics / human / unknown 之一。"""
    return "unknown"


def ticket_no(text: str) -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:4].upper()
    return "CS-" + h


def new_session() -> dict:
    """创建一个会话状态。"""
    return {"unknown": 0}


def reply(text: str, session: dict) -> dict:
    """返回 {intent, text, escalate}。"""
    return {"intent": "unknown", "text": "抱歉，我没听懂。", "escalate": False}
