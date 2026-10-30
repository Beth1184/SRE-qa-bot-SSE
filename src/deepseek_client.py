from __future__ import annotations
from typing import Generator, Optional
from dataclasses import dataclass
from .config import DeepSeekConfig
from openai import OpenAI

@dataclass
class StreamChunk:
    content: str
    finish_reason: str | None
    usage: Optional[LLMCallMetrics] = None


@dataclass
class LLMCallMetrics:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class DeepSeekClient:
    """DeepSeek API 客户端，支持同步调用和 SSE流式调用"""
    config: DeepSeekConfig

    def __post_init__(self):
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )

    def chat(self, messages: list[dict], temperature: float) -> tuple[str, LLMCallMetrics]:
        """同步聊天请求"""
        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            stream=False
        )

        if not response.choices or response.usage is None:
            return "", LLMCallMetrics(0, 0, 0)

        content = response.choices[0].message.content or ""
        usage = response.usage

        metrics = LLMCallMetrics(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens
        )
        return content, metrics

    def chat_stream(self, messages: list[dict], temperature: float) -> Generator[StreamChunk, None, None]:
        """SSE 流式聊天请求"""
        stream = self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        for chunk in stream:
            content = ""
            finish_reason = None
            metrics: Optional[LLMCallMetrics] = None

            if chunk.choices:
                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason
                content = delta.content or ""

            # 把SDK原生usage转成我们自己的LLMCallMetrics，统一类型
            if chunk.usage is not None:
                metrics = LLMCallMetrics(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens
                )

            yield StreamChunk(
                content=content,
                finish_reason=finish_reason,
                usage=metrics
            )