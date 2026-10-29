"""TODO 1 —— 白名单（权限约束）

规则：只有出现下面的命令能执行，其余一律拒绝。
      拒绝不是抛异常，是返回一个「被拒」的结果，让模型知道改方案。
"""

# ── 你要补的地方 ─────────────────────────────────────────
ALLOWED_COMMANDS = [
    # 格式：("命令", "子命令"), 例如 ("npm", "test")
    # TODO: 让 `npm test` 可以通过
    # TODO: 让 `python check.py` 可以通过
    # 提示：这里只写「允许什么」，不写「禁止什么」——黑名单永远有漏的
]
# ────────────────────────────────────────────────────────


def allowed(argv) -> bool:
    """argv 是不是在白名单里（前缀匹配）。"""
    t = tuple(argv)
    return any(t[:len(a)] == a for a in ALLOWED_COMMANDS)


def run(argv, workspace="."):
    """执行一条命令。不合法就返回 {"denied": True}。"""
    import subprocess

    if not isinstance(argv, list):
        return {"denied": True, "reason": "argv 必须是数组（防止 shell 拼接）"}

    if not allowed(argv):
        return {"denied": True, "reason": f"不在白名单：{argv}"}

    # shell=False + list 参数：即使参数里带 ; 也不会被 shell 解释
    p = subprocess.run(argv, cwd=workspace, capture_output=True, text=True, timeout=60)
    return {"code": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-800:]}
