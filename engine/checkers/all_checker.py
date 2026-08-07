"""全量 Checker：运行所有已注册 Checker。"""

from .base import Checker, CheckerResult
from . import load_checker, list_checkers


class AllChecker(Checker):
    name = "all"

    def check(self, target_dir: str, *, run_id: str = "", acceptance_path: str = "") -> CheckerResult:
        all_checks = []
        for name in list_checkers():
            try:
                c = load_checker(name)
                r = c.check(target_dir, run_id=run_id, acceptance_path=acceptance_path)
                all_checks.extend(r.checks)
            except Exception as e:
                all_checks.append({"name": name, "pass": False, "status": "unavailable", "detail": str(e)[:100]})

        pass_count = sum(1 for c in all_checks if c["pass"])
        return CheckerResult(
            pass_count=pass_count, total_count=len(all_checks),
            checks=all_checks, all_pass=pass_count == len(all_checks),
        )
