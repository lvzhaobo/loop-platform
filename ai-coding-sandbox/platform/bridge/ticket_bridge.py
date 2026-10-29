#!/usr/bin/env python3
"""
ticket_bridge.py — 工单桥 v0.1（本地工单 → 外部系统；禅道先行，Jira 预留）

口径（承接 2026-10-16 选型分析结论）：
- 适配器模式：中间 JSON 票面 → adapter 负责格式转换；三方法 create / update_status / close
- 提票阈值分级：默认仅 escalate 开外部票（避免噪音），--threshold pending_fix|always 可放开
- 防重复：同 fingerprint（任务+轮次+规则集）留痕 bridge-state.json，重复提交跳过（--force 重发）
- 安全：账号密码不落配置文件，从环境变量读（配置里只写环境变量名）

用法：
  python3 platform/bridge/ticket_bridge.py submit --ticket platform/data/tickets/ticket-r1.md
  python3 platform/bridge/ticket_bridge.py submit --ticket <...> --dry-run   # 只打票面与请求，不发送
  python3 platform/bridge/ticket_bridge.py submit --ticket <...> --threshold always
  python3 platform/bridge/ticket_bridge.py update --remote-id 42 --status open --comment "..."
  python3 platform/bridge/ticket_bridge.py close  --remote-id 42 --comment "复检通过，违规归零"
  python3 platform/bridge/ticket_bridge.py status

Jira adapter 为预留骨架（未实测）：走 REST v2 端点以纯文本作为描述，规避 v3 的 ADF 强格式。
禅道路径与字段按部署版本可调（config 的 routes / field_map），默认按 REST v1 形态（16.5+）。
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent          # platform/bridge/
PLATFORM = BRIDGE.parent                          # platform/
DEFAULT_CONFIG = BRIDGE / "bridge-config.json"
STATE_FILE = BRIDGE / "bridge-state.json"

TITLE_RE = re.compile(r"^#\s*工单（第\s*(\d+)\s*轮）—\s*(.+)$")
FIELD_RE = re.compile(r"^-\s*([^：]+)：(.+)$")
ITEM_RE = re.compile(r"^\d+\.\s*\[(\w+)\]\s*(.+?):(\d+)\s*$")


class BridgeError(Exception):
    """桥层错误（网络 / 认证 / 解析），带明确原因，不静默降级"""


# ---------- 基础 ----------

def load_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def load_bridge_config(explicit=None):
    p = Path(explicit).resolve() if explicit else DEFAULT_CONFIG
    if not p.exists():
        raise BridgeError(f"桥配置不存在：{p}（先复制 bridge-config.json 样例并按环境修改）")
    return load_json(p)


def platform_logs_dir() -> Path:
    """logs 目录单源：读 platform/config.json 的 logs_dir；缺省 platform/data/logs"""
    cfg_file = PLATFORM / "config.json"
    if cfg_file.exists():
        try:
            rel = load_json(cfg_file).get("logs_dir", "data/logs")
            return (PLATFORM / rel).resolve()
        except (json.JSONDecodeError, OSError):
            pass
    return PLATFORM / "data" / "logs"


def http_request(method: str, url: str, payload=None, headers=None, timeout=10):
    """极简 urllib 封装 -> (status, parsed_body, raw_text)；失败抛 BridgeError"""
    data = None
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"_raw": raw}
            return resp.status, body, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise BridgeError(f"HTTP {e.code} {method} {url}：{raw[:300]}")
    except urllib.error.URLError as e:
        raise BridgeError(f"网络不可达 {method} {url}：{e.reason}")


# ---------- 票面构建 ----------

def parse_ticket(md_path: Path):
    """解析本地工单（ticket-rN.md）→ 结构化字段"""
    text = Path(md_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    out = {}
    out["body_md"] = text
    out["items"] = []
    out["by_rule"] = []
    for ln in lines:
        m = TITLE_RE.match(ln)
        if m:
            out["round"] = int(m.group(1))
            out["task"] = m.group(2).strip()
            continue
        m = FIELD_RE.match(ln)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            if key == "目标":
                out["target"] = val
            elif key == "时间":
                out["ts"] = val
            elif key == "违规":
                mv = re.match(r"(\d+)\s*处（(.+)）", val)
                if mv:
                    out["violations_n"] = int(mv.group(1))
                    out["by_rule"] = [x.strip() for x in mv.group(2).split("，") if x.strip()]
            continue
        m = ITEM_RE.match(ln)
        if m:
            out["items"].append({"rule": m.group(1), "file": m.group(2),
                                 "line": int(m.group(3))})
    missing = [k for k in ("task", "round") if k not in out]
    if missing:
        raise BridgeError(f"工单解析失败（缺 {','.join(missing)}）：{md_path}")
    return out


def find_trace(task: str):
    """在 logs 目录（含子目录）找该任务最新 trace JSONL；找不到返回 None"""
    logs = platform_logs_dir()
    if not logs.exists():
        return None
    cands = sorted(logs.rglob(f"{task}*.jsonl"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def load_trace_entry(trace_path, round_no: int):
    """读 trace JSONL 中 round 匹配的记录；无匹配返回 None"""
    if not trace_path or not Path(trace_path).exists():
        return None
    for ln in Path(trace_path).read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("round") == round_no:
            return e
    return None


def severity_of(entry, ticket_info) -> str:
    """判定票的级别：escalate / pending_fix（trace 缺失时按工单本身降为 pending_fix）"""
    if entry:
        result = str(entry.get("result", "")).lower()
        action = str(entry.get("action", "")).lower()
        if "escalat" in result or "escalat" in action:
            return "escalate"
        if "pending_fix" in result:
            return "pending_fix"
        if result == "closed":
            return "closed"
    return "pending_fix" if ticket_info.get("violations_n", 0) > 0 else "closed"


THRESHOLD_RANK = {"escalate": 2, "pending_fix": 1, "closed": 0}


def passes_threshold(severity: str, threshold: str) -> bool:
    if threshold == "always":
        return True
    want = THRESHOLD_RANK.get(threshold, 2)
    return THRESHOLD_RANK.get(severity, 0) >= want


def build_face(ticket_path: Path, trace_path, threshold: str, cfg):
    """本地工单 + trace → 中间 JSON 票面（与外部系统解耦的交换格式）"""
    info = parse_ticket(ticket_path)
    entry = load_trace_entry(trace_path, info["round"]) if trace_path else None
    severity = severity_of(entry, info)
    if not passes_threshold(severity, threshold):
        return {"_skip": True, "severity": severity,
                "reason": f"未达阈值 {threshold}（当前 {severity}）"}
    rules = sorted({i["rule"] for i in info["items"]})
    fp = f"{info['task']}|r{info['round']}|{','.join(rules)}"
    face = {
        "fingerprint": fp,
        "title": f"[MumuLoop] {info['task']} 第 {info['round']} 轮检查未通过"
                 f"（{info.get('violations_n', len(info['items']))} 处违规）",
        "target": info.get("target", ""),
        "round": info["round"],
        "severity": severity,
        "priority": cfg.get("priority_map", {}).get(severity, "P3"),
        "tags": ["mumuloop", "harness-gate"],
        "body_md": info["body_md"],
        "trace_ref": str(trace_path) if trace_path else None,
        "ticket_ref": str(ticket_path),
        "by_rule": info["by_rule"],
    }
    return face


# ---------- Adapter（适配器模式：三方法接口） ----------

class TicketAdapter:
    name = "base"

    def __init__(self, cfg, overrides=None):
        self.cfg = cfg
        self.overrides = overrides or {}

    def create(self, face):
        raise NotImplementedError

    def update_status(self, remote_id, status: str, comment: str = ""):
        raise NotImplementedError

    def close(self, remote_id, comment: str = ""):
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class ZenTaoAdapter(TicketAdapter):
    """禅道 REST v1：账号密码换 token；路由与字段按部署版本可调"""

    name = "zentao"

    def __init__(self, cfg, overrides=None):
        super().__init__(cfg, overrides)
        z = dict(cfg.get("zentao", {}))
        z.update(overrides or {})
        self.z = z
        self.base = self.z["base_url"].rstrip("/")
        self.api = self.z.get("api_base", "/api.php/v1")
        self.routes = {"token": "/tokens", "create_ticket": "/tickets",
                       "update_ticket": "/tickets/{id}", "close_ticket": "/tickets/{id}/close"}
        self.routes.update(self.z.get("routes", {}))
        self.field_map = {"title": "title", "body_md": "desc", "priority": "pri",
                          "tags": "keywords"}
        self.field_map.update(self.z.get("field_map", {}))
        self._token = None

    def _cred(self):
        acc = os.getenv(self.z.get("account_env", ""), "")
        pwd = os.getenv(self.z.get("password_env", ""), "")
        if not acc or not pwd:
            raise BridgeError(
                f"禅道凭据缺失：请设置环境变量 "
                f"{self.z.get('account_env')} / {self.z.get('password_env')}")
        return acc, pwd

    def _login(self):
        acc, pwd = self._cred()
        _, body, _ = http_request("POST", self.base + self.api + self.routes["token"],
                                  {"account": acc, "password": pwd})
        token = body.get("token")
        if not token:
            raise BridgeError(f"禅道 token 获取失败：{body}")
        self._token = token

    def _post(self, path: str, payload):
        if self._token is None:
            self._login()
        return http_request("POST", self.base + self.api + path, payload,
                            headers={"Token": self._token})

    def _payload_from_face(self, face):
        fm = self.field_map
        p = {fm["title"]: face["title"],
             fm["body_md"]: face["body_md"],
             fm["priority"]: face["priority"]}
        if face.get("tags"):
            p[fm["tags"]] = ",".join(face["tags"])
        return p

    def create(self, face):
        _, body, _ = self._post(self.routes["create_ticket"], self._payload_from_face(face))
        return {"remote_id": body.get("id") or body.get("data", {}).get("id"), "raw": body}

    def update_status(self, remote_id, status: str, comment: str = ""):
        path = self.routes["update_ticket"].format(id=remote_id)
        _, body, _ = self._post(path, {"status": status, "comment": comment})
        return {"remote_id": remote_id, "raw": body}

    def close(self, remote_id, comment: str = ""):
        path = self.routes["close_ticket"].format(id=remote_id)
        _, body, _ = self._post(path, {"comment": comment})
        return {"remote_id": remote_id, "raw": body}

    def describe(self) -> str:
        return f"禅道 {self.base}{self.api}（token 认证，账号环境变量 {self.z.get('account_env')}）"


class JiraAdapter(TicketAdapter):
    """Jira 预留骨架（未实测）：Basic(email, api_token)；REST v2 纯文本规避 ADF"""

    name = "jira"

    def __init__(self, cfg, overrides=None):
        super().__init__(cfg, overrides)
        j = dict(cfg.get("jira", {}))
        j.update(overrides or {})
        self.j = j
        self.base = j.get("base_url", "").rstrip("/")
        self.ver = j.get("api_version", "2")

    def _headers(self):
        email = os.getenv(self.j.get("email_env", ""), "")
        token = os.getenv(self.j.get("token_env", ""), "")
        if not email or not token:
            raise BridgeError(
                f"Jira 凭据缺失：请设置环境变量 "
                f"{self.j.get('email_env')} / {self.j.get('token_env')}")
        basic = base64.b64encode(f"{email}:{token}".encode()).decode()
        return {"Authorization": f"Basic {basic}"}

    def create(self, face):
        payload = {"fields": {
            "project": {"key": self.j.get("project_key", "")},
            "summary": face["title"],
            "description": face["body_md"],          # v2 端点收纯文本（规避 ADF）
            "issuetype": {"name": self.j.get("issue_type", "Task")},
        }}
        _, body, _ = http_request("POST", f"{self.base}/rest/api/{self.ver}/issue",
                                  payload, headers=self._headers())
        return {"remote_id": body.get("id"), "raw": body}

    def update_status(self, remote_id, status: str, comment: str = ""):
        # Jira 状态流转依赖工作流 transition id（配置提供）
        tid = self.j.get("transition_ids", {}).get(status)
        if not tid:
            raise BridgeError(f"Jira 预留骨架：未配置状态 {status} 的 transition id")
        _, body, _ = http_request(
            "POST", f"{self.base}/rest/api/{self.ver}/issue/{remote_id}/transitions",
            {"transition": {"id": tid}}, headers=self._headers())
        return {"remote_id": remote_id, "raw": body}

    def close(self, remote_id, comment: str = ""):
        return self.update_status(remote_id, "closed", comment)

    def describe(self) -> str:
        return (f"Jira {self.base}（REST v{self.ver}，预留骨架未实测；"
                f"邮箱环境变量 {self.j.get('email_env')}）")


def make_adapter(cfg, provider: str, overrides=None) -> TicketAdapter:
    if provider == "zentao":
        return ZenTaoAdapter(cfg, overrides)
    if provider == "jira":
        return JiraAdapter(cfg, overrides)
    raise BridgeError(f"未知 provider：{provider}（支持 zentao / jira）")


# ---------- 状态（防重复） ----------

def load_state():
    if STATE_FILE.exists():
        try:
            return load_json(STATE_FILE)
        except json.JSONDecodeError:
            pass
    return {"submitted": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


# ---------- 命令 ----------

def cmd_submit(args, cfg):
    ticket_path = Path(args.ticket).resolve()
    if not ticket_path.exists():
        raise BridgeError(f"工单不存在：{ticket_path}")
    trace_path = Path(args.trace).resolve() if args.trace else find_trace(parse_ticket(ticket_path)["task"])
    threshold = args.threshold or cfg.get("threshold", "escalate")
    provider = args.provider or cfg.get("provider", "zentao")

    face = build_face(ticket_path, trace_path, threshold, cfg)
    print(f"票面（中间 JSON，provider={provider}）：")
    print(json.dumps(face, ensure_ascii=False, indent=2)[:2000])
    if face.get("_skip"):
        print(f"[跳过] {face['reason']}（阈值可调：--threshold pending_fix|always）")
        return 0

    state = load_state()
    if face["fingerprint"] in state["submitted"] and not args.force:
        rec = state["submitted"][face["fingerprint"]]
        print(f"[防重复] 已提交过（remote_id={rec.get('remote_id')} @ {rec.get('submitted_at')}）；"
              f"如需重发用 --force")
        return 0

    overrides = {}
    if args.base_url:
        overrides["base_url"] = args.base_url
    adapter = make_adapter(cfg, provider, overrides)
    print(f"适配器：{adapter.describe()}")

    if args.dry_run:
        print("[dry-run] 不发送。将调用 adapter.create()：")
        print(f"  -> {provider} create，票面指纹 {face['fingerprint']}")
        return 0

    result = adapter.create(face)
    state["submitted"][face["fingerprint"]] = {
        "provider": provider, "remote_id": result.get("remote_id"),
        "ticket_ref": face["ticket_ref"],
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_state(state)
    print(f"[已提交] {provider} remote_id={result.get('remote_id')} "
          f"指纹={face['fingerprint']} → {STATE_FILE.name}")
    return 0


def cmd_update(args, cfg):
    provider = args.provider or cfg.get("provider", "zentao")
    overrides = {"base_url": args.base_url} if args.base_url else {}
    adapter = make_adapter(cfg, provider, overrides)
    result = adapter.update_status(args.remote_id, args.status, args.comment or "")
    print(f"[已更新] {provider} #{args.remote_id} -> {args.status}：{result.get('raw')}")
    return 0


def cmd_close(args, cfg):
    provider = args.provider or cfg.get("provider", "zentao")
    overrides = {"base_url": args.base_url} if args.base_url else {}
    adapter = make_adapter(cfg, provider, overrides)
    result = adapter.close(args.remote_id, args.comment or "")
    # 状态回写：bridge-state.json 里对应 remote_id 的票标记 closed
    state = load_state()
    for fp, rec in state["submitted"].items():
        if str(rec.get("remote_id")) == str(args.remote_id):
            rec["closed_at"] = datetime.now().isoformat(timespec="seconds")
            rec["close_comment"] = args.comment or ""
    save_state(state)
    print(f"[已关闭] {provider} #{args.remote_id}：{result.get('raw')}（state 已回写）")
    return 0


def cmd_status(args, cfg):
    state = load_state()
    subs = state.get("submitted", {})
    if not subs:
        print("暂无提交记录（bridge-state.json 为空）")
        return 0
    print(f"{'fingerprint':<60}{'provider':<10}{'remote_id':<11}{'submitted_at':<21}closed_at")
    for fp, rec in subs.items():
        print(f"{fp:<60}{rec.get('provider', ''):<10}{str(rec.get('remote_id', '')):<11}"
              f"{rec.get('submitted_at', ''):<21}{rec.get('closed_at', '-')}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="工单桥 v0.1（本地工单 → 禅道/Jira）")
    ap.add_argument("--config", help="桥配置文件（默认 platform/bridge/bridge-config.json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("submit", help="提交本地工单为外部票")
    p.add_argument("--ticket", required=True, help="ticket-rN.md 路径")
    p.add_argument("--trace", help="trace JSONL（缺省自动按任务名在 logs/ 查找）")
    p.add_argument("--threshold", choices=["escalate", "pending_fix", "always"],
                   help="开票阈值（默认读配置，缺省 escalate）")
    p.add_argument("--provider", choices=["zentao", "jira"])
    p.add_argument("--base-url", help="覆盖配置的 base_url（联调/自测用）")
    p.add_argument("--dry-run", action="store_true", help="只打票面与调用意图，不发送")
    p.add_argument("--force", action="store_true", help="忽略防重复记录，强制重发")

    u = sub.add_parser("update", help="更新外部票状态")
    u.add_argument("--remote-id", required=True)
    u.add_argument("--status", required=True)
    u.add_argument("--comment")
    u.add_argument("--provider", choices=["zentao", "jira"])
    u.add_argument("--base-url")

    c = sub.add_parser("close", help="关闭外部票并回写 state")
    c.add_argument("--remote-id", required=True)
    c.add_argument("--comment")
    c.add_argument("--provider", choices=["zentao", "jira"])
    c.add_argument("--base-url")

    sub.add_parser("status", help="查看已提交票的台账")

    args = ap.parse_args()
    try:
        cfg = load_bridge_config(args.config)
        return {"submit": cmd_submit, "update": cmd_update,
                "close": cmd_close, "status": cmd_status}[args.cmd](args, cfg)
    except BridgeError as e:
        print(f"[桥错误] {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
