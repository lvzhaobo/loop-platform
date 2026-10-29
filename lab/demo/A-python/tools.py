"""工具层：模型能做的事，全在这里被约束。

两条硬边界：
  ① 文件：只能碰 WORKSPACE 里面的路径（路径穿越会被拒）
  ② 命令：argv 前缀白名单（不是字符串包含，防注入）
模型"知不知道"这些边界，不影响结果 —— 它只会拿到一个拒绝结果。
"""
import subprocess
from pathlib import Path

# ── 命令白名单：只放行这些 argv 前缀 ──────────────────────
ALLOWED_COMMANDS = [
    ("python", "check.py"),
    ("python3", "check.py"),
    ("ls",),
    ("cat",),
    ("node", "--check"),
]


def _p(t, d=""):
    o = {"type": t}
    if d:
        o["description"] = d
    return o

def _fn(name, desc, props=None, required=None):
    params = {"type": "object", "properties": props or {}}
    if required:
        params["required"] = required
    return {"type": "function",
            "function": {"name": name, "description": desc, "parameters": params}}

def match_rule(argv):
    """返回命中的白名单规则（tuple）或 None。"""
    t = tuple(argv)
    for a in ALLOWED_COMMANDS:
        if t[:len(a)] == a:
            return a
    return None

def _allowed(argv) -> bool:
    return match_rule(argv) is not None

class Tools:
    def __init__(self, cfg, session, approver, emit=None, check_path=None):
        self.cfg = cfg
        self.ws: Path = cfg["WORKSPACE_PATH"]
        self.shared: Path = cfg["SHARED"]
        self.session = session
        self.approver = approver
        self.emit = emit or (lambda ev: None)
        self.check_path = Path(check_path) if check_path else (self.shared / "check.py")
        self.denied = 0          # 统计：被拒过几次（演示用）

    # ── 路径监狱 ────────────────────────────────────────
    def _resolve(self, rel: str) -> Path:
        p = (self.ws / rel).resolve()
        if p != self.ws and self.ws not in p.parents:
            raise PermissionError(f"路径越界：{rel} 不在工作区内")
        return p

    # ── schema：模型看到的世界 ───────────────────────────
    def spec(self):
        return [
            _fn("list_files", "列出工作区某个目录下的文件",
                {"dir": _p("string", "相对工作区的目录，默认 .")}),
            _fn("read_file", "读取工作区内一个文本文件",
                {"path": _p("string", "相对工作区的路径")}, ["path"]),
            _fn("write_file", "覆盖写入工作区内的文件（需要审批）",
                {"path": _p("string"), "content": _p("string")}, ["path", "content"]),
            _fn("run_command", "执行一条命令（只允许白名单内的命令）",
                {"argv": {"type": "array", "items": {"type": "string"},
                          "description": '命令与参数的数组，例如 ["ls","-la"]'}}, ["argv"]),
            _fn("run_check", "运行门禁 check.py，返回退出码与输出"),
        ]

    # ── 执行 ────────────────────────────────────────────
    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, "_" + name, None)
        if not fn:
            return {"error": f"没有这个工具：{name}"}
        try:
            return fn(**args)
        except PermissionError as e:
            self.denied += 1
            return {"denied": True, "reason": str(e)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def _list_files(self, dir="."):
        p = self._resolve(dir)
        items = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
        return {"files": items}

    def _read_file(self, path):
        p = self._resolve(path)
        return {"content": p.read_text(encoding="utf-8")[:6000]}

    def _write_file(self, path, content):
        p = self._resolve(path)
        before = p.read_text(encoding="utf-8") if p.exists() else ""
        old = len(before)
        if self.cfg["bool"]("NEED_APPROVAL"):
            ok = self.approver("写入文件", f"{path}（{old} → {len(content)} 字符）",
                               self.cfg.get("AUTO_YES", False))
            if not ok:
                self.denied += 1
                return {"denied": True, "reason": "人类拒绝了这次写入"}
        p.write_text(content, encoding="utf-8")
        self.emit({"type": "file_write", "path": path,
                   "before": before[-4000:], "after": content[-4000:],
                   "bytes": len(content.encode())})
        return {"ok": True, "path": path, "bytes": len(content.encode())}

    def _arg_path_ok(self, arg):
        """参数里的路径也必须落在工作区内 —— 否则 cat 能绕过 read_file 的监狱。"""
        if not isinstance(arg, str) or not arg or arg.startswith("-"):
            return True
        if arg.startswith(("/", "~")) or ".." in arg:
            p = (self.ws / arg).resolve()
            return p == self.ws or self.ws in p.parents
        return True

    def _run_command(self, argv):
        if not isinstance(argv, list):
            return {"denied": True, "reason": "argv 必须是数组（防止 shell 拼接）"}
        rule = match_rule(argv)
        if rule is None:
            self.denied += 1
            self.emit({"type": "whitelist", "argv": argv, "allowed": False, "rule": None,
                       "rules": [" ".join(a) for a in ALLOWED_COMMANDS]})
            return {"denied": True,
                    "reason": f"不在白名单：{argv}",
                    "hint": "只能跑 " + ", ".join(" ".join(a) for a in ALLOWED_COMMANDS)}
        self.emit({"type": "whitelist", "argv": argv, "allowed": True, "rule": " ".join(rule)})
        # 路径监狱：光校验命令名不够，参数里的路径也要管
        bad = [a for a in argv[1:] if not self._arg_path_ok(a)]
        if bad:
            self.denied += 1
            self.emit({"type": "whitelist", "argv": argv, "allowed": False, "rule": None,
                       "rules": [" ".join(a) for a in ALLOWED_COMMANDS]})
            return {"denied": True,
                    "reason": f"参数路径越界：{bad}",
                    "hint": "命令名在白名单里，但它的参数指向了工作区外。cat 和 read_file 是同一个能力。"}

        if self.cfg["bool"]("NEED_APPROVAL"):
            ok = self.approver("执行命令", " ".join(argv), self.cfg.get("AUTO_YES", False))
            if not ok:
                self.denied += 1
                return {"denied": True, "reason": "人类拒绝了这次执行"}
        # shell=False + list 参数：即使 argv 里带 ; 也不会被 shell 解释
        p = subprocess.run(argv, cwd=self.ws, capture_output=True, text=True,
                           timeout=self.cfg["int"]("CMD_TIMEOUT", 120))
        return {"code": p.returncode, "stdout": p.stdout[-3000:], "stderr": p.stderr[-1200:]}

    def _run_check(self):
        script = self.check_path
        p = subprocess.run(["python3", str(script)], capture_output=True, text=True, timeout=180)
        self.emit({"type": "gate", "code": p.returncode, "stdout": p.stdout[-2500:]})
        return {"code": p.returncode,
                "stdout": p.stdout[-3000:],
                "stderr": p.stderr[-800:],
                "note": "退出码 0 = 门禁绿，非 0 = 门禁红"}
