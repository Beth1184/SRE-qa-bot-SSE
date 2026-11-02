"""入口：飞书长连接模式（WebSocket）

长连接模式无需公网地址、无需配置回调 URL，适合本地开发调试。
飞书通过 WebSocket 长连接推送事件，本入口注册消息事件处理器后常驻运行。

运行：python -m src.start_lark
"""
import logging
from concurrent.futures import ThreadPoolExecutor

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.ws import Client as WsClient

from .config import lark_cfg
from .lark_bot import LarkBot

logger = logging.getLogger(__name__)

# 问答处理是同步阻塞的（内部有 time.sleep 限流），
# 用线程池执行，避免阻塞飞书 SDK 的事件接收循环。
executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="qa")

# 全局机器人实例（单例，进程生命周期内复用）
bot = LarkBot()


def do_message_receive(data: P2ImMessageReceiveV1) -> None:
    """im.message.receive_v1 事件回调：快速提交到线程池后立即返回"""
    executor.submit(bot.handle_message_event, data)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # 注册事件处理器（builder 参数顺序：encrypt_key, verification_token）
    event_handler = (
        lark.EventDispatcherHandler.builder(lark_cfg.encrypt_key, lark_cfg.verification_token)
        .register_p2_im_message_receive_v1(do_message_receive)
        .build()
    )

    # 构建长连接客户端（lark-oapi 1.7.x 无 builder，直接用构造函数）
    ws_client = WsClient(
        app_id=lark_cfg.app_id,
        app_secret=lark_cfg.app_secret,
        event_handler=event_handler,
    )

    logger.info("启动飞书长连接，等待消息事件...")
    ws_client.start()  # 阻塞常驻


if __name__ == "__main__":
    main()
