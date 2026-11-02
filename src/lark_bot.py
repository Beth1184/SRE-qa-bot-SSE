"""飞书交互层（应用层）：接收消息事件、编排问答流程、流式更新卡片。

本模块是项目的编排核心，把 DeepSeekClient（模型接入层）和
SessionManager（会话管理层）组合起来，实现完整问答链路：

    事件 → 占位卡片 → SSE 流式 → PATCH 更新 → 最终卡片（含 token 统计）

降级链：占位卡片失败 → 同步模式；同步也失败 → 纯文本报错。

注意：本模块的方法是同步阻塞的（底层限流用 time.sleep），
入口层（main.py / start_lark.py）需把它们放到线程池/后台线程执行。
"""

import json
import logging
import re
import time

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    PatchMessageRequest,
    PatchMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from .config import LarkConfig, deepseek_cfg, lark_cfg, sse_cfg
from .deepseek_client import DeepSeekClient, LLMCallMetrics
from .session_manager import Session, SessionManager

logger = logging.getLogger(__name__)


class LarkBot:
    """飞书 SRE 运维问答机器人（SSE 流式版）"""

    def __init__(self) -> None:
        # 飞书客户端
        self._lark_client = self._build_lark_client(lark_cfg)
        # 模型接入层
        self._deepseek_client = DeepSeekClient(deepseek_cfg)
        # 会话管理层
        self._session_manager = SessionManager()
        # 卡片更新间隔（毫秒 → 秒）
        self._update_interval = sse_cfg.card_update_interval_ms / 1000.0
        # 模型参数
        self._model = deepseek_cfg.model
        self._temperature = deepseek_cfg.temperature

    # ------------------------------------------------------------------
    # 初始化 / 客户端
    # ------------------------------------------------------------------
    def _build_lark_client(self, cfg: LarkConfig) -> lark.Client:
        """构建飞书 SDK 客户端"""
        builder = (
            lark.Client.builder()
            .app_id(cfg.app_id)
            .app_secret(cfg.app_secret)
        )
        if cfg.verification_token:
            builder = builder.verification_token(cfg.verification_token)
        if cfg.encrypt_key:
            builder = builder.encrypt_key(cfg.encrypt_key)
        return builder.build()

    # ------------------------------------------------------------------
    # 卡片构建
    # ------------------------------------------------------------------
    def _build_streaming_card(self, content: str, is_streaming: bool) -> dict:
        """构建「占位 / 流式」卡片（浅蓝色标题）"""
        if not content:
            title = "⏳ 正在思考中..."
            body = "正在连接 AI 服务，请稍候..."
        else:
            title = "💬 SRE 运维助手"
            body = content

        elements = [{"tag": "markdown", "content": body}]
        if is_streaming and content:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": "⏳ 流式输出中..."}],
            })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "wathet",  # 浅蓝
            },
            "elements": elements,
        }

    def _build_final_card(self, content: str, metrics: LLMCallMetrics | None, elapsed_ms: int) -> dict:
        """构建「最终」卡片（蓝色标题，含 token 统计）"""
        if metrics is not None:
            stats = (
                f"模型: {self._model} | 耗时: {elapsed_ms}ms | "
                f"输入: {metrics.prompt_tokens} tokens | "
                f"输出: {metrics.completion_tokens} tokens"
            )
        else:
            stats = f"模型: {self._model} | 耗时: {elapsed_ms}ms"

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💬 SRE 运维助手"},
                "template": "blue",  # 蓝色
            },
            "elements": [
                {"tag": "markdown", "content": content},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": stats}]},
            ],
        }

    # ------------------------------------------------------------------
    # 飞书消息发送 / 更新
    # ------------------------------------------------------------------
    def _send_placeholder_card(self, chat_id: str, msg_id: str) -> str | None:
        """发送占位卡片，成功返回新消息 ID，失败返回 None"""
        card = self._build_streaming_card("", is_streaming=False)
        request = (
            ReplyMessageRequest.builder()
            .message_id(msg_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps(card))
                .msg_type("interactive")
                .build()
            )
            .build()
        )
        try:
            response = self._lark_client.im.v1.message.reply(request)
            if response.success() and response.data:
                return response.data.message_id
            logger.error("发送占位卡片失败: code=%s msg=%s", response.code, response.msg)
        except Exception as e:
            logger.exception("发送占位卡片异常: %s", e)
        return None

    def _patch_card(self, message_id: str, card: dict) -> bool:
        """底层封装：PATCH 原地更新已发送的卡片"""
        request = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(PatchMessageRequestBody.builder().content(json.dumps(card)).build())
            .build()
        )
        try:
            response = self._lark_client.im.v1.message.patch(request)
            if not response.success():
                logger.error("更新卡片失败: code=%s msg=%s", response.code, response.msg)
            return response.success()
        except Exception as e:
            logger.exception("更新卡片异常: %s", e)
            return False

    def _update_card_streaming(self, message_id: str, text: str) -> None:
        """流式中更新卡片（部分内容）"""
        if not message_id:
            return
        self._patch_card(message_id, self._build_streaming_card(text, is_streaming=True))

    def _update_card_final(self, message_id: str, text: str, metrics: LLMCallMetrics | None, elapsed_ms: int) -> None:
        """最终更新卡片（完整内容 + token 统计）"""
        if not message_id:
            return
        self._patch_card(message_id, self._build_final_card(text, metrics, elapsed_ms))

    def _reply_card_with_metrics(self, chat_id: str, msg_id: str, answer: str, metrics: LLMCallMetrics, elapsed_ms: int) -> None:
        """降级路径：直接回复一张最终卡片（无占位卡片）"""
        card = self._build_final_card(answer, metrics, elapsed_ms)
        request = (
            ReplyMessageRequest.builder()
            .message_id(msg_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps(card))
                .msg_type("interactive")
                .build()
            )
            .build()
        )
        try:
            response = self._lark_client.im.v1.message.reply(request)
            if not response.success():
                logger.error("回复卡片失败: code=%s msg=%s", response.code, response.msg)
                self._reply_text(chat_id, msg_id, answer)
        except Exception as e:
            logger.exception("回复卡片异常: %s", e)
            self._reply_text(chat_id, msg_id, answer)

    def _reply_text(self, chat_id: str, msg_id: str, text: str) -> None:
        """最终降级：回复纯文本"""
        request = (
            ReplyMessageRequest.builder()
            .message_id(msg_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps({"text": text}))
                .msg_type("text")
                .build()
            )
            .build()
        )
        try:
            response = self._lark_client.im.v1.message.reply(request)
            if not response.success():
                logger.error("回复文本失败: code=%s msg=%s", response.code, response.msg)
        except Exception as e:
            logger.exception("回复文本异常: %s", e)

    # ------------------------------------------------------------------
    # 问答编排
    # ------------------------------------------------------------------
    def _process_qa_stream(self, chat_id: str, msg_id: str, user_id: str, question: str) -> None:
        """主流程：占位卡片 → SSE 流式 → 最终卡片"""
        session = self._session_manager.get_or_create(user_id)

        # 1. 发送占位卡片
        placeholder_msg_id = self._send_placeholder_card(chat_id, msg_id)
        if placeholder_msg_id is None:
            logger.warning("占位卡片发送失败，降级为同步模式")
            self._fallback_sync(chat_id, msg_id, user_id, question, session)
            return

        # 2. 组装消息（系统提示词 + 历史 + 当前问题）
        messages = self._deepseek_client.build_sre_messages(question, session.get_history())

        # 3. 流式处理
        accumulated_text = ""
        last_update_time = 0.0
        start_time = time.time()
        metrics: LLMCallMetrics | None = None

        try:
            for chunk in self._deepseek_client.chat_stream(messages, self._temperature):
                if chunk.content:
                    accumulated_text += chunk.content

                # 限频更新卡片（每 _update_interval 秒一次）
                now = time.time()
                if now - last_update_time >= self._update_interval:
                    self._update_card_streaming(placeholder_msg_id, accumulated_text)
                    last_update_time = now

                if chunk.usage is not None:
                    metrics = chunk.usage
        except Exception as e:
            logger.exception("SSE 流式调用失败: %s", e)
            if accumulated_text:
                # 已有部分内容：保存并展示部分回答
                session.add_message("user", question)
                session.add_message("assistant", accumulated_text)
                elapsed_ms = int((time.time() - start_time) * 1000)
                self._update_card_final(
                    placeholder_msg_id,
                    accumulated_text + "\n\n⚠️ 流式输出中断，以上为部分回答",
                    metrics,
                    elapsed_ms,
                )
            else:
                # 没有任何内容：降级同步
                self._fallback_sync(chat_id, msg_id, user_id, question, session)
            return

        # 4. 保存对话历史
        session.add_message("user", question)
        session.add_message("assistant", accumulated_text)

        # 5. 最终更新卡片
        elapsed_ms = int((time.time() - start_time) * 1000)
        self._update_card_final(placeholder_msg_id, accumulated_text, metrics, elapsed_ms)

    def _fallback_sync(self, chat_id: str, msg_id: str, user_id: str, question: str, session: Session) -> None:
        """降级：同步模式一次性返回完整回答"""
        messages = self._deepseek_client.build_sre_messages(question, session.get_history())
        start_time = time.time()
        try:
            answer, metrics = self._deepseek_client.chat(messages, self._temperature)
            session.add_message("user", question)
            session.add_message("assistant", answer)
            elapsed_ms = int((time.time() - start_time) * 1000)
            self._reply_card_with_metrics(chat_id, msg_id, answer, metrics, elapsed_ms)
        except Exception as e:
            logger.exception("同步调用失败: %s", e)
            self._reply_text(chat_id, msg_id, f"⚠️ AI 服务不可用：{str(e)[:200]}")

    # ------------------------------------------------------------------
    # 事件入口
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_question(content: str) -> str:
        """从消息 content（JSON 字符串）解析问题文本，去掉 @mention"""
        try:
            data = json.loads(content)
            text = data.get("text", "")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return ""
        # 去掉开头的 @xxx 提及（飞书 mention 形如 "@_user_1"）
        return re.sub(r"^(@[^\s]+\s*)+", "", text).strip()

    def handle_message_event(self, event: P2ImMessageReceiveV1) -> None:
        """处理飞书消息事件（im.message.receive_v1）

        入口层（main.py / start_lark.py）在 SDK 事件回调里调用此方法。
        本方法内部是同步阻塞调用，入口层需放到线程池/后台线程执行。
        """
        data = event.event
        sender = data.sender
        message = data.message

        sender_id = sender.sender_id if sender else None
        user_id = sender_id.open_id if sender_id else ""
        message_id = message.message_id or ""
        chat_id = message.chat_id or ""
        msg_type = message.message_type or ""

        # 只处理文本消息
        if msg_type != "text":
            logger.info("忽略非文本消息: type=%s", msg_type)
            return

        question = self._extract_question(message.content or "{}")
        if not question:
            logger.info("未解析出有效问题，跳过")
            return

        logger.info("收到提问: user=%s chat=%s question=%s", user_id, chat_id, question[:50])
        self._process_qa_stream(chat_id, message_id, user_id, question)
