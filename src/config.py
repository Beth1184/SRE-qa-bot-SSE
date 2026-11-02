# config.py
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# 加载项目根目录 .env 文件，放在最前面
# override=True：强制 .env 覆盖系统环境变量，避免终端里残留的旧值干扰
load_dotenv(override=True)

@dataclass
class DeepSeekConfig:
    """DeepSeek API 配置"""
    api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")))
    temperature: float = field(default_factory=lambda: float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3")))
    rate_limit_rpm: int = field(default_factory=lambda:int(os.getenv("DEEPSEEK_RATE_RPM","60")))

@dataclass
class SSEConfig:
    """SSE 流式卡片配置"""
    card_update_interval_ms: int = field(
        default_factory=lambda: int(os.getenv("SSE_CARD_UPDATE_INTERVAL_MS", "800"))
    )


@dataclass
class LarkConfig:
    """飞书应用配置"""
    app_id: str = field(default_factory=lambda: os.getenv("LARK_APP_ID", ""))
    app_secret: str = field(default_factory=lambda: os.getenv("LARK_APP_SECRET", ""))
    verification_token: str = field(default_factory=lambda: os.getenv("LARK_VERIFICATION_TOKEN", ""))
    encrypt_key: str = field(default_factory=lambda: os.getenv("LARK_ENCRYPT_KEY", ""))


# 全局单例，项目别的地方直接 import
deepseek_cfg = DeepSeekConfig()
sse_cfg = SSEConfig()
lark_cfg = LarkConfig()