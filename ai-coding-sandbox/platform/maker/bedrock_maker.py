#!/usr/bin/env python3
"""BedrockMaker：Loop Platform 的 AWS Bedrock 生成端适配器。

定位：
  Loop 是 Maker-agnostic。本文件只做一件事——把「单元规格 + Harness 约束」
  交给 Amazon Bedrock Converse API，取回生成文本与用量。
  判定 / 门禁不在这里，在 checker 与 Loop 流程层。

用法（示例）：
  from maker.bedrock_maker import BedrockMaker
  m = BedrockMaker(region_name="us-west-2", model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0")
  code, usage = m.generate(spec, constraints)
"""

from __future__ import annotations

from typing import Any


class BedrockMaker:
    """通过 boto3 bedrock-runtime.converse 生成代码候选。"""

    def __init__(
        self,
        region_name: str,
        model_id: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        self.region_name = region_name
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import boto3  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "缺少 boto3：pip install boto3"
                ) from exc
            session = boto3.Session(region_name=self.region_name)
            self._client = session.client(
                "bedrock-runtime", region_name=self.region_name
            )
        return self._client

    def generate(self, spec: str, constraints: str) -> tuple[str, dict]:
        """返回 (代码文本, usage 字典)。usage 可能为空。"""
        resp = self.client.converse(
            modelId=self.model_id,
            system=[{"text": constraints}],
            messages=[{"role": "user", "content": [{"text": spec}]}],
            inferenceConfig={
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        )
        content = resp.get("output", {}).get("message", {}).get("content", [])
        text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
        usage = resp.get("usage", {}) or {}
        return text, usage
