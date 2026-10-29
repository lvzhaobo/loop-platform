"""智能客服 · 参考答案"""
import hashlib

RULES = [
    (("退款", "退货", "退钱"), "refund"),
    (("物流", "快递", "到哪", "发货"), "logistics"),
    (("人工", "客服", "投诉", "转人工"), "human"),
]

TEMPLATES = {
    "refund": "已收到您的退款诉求，我们会在 1 个工作日内处理。",
    "logistics": "您的包裹正在运输中，预计 2 天内送达。",
    "human": "正在为您转接人工客服，请稍候。",
    "unknown": "抱歉，这个问题我还处理不了。",
}

ESCALATE_AFTER = 2


def classify(text: str) -> str:
    for kws, intent in RULES:
        if any(k in text for k in kws):
            return intent
    return "unknown"


def ticket_no(text: str) -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:4].upper()
    return "CS-" + h


def new_session() -> dict:
    return {"unknown": 0}


def reply(text: str, session: dict) -> dict:
    intent = classify(text)
    if intent == "unknown":
        session["unknown"] = session.get("unknown", 0) + 1
    else:
        session["unknown"] = 0

    escalate = intent == "human" or session["unknown"] >= ESCALATE_AFTER
    body = TEMPLATES.get(intent, TEMPLATES["unknown"])
    return {
        "intent": intent,
        "text": body + " 工单号：" + ticket_no(text),
        "escalate": escalate,
    }
