"""TODO 3 —— 终止判定（重试预算）

规则：同一个动作重复超过 max_retries 次，就不能再重试了，要升级给人。
      升级不是报错退出，是返回 "escalate"，由上层转人工。
"""


class Budget:
    def __init__(self, max_retries=2, max_steps=10):
        self.max_retries = max_retries
        self.max_steps = max_steps
        self.steps = 0
        self.sig = None
        self.repeat = 0

    def usable(self) -> bool:
        """还能不能走下一步。"""
        self.steps += 1
        return self.steps <= self.max_steps

    def observe(self, signature: str):
        if signature == self.sig:
            self.repeat += 1
        else:
            self.sig, self.repeat = signature, 1
        return "escalate" if self.repeat > self.max_retries else None
