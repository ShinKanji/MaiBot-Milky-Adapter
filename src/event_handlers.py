"""
Milky 事件处理器模块
包含所有事件类型的处理逻辑
"""

import asyncio
from typing import Dict, Any
from .logger import logger
from .milky_com_layer import milky_com


class EventHandlers:
    """Milky 事件处理器集合"""
    
    def __init__(self):
        self.message_queue = None
        
    def set_message_queue(self, message_queue):
        """设置消息队列"""
        self.message_queue = message_queue
        
    async def handle_message_event(self, event_data: dict):
        """处理消息接收事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "message",
                "data": event_data
            })

    async def handle_recall_event(self, event_data: dict):
        """处理消息撤回事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_friend_request_event(self, event_data: dict):
        """处理好友请求事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_join_request_event(self, event_data: dict):
        """处理入群请求事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_invited_join_request_event(self, event_data: dict):
        """处理群成员邀请他人入群请求事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_invitation_event(self, event_data: dict):
        """处理他人邀请自身入群事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_friend_nudge_event(self, event_data: dict):
        """处理好友戳一戳事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_nudge_event(self, event_data: dict):
        """处理群戳一戳事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_member_increase_event(self, event_data: dict):
        """处理群成员增加事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_member_decrease_event(self, event_data: dict):
        """处理群成员减少事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_admin_change_event(self, event_data: dict):
        """处理群管理员变更事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_mute_event(self, event_data: dict):
        """处理群禁言事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_group_whole_mute_event(self, event_data: dict):
        """处理群全体禁言事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "notice",
                "data": event_data
            })

    async def handle_bot_offline_event(self, event_data: dict):
        """处理机器人离线事件"""
        if self.message_queue:
            await self.message_queue.put({
                "post_type": "meta_event",
                "data": event_data
            })

    def register_all_handlers(self):
        """注册所有事件处理器"""
        handlers = {
            "message_receive": self.handle_message_event,
            "message_recall": self.handle_recall_event,
            "friend_request": self.handle_friend_request_event,
            "group_join_request": self.handle_group_join_request_event,
            "group_invited_join_request": self.handle_group_invited_join_request_event,
            "group_invitation": self.handle_group_invitation_event,
            "friend_nudge": self.handle_friend_nudge_event,
            "group_nudge": self.handle_group_nudge_event,
            "group_member_increase": self.handle_group_member_increase_event,
            "group_member_decrease": self.handle_group_member_decrease_event,
            "group_admin_change": self.handle_group_admin_change_event,
            "group_mute": self.handle_group_mute_event,
            "group_whole_mute": self.handle_group_whole_mute_event,
            "bot_offline": self.handle_bot_offline_event,
        }
        
        for event_type, handler in handlers.items():
            milky_com.register_event_handler(event_type, handler)
            logger.debug(f"注册事件处理器: {event_type}")
            
        logger.info("所有 Milky 事件处理器注册完成")


# 全局事件处理器实例
event_handlers = EventHandlers()


async def setup_event_handlers(message_queue):
    """设置事件处理器"""
    event_handlers.set_message_queue(message_queue)
    event_handlers.register_all_handlers()
