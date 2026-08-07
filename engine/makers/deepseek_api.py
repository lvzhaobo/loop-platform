"""DeepSeek API Maker。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import urllib.request

from engine.core.paths import load_config
from .base import Maker, MakerResult
from . import register

FILE_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<ENDFILE>>>", re.S)
# 兜底：LLM 未按协议输出时，尝试从 markdown 代码围栏中提取
CODE_FENCE_RE = re.compile(r"```(\w+)?\n(.*?)```", re.S)

_EXT_BY_LANG = {
    "html": "index.html", "htm": "index.html",
    "python": "app.py", "py": "app.py",
    "javascript": "app.js", "js": "app.js",
    "css": "style.css", "json": "data.json",
}


def _safe_output_path(workdir: str, relative: str) -> Path:
    if not relative or "\\" in relative or Path(relative).is_absolute():
        raise ValueError("模型输出包含非法文件路径")
    root = Path(workdir).resolve()
    target = (root / relative).resolve()
    if target == root or root not in target.parents:
        raise ValueError("模型输出路径越出制品目录")
    return target


@register("deepseek")
class DeepSeekMaker(Maker):
    name = "deepseek"
    type = "api"

    def __init__(self, timeout_seconds: int = 180, **kwargs):
        config = load_config()
        self.api_key = config.get("DEEPSEEK_API_KEY")
        self.base_url = config.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = config.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
        try:
            self.temperature = float(config.get("HARNESS_TEMPERATURE", "0"))
        except (TypeError, ValueError):
            self.temperature = 0.0
        self.timeout_seconds = int(timeout_seconds)

    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        if not self.api_key:
            return MakerResult(success=False, error="DEEPSEEK_API_KEY 未设置")

        # 构建消息
        messages = [{"role": "system", "content": prompt}]
        if feedback:
            messages.append({
                "role": "user",
                "content": f"上一轮验收失败，以下是失败日志。请只修复这些失败项，重新输出全部文件：\n\n{feedback[-3000:]}"
            })
        else:
            messages.append({"role": "user", "content": "请依据以上约束与规格，生成全部文件。"})

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as r:
                body = json.loads(r.read())
            text = body["choices"][0]["message"]["content"]
        except Exception as e:
            return MakerResult(success=False, error=str(e),
                             model=self.model, raw_output="")

        # 原始模型文本不落入制品目录，避免 Prompt/响应被后续交付或页面误暴露。
        os.makedirs(workdir, exist_ok=True)
        files = {}
        for rel, content in FILE_RE.findall(text):
            rel = rel.strip()
            if len(rel) > 200:
                continue
            try:
                path = _safe_output_path(workdir, rel)
            except ValueError:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            files[rel] = content

        if not files:
            # 兜底：提取 markdown 代码围栏（LLM 常见的违协议输出形态）
            fences = CODE_FENCE_RE.findall(text)
            used_names: set[str] = set()
            for lang, content in fences:
                lang = (lang or "").lower()
                # 代码围栏首行若是注释里的文件名提示则忽略，按语言推断文件名
                name = _EXT_BY_LANG.get(lang)
                if not name:
                    continue
                if name in used_names:
                    stem, dot, ext = name.partition(".")
                    name = f"{stem}_{len(used_names)}{dot}{ext}"
                used_names.add(name)
                try:
                    path = _safe_output_path(workdir, name)
                except ValueError:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                files[name] = content
            if files:
                print(f"  ⚠ 未找到 FILE 标记，已从代码围栏兜底提取 {len(files)} 个文件")

        if not files:
            return MakerResult(success=False, error="LLM 输出中未找到 FILE 标记",
                             model=self.model, raw_output=text[:500],
                             output_dir=workdir)

        # 估算成本
        cost = (len(prompt) / 4 / 1_000_000 * 1.0
                + len(text) / 4 / 1_000_000 * 2.0)

        return MakerResult(success=True, files=files, output_dir=workdir,
                          model=self.model, raw_output=text[:2000],
                          cost_estimate_yuan=round(cost, 6))
