from src.logger import logger
from src.config import global_config
import time
import asyncio

from . import MetaEventType


class MetaEventHandler:
    """
    处理Meta事件
    """

    def __init__(self):
        self.interval = 30  # 默认心跳间隔
        self._interval_checking = False
        self.last_heart_beat = time.time()

    async def handle_meta_event(self, message: dict) -> None:
        # 从 Milky 事件中提取元事件数据
        event_data = message.get("data", {})
        event_type = message.get("event_type")
        
        if event_type == "bot_offline":
            # 处理机器人离线事件
            self_id = event_data.get("self_id")
            reason = event_data.get("reason", "未知原因")
            logger.warning(f"Bot {self_id} 离线，原因: {reason}")
            # 可以在这里添加重连逻辑
        else:
            # 其他事件类型，更新心跳时间
            self.last_heart_beat = time.time()
            if not self._interval_checking:
                asyncio.create_task(self.check_heartbeat())

    async def check_heartbeat(self) -> None:
        """检查心跳状态"""
        self._interval_checking = True
        while True:
            now_time = time.time()
            if now_time - self.last_heart_beat > self.interval * 2:
                logger.error("Bot 可能发生了连接断开，被下线，或者 Milky 端卡死！")
                break
            else:
                logger.debug("心跳正常")
            await asyncio.sleep(self.interval)


meta_event_handler = MetaEventHandler()
