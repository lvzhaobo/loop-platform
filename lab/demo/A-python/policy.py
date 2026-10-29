"""策略层：预算与终止判定。

三种终止：
  done       正常完成
  max_steps  步数耗尽（防死循环）
  escalated  同一动作重复超限 → 升级给人（R1 失败 → R3 转人）
"""

class Budget:
    def __init__(self, cfg):
        self.max_steps = cfg["int"]("MAX_STEPS", 30)
        self.max_retries = cfg["int"]("MAX_RETRIES", 2)
        self.steps = 0
        self.sig = None
        self.repeat = 0

    def tick(self) -> bool:
        """还能不能走下一步。"""
        self.steps += 1
        return self.steps <= self.max_steps

    def observe(self, signature: str):
        """同一动作重复超过 max_retries 次 → 要求升级。"""
        if signature == self.sig:
            self.repeat += 1
        else:
            self.sig, self.repeat = signature, 1
        if self.repeat > self.max_retries:
            return "escalate"
        return None

    def summary(self):
        return {"steps": self.steps, "max_steps": self.max_steps,
                "max_retries": self.max_retries}
