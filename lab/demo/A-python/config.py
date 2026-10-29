"""读取 demo/config.env —— 三个装置共用的唯一配置点。"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent

def load() -> dict:
    cfg = {}
    p = DEMO / "config.env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")

    # 环境变量优先级更高（方便 CI 覆盖）
    for k in list(cfg):
        if os.environ.get(k):
            cfg[k] = os.environ[k]

    d = {
        "DEEPSEEK_API_KEY": "", "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_MODEL": "deepseek-chat", "WORKSPACE": "../shared/fixture/pomodoro",
        "MAX_RETRIES": "2", "MAX_STEPS": "30", "NEED_APPROVAL": "true",
        "CMD_TIMEOUT": "120", "MOCK": "false",
    }
    for k, v in d.items():
        cfg.setdefault(k, v)

    ws = Path(cfg["WORKSPACE"])
    cfg["WORKSPACE_PATH"] = (ws if ws.is_absolute() else (DEMO / ws)).resolve()
    cfg["SHARED"] = DEMO / "shared"
    cfg.setdefault("MOCK_SCRIPT", str(DEMO / "shared" / "mock" / "pomodoro.json"))
    cfg["bool"] = lambda k: str(cfg.get(k, "")).lower() in ("1", "true", "yes", "on")
    cfg["int"] = lambda k, dv=0: int(cfg.get(k, dv) or dv)
    return cfg
