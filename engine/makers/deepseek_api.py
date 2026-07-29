"""DeepSeek API Maker。"""

from __future__ import annotations

import json
import os
import re
import urllib.request

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


@register("deepseek")
class DeepSeekMaker(Maker):
    name = "deepseek"
    type = "api"

    def __init__(self, **kwargs):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
        self.temperature = float(os.environ.get("HARNESS_TEMPERATURE", "0"))

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
            with urllib.request.urlopen(req, timeout=180) as r:
                body = json.loads(r.read())
            text = body["choices"][0]["message"]["content"]
        except Exception as e:
            return MakerResult(success=False, error=str(e),
                             model=self.model, raw_output="")

        # 保存原始输出供调试
        os.makedirs(workdir, exist_ok=True)
        with open(os.path.join(workdir, "_llm_raw.txt"), "w", encoding="utf-8") as f:
            f.write(text)

        # 解析 FILE 标记 → 写入文件
        files = {}
        for rel, content in FILE_RE.findall(text):
            rel = rel.strip()
            # 文件名超长 → 跳过（LLM 输出格式异常）
            if len(rel) > 200:
                print(f"  ⚠ 跳过异常文件名 ({len(rel)} 字符): {rel[:80]}...")
                continue
            # 路径截断
            safe_rel = rel.split("\n")[0].strip()
            if safe_rel != rel:
                print(f"  ⚠ 文件名含换行，已截断: {safe_rel}")
            path = os.path.join(workdir, safe_rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            files[safe_rel] = content

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
                path = os.path.join(workdir, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
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

        # 保存 prompt 到产物目录供调试
        with open(os.path.join(workdir, "_prompt.txt"), "w", encoding="utf-8") as f:
            f.write(prompt)

        return MakerResult(success=True, files=files, output_dir=workdir,
                          model=self.model, raw_output=text[:2000],
                          cost_estimate_yuan=round(cost, 6))
