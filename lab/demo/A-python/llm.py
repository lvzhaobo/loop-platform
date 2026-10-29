"""模型接入层：真实 DeepSeek / 离线 Mock，同一套接口。"""
import json, time, urllib.request
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent
SOLUTION = DEMO / "shared" / "solution"
DEFAULT_SCRIPT = DEMO / "shared" / "mock" / "pomodoro.json"

SYSTEM = """你是一个在受控工作区里干活的编程 agent。

规则：
1. 先看：list_files 看结构，read_file 读相关文件。
2. 再改：用 write_file 覆盖写入，一次只改必要的文件。
3. 最后验证：调用 run_check 跑门禁。退出码为 0 才算完成。
4. 门禁红了就根据输出继续修，最多修两次；两次还不行就停下来说明原因。
5. 不要试图修改 check.py，也不要运行白名单以外的命令。

门禁的输出是你的唯一验收标准，它比你自己的判断可靠。"""


class LLM:
    """真实模型：DeepSeek（OpenAI 兼容接口）。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.mock = cfg["bool"]("MOCK")

    def chat(self, messages, tools):
        if self.mock:
            return MockModel(self.cfg.get("MOCK_SCRIPT")).reply(messages)
        key = self.cfg.get("DEEPSEEK_API_KEY", "")
        if not key or key.startswith("sk-在这里"):
            raise RuntimeError("没配 DEEPSEEK_API_KEY —— 去 demo/config.env 填，或设 MOCK=true")
        url = self.cfg["DEEPSEEK_BASE_URL"].rstrip("/") + "/chat/completions"
        payload = {
            "model": self.cfg["DEEPSEEK_MODEL"],
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read().decode("utf-8"))
        return body["choices"][0]["message"]


    def chat_stream(self, messages):
        """流式版：逐个吐 token。mock 模式按字符模拟，方便前端演示。"""
        if self.mock:
            text = MockModel(self.cfg.get("MOCK_SCRIPT")).stream_text()
            for i in range(0, len(text), 12):
                yield text[i:i+12]
                time.sleep(0.01)
            return

        key = self.cfg.get("DEEPSEEK_API_KEY", "")
        if not key or key.startswith("sk-在这里"):
            raise RuntimeError("没配 DEEPSEEK_API_KEY")

        url = self.cfg["DEEPSEEK_BASE_URL"].rstrip("/") + "/chat/completions"
        payload = {"model": self.cfg["DEEPSEEK_MODEL"], "messages": messages,
                   "stream": True, "temperature": 0.4}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                ch = obj.get("choices") or [{}]
                delta = (ch[0].get("delta") or {}).get("content")
                if delta:
                    yield delta


class MockModel:
    """离线脚本模型：按 shared/mock/*.json 的剧本演示一轮完整流程。

    step 里的 "from" 表示"把那个文件的全文作为 content"，
    这样剧本可以和数据分开，换任务只换 json。
    """

    def __init__(self, script_path=None):
        path = Path(script_path) if script_path else DEFAULT_SCRIPT
        self.steps = json.loads(path.read_text(encoding="utf-8"))

    def stream_text(self):
        """mock 流式：拿剧本里最后一句 final，或者一段占位文本"""
        for step in self.steps:
            if "final" in step:
                return step["final"] * 8
        return "（mock 流式输出）" * 20

    def reply(self, messages):
        n = sum(1 for m in messages if m.get("role") == "assistant")
        if n >= len(self.steps):
            return {"role": "assistant", "content": "门禁已绿，任务完成。"}

        step = self.steps[n]
        if "final" in step:
            return {"role": "assistant", "content": step["final"]}

        args = dict(step.get("args") or {})
        if "from" in args:
            args["content"] = (DEMO / args.pop("from")).read_text(encoding="utf-8")
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"mock_{n}", "type": "function",
            "function": {"name": step["name"],
                         "arguments": json.dumps(args, ensure_ascii=False)},
        }]}
