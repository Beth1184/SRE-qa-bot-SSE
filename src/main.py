"""入口：飞书 Webhook 模式（FastAPI）

Webhook 模式需要公网可访问的地址，飞书把事件 POST 到 /lark/event。
本地调试建议用长连接模式（start_lark.py），本文件用于有公网地址的部署场景。

运行：uvicorn src.main:app --host 0.0.0.0 --port 8000
"""
import logging
from concurrent.futures import ThreadPoolExecutor

import lark_oapi as lark
from fastapi import FastAPI, Request, Response
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.core.model.raw_request import RawRequest

from .config import lark_cfg
from .lark_bot import LarkBot

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="qa")
bot = LarkBot()


def _on_message(data: P2ImMessageReceiveV1) -> None:
    """im.message.receive_v1 事件回调：提交到线程池后立即返回"""
    executor.submit(bot.handle_message_event, data)


# 事件处理器：内部处理验签 / 解密 / 分发。
# 注意 builder 参数顺序是 (encrypt_key, verification_token)。
event_handler = (
    lark.EventDispatcherHandler.builder(
        lark_cfg.encrypt_key,
        lark_cfg.verification_token,
    )
    .register_p2_im_message_receive_v1(_on_message)
    .build()
)

app = FastAPI(title="SRE 运维问答机器人")


@app.post("/lark/event")
async def lark_event(request: Request) -> Response:
    """飞书事件回调入口"""
    body = await request.body()

    # do() 需要一个 RawRequest（body / uri / headers）
    req = RawRequest()
    req.body = body
    req.uri = str(request.url)
    req.headers = dict(request.headers)

    resp = event_handler.do(req)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type="application/json",
    )
