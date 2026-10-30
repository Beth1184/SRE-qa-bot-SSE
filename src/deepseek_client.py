from __future__ import annotations
from typing import Generator, Optional
from dataclasses import dataclass
from .config import DeepSeekConfig
from openai import OpenAI
import time

SRE_SYSTEM_PROMPT = (
    "你是一名专业的 SRE（Site Reliability Engineering）运维助手，"
    "擅长故障排查、监控告警、发布流程、容量规划等运维领域知识。\n"
    "回答要求：\n"
    "1. 简洁准确，直接给结论，不要冗长铺垫；\n"
    "2. 涉及操作步骤时，用有序列表分步说明；\n"
    "3. 涉及命令时，给出可复制执行的命令并说明关键参数；\n"
    "4. 不确定的内容要明确说明，不要编造。"
)

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
        self._request_timestamps: list[float] = []

    def _check_rate_limit(self) -> None:
        """滑动窗口限流检查"""
        now = time.time()
        window_start = now - 60
        self._request_timestamps = [ts for ts in self._request_timestamps if ts > window_start]

        if len(self._request_timestamps) >= self._config.rate_limit_rpm:
            sleep_time = 60 - (now - self._request_timestamps[0]) + 0.1
            time.sleep(sleep_time)

        self._request_timestamps.append(time.time())


    def build_sre_messages(self,question:str, history: list[dict] |None = None) -> list[dict]:
        # 提示词 = SRE 系统提示词 + 历史对话 + 当前问题
        messages: list[dict] = [{"role": "system", "content":
  SRE_SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user","content": question})
        return messages
    

    def chat(self, messages: list[dict], temperature: float) -> tuple[str, LLMCallMetrics]:
        """同步聊天请求"""
        # 闸门放在请求前，超了就sleep等着
        self._check_rate_limit()
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
        self._check_rate_limit()
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