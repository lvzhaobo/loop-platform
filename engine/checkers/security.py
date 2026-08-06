"""安全扫描 Checker。"""

import os

from .base import Checker, CheckerResult
from . import register

BANNED_PATTERNS = ["eval(", "exec(", "os.system(", "subprocess.", "__import__(", "pickle.load"]


@register("security")
class SecurityChecker(Checker):
    name = "security"

    def check(self, target_dir: str, *, run_id: str = "") -> CheckerResult:
        hits = []
        for root, _, files in os.walk(target_dir):
            for fn in files:
                if fn.endswith(".py") and not fn.startswith("_"):
                    code = open(os.path.join(root, fn), encoding="utf-8").read()
                    for p in BANNED_PATTERNS:
                        if p in code:
                            rel = os.path.relpath(os.path.join(root, fn), target_dir)
                            hits.append(f"{rel}:{p}")

        return CheckerResult(
            pass_count=0 if hits else 1,
            total_count=1,
            checks=[{"name": "security", "pass": not hits, "detail": "; ".join(hits) if hits else ""}],
            all_pass=not hits,
        )
