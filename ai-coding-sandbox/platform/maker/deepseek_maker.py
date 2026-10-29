#!/usr/bin/env python3
"""DeepSeekMaker：OpenAI 兼容接口的临时生成端适配器。

定位：与 BedrockMaker 同接口，用于先跑通闭环；稳定后切回 Bedrock。
凭据：环境变量 DEEPSEEK_API_KEY。
"""

from __future__ import annotations

import os
from typing import Any


class DeepSeekMaker:
    def __init__(
        self,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, spec: str, constraints: str) -> tuple[str, dict]:
        import requests  # type: ignore

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "缺少 DEEPSEEK_API_KEY：export DEEPSEEK_API_KEY=..."
            )
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": constraints},
                    {"role": "user", "content": spec},
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {}) or {}
        return text, usage
