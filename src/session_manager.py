import time
from collections import OrderedDict

MAX_MESSAGES_PER_SESSION = 20     # 每会话最多保留 20 条消息（10 轮对话）
SESSION_TIMEOUT_SECONDS = 3600    # 无活动 1 小时自动过期
MAX_SESSIONS = 1000               # 最大并发会话数，超出 LRU 淘汰


class Session:
    """单个用户会话：消息历史 + 最后活动时间"""
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.messages: list[dict] = []
        self.last_active = time.time()

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.last_active = time.time()

        if len(self.messages) > MAX_MESSAGES_PER_SESSION:
            self.messages = self.messages[-MAX_MESSAGES_PER_SESSION:]

    def get_history(self) -> list[dict]:
        return self.messages

    def is_expired(self, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        return (now - self.last_active) > SESSION_TIMEOUT_SECONDS

        

class SessionManager:
    """会话管理器：用户隔离 + 自动过期 + LRU 淘汰"""

    def __init__(self) -> None:
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    def get_or_create(self, user_id: str) -> Session:
        session = self._sessions.get(user_id)
        if session is None:
            return self._create(user_id)
        # 已有会话但过期了 → 当作不存在，重建
        if session.is_expired():
            del self._sessions[user_id]
            return self._create(user_id)
        # 未过期 → 移到末尾（标记为「最近使用」）
        self._sessions.move_to_end(user_id)
        return session

    def _create(self, user_id: str) -> Session:
        # 容量满 → 淘汰最久未使用（OrderedDict 头部 = 最旧）
        if len(self._sessions) >= MAX_SESSIONS:
            self._sessions.popitem(last=False)
        session = Session(user_id)
        self._sessions[user_id] = session
        return session

    def get_history(self, user_id: str) -> list[dict]:
        session = self._sessions.get(user_id)
        return session.get_history() if session else []

    def clear(self, user_id: str) -> None:
        """清除某用户会话（供后续 /history、/reset 命令用）"""
        self._sessions.pop(user_id, None)
