"""feishu 适配器:从飞书云文档(docx)读取需求 Spec。

设计要点:
  - 运行时**直连飞书开放 API**(app_id/app_secret 换 tenant_access_token → 读 docx 正文),
    不依赖 lark-mcp(MCP 是 agent 用的,独立进程用不了)。
  - 需求池清单在 feishu_docs.json(非机密:只有文档 token/标题/可选 case 提示)。
  - **回写限制**:docx 无法像多维表格那样改字段,故状态回写落到本地 feishu_state.json;
    等转多维表格(Bitable)时,report() 换成 record 更新即可真正写回飞书。

凭证从环境变量读(仓库根 .env,已 gitignore):FEISHU_APP_ID / FEISHU_APP_SECRET。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from .base import Adapter, Task, apply_report
except ImportError:
    from base import Adapter, Task, apply_report  # type: ignore[no-redef]

_KNOWN = {"id", "title", "source", "status", "priority", "case", "spec_text"}


class FeishuAdapter(Adapter):
    name = "feishu"

    def __init__(self, docs_file: str, state_file: str):
        self.docs_file = docs_file
        self.state_file = state_file
        self.base = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/")
        self.app_id = os.environ.get("FEISHU_APP_ID")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET")
        self._token: str | None = None

    # ---- 飞书开放 API ----
    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        return self._send(req)

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(
            f"{self.base}{path}",
            headers={"Authorization": f"Bearer {self._ensure_token()}"},
        )
        return self._send(req)

    @staticmethod
    def _send(req: urllib.request.Request) -> dict:
        """发送请求;4xx/5xx 时也解析飞书返回的 JSON 错误体(含 code/msg/权限提示),
        而不是扒下一个笼统的「HTTP Error 400」。
        传输层故障(握手/连接/读取超时、DNS 等 URLError)会重试最多 3 次,
        避免偶发网络抖动直接毁掉整个交付;业务错误(HTTPError 已返回 JSON)不重试。"""
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {"code": e.code, "msg": f"HTTP {e.code}: {body[:300]}"}
            except urllib.error.URLError as e:  # 握手/超时/DNS 等传输层故障→退避重试
                last_err = e
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise last_err  # type: ignore[misc]

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        if not self.app_id or not self.app_secret:
            raise SystemExit("[feishu] 缺少 FEISHU_APP_ID / FEISHU_APP_SECRET(请在仓库根 .env 配置)")
        res = self._post("/open-apis/auth/v3/tenant_access_token/internal",
                         {"app_id": self.app_id, "app_secret": self.app_secret})
        if res.get("code") != 0:
            raise SystemExit(f"[feishu] 获取 tenant_access_token 失败:{res}")
        token = str(res["tenant_access_token"])
        self._token = token
        return token

    def _doc_raw_content(self, document_id: str) -> str:
        """读取 docx 文档纯文本正文。document_id 取自文档 URL 的 /docx/<id>。"""
        res = self._get(f"/open-apis/docx/v1/documents/{document_id}/raw_content?lang=0")
        if res.get("code") != 0:
            raise RuntimeError(f"读取文档 {document_id} 失败:{res}")
        return res.get("data", {}).get("content", "")

    def _wiki_obj_token(self, node_token: str) -> str:
        """把知识库 Wiki 节点(/wiki/<token>)解析为底层 docx 文档 id。"""
        res = self._get(f"/open-apis/wiki/v2/spaces/get_node?token={node_token}")
        if res.get("code") != 0:
            raise RuntimeError(f"解析 Wiki 节点 {node_token} 失败:{res}")
        node = res.get("data", {}).get("node", {})
        if node.get("obj_type") != "docx":
            raise RuntimeError(f"Wiki 节点 {node_token} 底层类型为 {node.get('obj_type')},暂只支持 docx")
        return node["obj_token"]

    def _resolve_content(self, entry: dict) -> str:
        """取需求正文:优先直接文本 spec_text;其次飞书链接(doc_token/wiki_token)运行时拉取。"""
        if entry.get("spec_text"):
            return entry["spec_text"]
        if entry.get("wiki_token"):
            return self._doc_raw_content(self._wiki_obj_token(entry["wiki_token"]))
        if entry.get("doc_token"):
            return self._doc_raw_content(entry["doc_token"])
        raise RuntimeError("需求条目缺少 spec_text、doc_token 或 wiki_token")

    # ---- 本地状态(docx 无法回写字段,状态落本地) ----
    def _read_state(self) -> dict[str, dict]:
        if not os.path.exists(self.state_file):
            return {}
        with open(self.state_file, encoding="utf-8") as f:
            return json.load(f)

    def _write_state(self, state: dict[str, dict]) -> None:
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    # ---- 契约实现 ----
    def list_pending(self) -> list[Task]:
        if not os.path.exists(self.docs_file):
            raise SystemExit(f"[feishu] 未找到需求清单 {self.docs_file}")
        with open(self.docs_file, encoding="utf-8") as f:
            cfg = json.load(f)
        state = self._read_state()

        tasks: list[Task] = []
        for d in cfg.get("docs", []):
            tid = str(d["id"])
            if state.get(tid, {}).get("status") in ("done", "fetched"):
                continue  # 已处理,跳过(去重)
            title = d.get("title", tid)
            case = d.get("case")
            priority = int(d.get("priority", 99))
            extra: dict[str, Any] = {k: v for k, v in d.items() if k not in _KNOWN | {"doc_token", "wiki_token"}}
            extra["doc_token"] = d.get("doc_token")
            extra["wiki_token"] = d.get("wiki_token")
            try:
                spec_text = self._resolve_content(d)
            except Exception as e:  # 拉取失败:仍入队,由 orchestrator 标 failed
                extra["fetch_error"] = str(e)
                spec_text = None
            tasks.append(Task(id=tid, title=title, source="feishu", status="pending",
                              priority=priority, case=case, spec_text=spec_text, extra=extra))
        tasks.sort(key=lambda t: t.priority)
        return tasks

    def report(self, task_id: str, status: str, **fields: Any) -> None:
        state = self._read_state()
        rec = state.get(str(task_id), {})
        apply_report(rec, status, fields)
        state[str(task_id)] = rec
        self._write_state(state)
