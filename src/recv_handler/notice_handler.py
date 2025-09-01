import time
import json
import asyncio
from typing import Tuple, Optional

from src.logger import logger
from src.config import global_config
from src.database import BanUser, db_manager, is_identical
from . import NoticeType, ACCEPT_FORMAT
from .message_sending import message_send_instance
from .message_handler import message_handler
from maim_message import FormatInfo, UserInfo, GroupInfo, Seg, BaseMessageInfo, MessageBase, SenderInfo, ReceiverInfo

from src.utils import get_member_info

notice_queue: asyncio.Queue[MessageBase] = asyncio.Queue(maxsize=100)
unsuccessful_notice_queue: asyncio.Queue[MessageBase] = asyncio.Queue(maxsize=3)


class NoticeHandler:
    banned_list: list[BanUser] = []  # 当前仍在禁言中的用户列表
    lifted_list: list[BanUser] = []  # 已经自然解除禁言

    def __init__(self):
        pass

    def _create_sender_info(self, user_id: int, user_nickname: str, user_cardname: str, group_id: Optional[int] = None, group_name: str = "") -> SenderInfo:
        """
        创建发送者信息
        
        Args:
            user_id: 用户ID
            user_nickname: 用户昵称
            user_cardname: 用户群昵称
            group_id: 群ID（如果是群聊）
            group_name: 群名称（如果是群聊）
            
        Returns:
            SenderInfo: 发送者信息对象
        """
        # 创建用户信息
        user_info = UserInfo(
            platform=global_config.maibot_server.platform_name,
            user_id=str(user_id),
            user_nickname=user_nickname,
            user_cardname=user_cardname,
        )
        
        # 创建群组信息（如果是群聊）
        group_info = None
        if group_id:
            group_info = GroupInfo(
                platform=global_config.maibot_server.platform_name,
                group_id=str(group_id),
                group_name=group_name,
            )
        
        # 创建发送者信息
        return SenderInfo(
            user_info=user_info,
            group_info=group_info,
        )

    def _create_receiver_info(self, target_user_id: Optional[int] = None, target_user_nickname: str = "", 
                             group_id: Optional[int] = None, group_name: str = "", 
                             is_bot: bool = False) -> ReceiverInfo:
        """
        创建接收者信息
        
        Args:
            target_user_id: 目标用户ID（私聊时）
            target_user_nickname: 目标用户昵称
            group_id: 群ID（群聊时）
            group_name: 群名称（群聊时）
            is_bot: 是否是机器人
            
        Returns:
            ReceiverInfo: 接收者信息对象
        """
        # 创建用户信息（私聊时）
        user_info = None
        if target_user_id and not is_bot:
            user_info = UserInfo(
                platform=global_config.maibot_server.platform_name,
                user_id=str(target_user_id),
                user_nickname=target_user_nickname,
                user_cardname=target_user_nickname,
            )
        
        # 创建群组信息（群聊时）
        group_info = None
        if group_id:
            group_info = GroupInfo(
                platform=global_config.maibot_server.platform_name,
                group_id=str(group_id),
                group_name=group_name,
            )
        
        # 创建接收者信息
        return ReceiverInfo(
            user_info=user_info,
            group_info=group_info,
        )

    async def handle_notice(self, raw_message: dict) -> None:
        # 从 Milky 事件中提取通知数据
        event_data = raw_message.get("data", {})
        event_type = raw_message.get("event_type")
        
        # 根据 Milky 事件类型映射到通知类型
        notice_type = self._map_milky_event_to_notice(event_type, event_data)
        
        message_time: float = time.time()

        group_id = event_data.get("group_id")
        user_id = event_data.get("user_id") or event_data.get("initiator_id") or event_data.get("sender_id")
        target_id = event_data.get("target_user_id") or event_data.get("receiver_id")

        handled_message: Seg = None
        user_info: UserInfo = None
        system_notice: bool = False

        match notice_type:
            case NoticeType.friend_recall:
                logger.info("好友撤回一条消息")
                logger.info(f"撤回消息序列号：{event_data.get('message_seq')}, 撤回时间：{event_data.get('time')}")
                logger.warning("暂时不支持撤回消息处理")
            case NoticeType.group_recall:
                logger.info("群内用户撤回一条消息")
                logger.info(f"撤回消息序列号：{event_data.get('message_seq')}, 撤回时间：{event_data.get('time')}")
                logger.warning("暂时不支持撤回消息处理")
            case NoticeType.notify:
                sub_type = self._get_notify_sub_type(event_type, event_data)
                match sub_type:
                    case NoticeType.Notify.poke:
                        if global_config.chat.enable_poke and await message_handler.check_allow_to_chat(
                            user_id, group_id, False, False
                        ):
                            logger.info("处理戳一戳消息")
                            handled_message, user_info = await self.handle_poke_notify(event_data, group_id, user_id)
                        else:
                            logger.warning("戳一戳消息被禁用，取消戳一戳处理")
                    case _:
                        logger.warning(f"不支持的notify类型: {notice_type}.{sub_type}")
            case NoticeType.group_ban:
                sub_type = self._get_group_ban_sub_type(event_type, event_data)
                match sub_type:
                    case NoticeType.GroupBan.ban:
                        if not await message_handler.check_allow_to_chat(user_id, group_id, True, False):
                            return None
                        logger.info("处理群禁言")
                        handled_message, user_info = await self.handle_ban_notify(event_data, group_id)
                        system_notice = True
                    case NoticeType.GroupBan.lift_ban:
                        if not await message_handler.check_allow_to_chat(user_id, group_id, True, False):
                            return None
                        logger.info("处理解除群禁言")
                        handled_message, user_info = await self.handle_lift_ban_notify(event_data, group_id)
                        system_notice = True
                    case _:
                        logger.warning(f"不支持的group_ban类型: {notice_type}.{sub_type}")
            case _:
                logger.warning(f"不支持的notice类型: {notice_type}")
                return None
        if not handled_message or not user_info:
            logger.warning("notice处理失败或不支持")
            return None

        group_info: GroupInfo = None
        if group_id:
            # Milky 可能不提供群名称，使用默认值
            group_name = ""
            group_info = GroupInfo(
                platform=global_config.maibot_server.platform_name,
                group_id=group_id,
                group_name=group_name,
            )

        # 从user_info中获取用户信息
        user_nickname = user_info.user_nickname if user_info else f"用户{user_id}"
        user_cardname = user_info.user_cardname if user_info else f"用户{user_id}"
        
        # 创建发送者信息
        sender_info = self._create_sender_info(
            user_id=user_id,
            user_nickname=user_nickname,
            user_cardname=user_cardname,
            group_id=group_id,
            group_name=group_name,
        )
        
        # 创建接收者信息
        # 戳一戳事件的接收者是被戳的人
        target_nickname = f"用户{target_id}" if target_id else "未知目标"  # 使用用户ID作为默认昵称
        receiver_info = self._create_receiver_info(
            target_user_id=target_id,
            target_user_nickname=target_nickname,
            group_id=group_id,
            group_name=group_name,
            is_bot=False,
        )
        
        message_info: BaseMessageInfo = BaseMessageInfo(
            platform=global_config.maibot_server.platform_name,
            message_id="notice",
            time=message_time,
            user_info=user_info,
            group_info=group_info,
            template_info=None,
            format_info=FormatInfo(
                content_format=["text", "notify"],
                accept_format=ACCEPT_FORMAT,
            ),
            additional_config={"target_id": target_id},  # 在这里塞了一个target_id，方便mmc那边知道被戳的人是谁
            sender_info=sender_info,
            receiver_info=receiver_info,
        )

        message_base: MessageBase = MessageBase(
            message_info=message_info,
            message_segment=handled_message,
            raw_message=json.dumps(raw_message),
        )

        if system_notice:
            await self.put_notice(message_base)
        else:
            logger.info("发送到Maibot处理通知信息")
            await message_send_instance.message_send(message_base)

    def _map_milky_event_to_notice(self, event_type: str, event_data: dict) -> str:
        """将 Milky 事件类型映射到通知类型"""
        if event_type == "message_recall":
            # 判断是群聊还是私聊
            message_scene = event_data.get("message_scene")
            if message_scene == "friend":
                return NoticeType.friend_recall
            elif message_scene == "group":
                return NoticeType.group_recall
        elif event_type in ["friend_nudge", "group_nudge"]:
            return NoticeType.notify
        elif event_type in ["group_mute", "group_whole_mute"]:
            return NoticeType.group_ban
        elif event_type in ["friend_request", "group_join_request", "group_invited_join_request", "group_invitation"]:
            return NoticeType.notify
        return "unknown"

    def _get_notify_sub_type(self, event_type: str, event_data: dict) -> str:
        """获取通知子类型"""
        if event_type in ["friend_nudge", "group_nudge"]:
            return NoticeType.Notify.poke
        return "unknown"

    def _get_group_ban_sub_type(self, event_type: str, event_data: dict) -> str:
        """获取群禁言子类型"""
        if event_type == "group_mute":
            duration = event_data.get("duration", 0)
            if duration > 0:
                return NoticeType.GroupBan.ban
            else:
                return NoticeType.GroupBan.lift_ban
        elif event_type == "group_whole_mute":
            is_mute = event_data.get("is_mute", False)
            if is_mute:
                return NoticeType.GroupBan.ban
            else:
                return NoticeType.GroupBan.lift_ban
        return "unknown"

    async def handle_poke_notify(
        self, event_data: dict, group_id: int, user_id: int
    ) -> Tuple[Seg | None, UserInfo | None]:
        # sourcery skip: merge-comparisons, merge-duplicate-blocks, remove-redundant-if, remove-unnecessary-else, swap-if-else-branches
        
        # Milky 可能不提供机器人信息，使用默认值
        self_id = event_data.get("self_id", 0)
        target_id = event_data.get("receiver_id") or event_data.get("user_id")
        
        # 获取用户信息 - 修复不存在的sender字段
        # 从sender_id获取用户ID，然后调用API获取详细信息
        user_id = event_data.get("sender_id") or event_data.get("user_id")
        user_name = f"用户{user_id}" if user_id else "未知用户"
        user_cardname = f"用户{user_id}" if user_id else "未知用户"
        
        # 如果有用户ID，尝试获取详细信息
        if user_id:
            try:
                member_info_result = await get_member_info(group_id, user_id)
                if member_info_result.get("status") == "ok":
                    member_data = member_info_result.get("data", {})
                    user_name = member_data.get("nickname", f"用户{user_id}")
                    user_cardname = member_data.get("card", f"用户{user_id}")
                    logger.debug(f"通过API获取到群成员信息: nickname={user_name}, card={user_cardname}")
            except Exception as e:
                logger.error(f"调用API获取用户信息时发生错误: {e}")
                user_name = f"用户{user_id}" if user_id else "未知用户"
                user_cardname = f"用户{user_id}" if user_id else "未知用户"

        # 计算Seg
        if self_id == target_id:
            display_name = ""
            target_name = "机器人"
        elif self_id == user_id:
            # 让ada不发送麦麦戳别人的消息
            return None, None
        else:
            # 老实说这一步判定没啥意义，毕竟私聊是没有其他人之间的戳一戳，但是感觉可以有这个判定来强限制群聊环境
            if group_id:
                target_name = f"用户{target_id}" if target_id else "未知目标"
                display_name = user_name
            else:
                return None, None

        first_txt: str = "戳了戳"
        second_txt: str = ""

        user_info: UserInfo = UserInfo(
            platform=global_config.maibot_server.platform_name,
            user_id=user_id,
            user_nickname=user_name,
            user_cardname=user_cardname,
        )

        seg_data: Seg = Seg(
            type="text",
            data=f"{display_name}{first_txt}{target_name}{second_txt}（这是QQ的一个功能，用于提及某人，但没那么明显）",
        )
        return seg_data, user_info

    async def handle_ban_notify(self, event_data: dict, group_id: int) -> Tuple[Seg, UserInfo] | Tuple[None, None]:
        if not group_id:
            logger.error("群ID不能为空，无法处理禁言通知")
            return None, None

        # 计算user_info
        operator_id = event_data.get("operator_id")
        operator_nickname: str = f"用户{operator_id}" if operator_id else "未知操作者"
        operator_cardname: str = None

        operator_info: UserInfo = UserInfo(
            platform=global_config.maibot_server.platform_name,
            user_id=operator_id,
            user_nickname=operator_nickname,
            user_cardname=operator_cardname,
        )

        # 计算Seg
        user_id = event_data.get("user_id")
        banned_user_info: UserInfo = None
        user_nickname: str = f"用户{user_id}" if user_id else "未知用户"
        user_cardname: str = None
        sub_type: str = None

        duration = event_data.get("duration")
        if duration is None:
            logger.error("禁言时长不能为空，无法处理禁言通知")
            return None, None

        if user_id == 0:  # 为全体禁言
            sub_type: str = "whole_ban"
            self._ban_operation(group_id)
        else:  # 为单人禁言
            # 获取被禁言人的信息
            sub_type: str = "ban"
            banned_user_info: UserInfo = UserInfo(
                platform=global_config.maibot_server.platform_name,
                user_id=user_id,
                user_nickname=user_nickname,
                user_cardname=user_cardname,
            )
            self._ban_operation(group_id, user_id, int(time.time() + duration))

        seg_data: Seg = Seg(
            type="notify",
            data={
                "sub_type": sub_type,
                "duration": duration,
                "banned_user_info": banned_user_info.to_dict() if banned_user_info else None,
            },
        )

        return seg_data, operator_info

    async def handle_lift_ban_notify(
        self, event_data: dict, group_id: int
    ) -> Tuple[Seg, UserInfo] | Tuple[None, None]:
        if not group_id:
            logger.error("群ID不能为空，无法处理解除禁言通知")
            return None, None

        # 计算user_info
        operator_id = event_data.get("operator_id")
        operator_nickname: str = f"用户{operator_id}" if operator_id else "未知操作者"
        operator_cardname: str = None

        operator_info: UserInfo = UserInfo(
            platform=global_config.maibot_server.platform_name,
            user_id=operator_id,
            user_nickname=operator_nickname,
            user_cardname=operator_cardname,
        )

        # 计算Seg
        sub_type: str = None
        user_nickname: str = f"用户{user_id}" if user_id else "未知用户"
        user_cardname: str = None
        lifted_user_info: UserInfo = None

        user_id = event_data.get("user_id")
        if user_id == 0:  # 全体禁言解除
            sub_type = "whole_lift_ban"
            self._lift_operation(group_id)
        else:  # 单人禁言解除
            sub_type = "lift_ban"
            lifted_user_info: UserInfo = UserInfo(
                platform=global_config.maibot_server.platform_name,
                user_id=user_id,
                user_nickname=user_nickname,
                user_cardname=user_cardname,
            )
            self._lift_operation(group_id, user_id)

        seg_data: Seg = Seg(
            type="notify",
            data={
                "sub_type": sub_type,
                "lifted_user_info": lifted_user_info.to_dict() if lifted_user_info else None,
            },
        )
        return seg_data, operator_info

    def _ban_operation(self, group_id: int, user_id: Optional[int] = None, lift_time: Optional[int] = None) -> None:
        """
        将用户禁言记录添加到self.banned_list中
        如果是全体禁言，则user_id为0
        """
        if user_id is None:
            user_id = 0  # 使用0表示全体禁言
            lift_time = -1
        ban_record = BanUser(user_id=user_id, group_id=group_id, lift_time=lift_time)
        for record in self.banned_list:
            if is_identical(record, ban_record):
                self.banned_list.remove(record)
                self.banned_list.append(ban_record)
                db_manager.create_ban_record(ban_record)  # 作为更新
                return
        self.banned_list.append(ban_record)
        db_manager.create_ban_record(ban_record)  # 添加到数据库

    def _lift_operation(self, group_id: int, user_id: Optional[int] = None) -> None:
        """
        从self.lifted_group_list中移除已经解除全体禁言的群
        """
        if user_id is None:
            user_id = 0  # 使用0表示全体禁言
        ban_record = BanUser(user_id=user_id, group_id=group_id, lift_time=-1)
        self.lifted_list.append(ban_record)
        db_manager.delete_ban_record(ban_record)  # 删除数据库中的记录

    async def put_notice(self, message_base: MessageBase) -> None:
        """
        将处理后的通知消息放入通知队列
        """
        if notice_queue.full() or unsuccessful_notice_queue.full():
            logger.warning("通知队列已满，可能是多次发送失败，消息丢弃")
        else:
            await notice_queue.put(message_base)

    async def handle_natural_lift(self) -> None:
        while True:
            if len(self.lifted_list) != 0:
                lift_record = self.lifted_list.pop()
                group_id = lift_record.group_id
                user_id = lift_record.user_id

                db_manager.delete_ban_record(lift_record)  # 从数据库中删除禁言记录

                seg_message: Seg = await self.natural_lift(group_id, user_id)

                # Milky 可能不提供群名称，使用默认值
                group_name = ""
                group_info = GroupInfo(
                    platform=global_config.maibot_server.platform_name,
                    group_id=group_id,
                    group_name=group_name,
                )

                # 自然解除禁言没有发送者，只有接收者（群）
                sender_info = None
                
                # 创建接收者信息（群）
                receiver_info = self._create_receiver_info(
                    group_id=group_id,
                    group_name=group_name,
                )
                
                message_info: BaseMessageInfo = BaseMessageInfo(
                    platform=global_config.maibot_server.platform_name,
                    message_id="notice",
                    time=time.time(),
                    user_info=None,  # 自然解除禁言没有操作者
                    group_info=group_info,
                    template_info=None,
                    format_info=None,
                    sender_info=sender_info,
                    receiver_info=receiver_info,
                )

                message_base: MessageBase = MessageBase(
                    message_info=message_info,
                    message_segment=seg_message,
                    raw_message=json.dumps(
                        {
                            "post_type": "notice",
                            "notice_type": "group_ban",
                            "sub_type": "lift_ban",
                            "group_id": group_id,
                            "user_id": user_id,
                            "operator_id": None,  # 自然解除禁言没有操作者
                        }
                    ),
                )

                await self.put_notice(message_base)
                await asyncio.sleep(0.5)  # 确保队列处理间隔
            else:
                await asyncio.sleep(5)  # 每5秒检查一次

    async def natural_lift(self, group_id: int, user_id: int) -> Seg | None:
        if not group_id:
            logger.error("群ID不能为空，无法处理解除禁言通知")
            return None

        if user_id == 0:  # 理论上永远不会触发
            return Seg(
                type="notify",
                data={
                    "sub_type": "whole_lift_ban",
                    "lifted_user_info": None,
                },
            )

        user_nickname: str = f"用户{user_id}" if user_id else "未知用户"
        user_cardname: str = None

        lifted_user_info: UserInfo = UserInfo(
            platform=global_config.maibot_server.platform_name,
            user_id=user_id,
            user_nickname=user_nickname,
            user_cardname=user_cardname,
        )

        return Seg(
            type="notify",
            data={
                "sub_type": "lift_ban",
                "lifted_user_info": lifted_user_info.to_dict(),
            },
        )

    async def auto_lift_detect(self) -> None:
        while True:
            if len(self.banned_list) == 0:
                await asyncio.sleep(5)
                continue
            for ban_record in self.banned_list:
                if ban_record.user_id == 0 or ban_record.lift_time == -1:
                    continue
                if ban_record.lift_time <= int(time.time()):
                    # 触发自然解除禁言
                    logger.info(f"检测到用户 {ban_record.user_id} 在群 {ban_record.group_id} 的禁言已解除")
                    self.lifted_list.append(ban_record)
                    self.banned_list.remove(ban_record)
            await asyncio.sleep(5)

    async def send_notice(self) -> None:
        """
        发送通知消息到 Milky
        """
        while True:
            if not unsuccessful_notice_queue.empty():
                to_be_send: MessageBase = await unsuccessful_notice_queue.get()
                try:
                    send_status = await message_send_instance.message_send(to_be_send)
                    if send_status:
                        unsuccessful_notice_queue.task_done()
                    else:
                        await unsuccessful_notice_queue.put(to_be_send)
                except Exception as e:
                    logger.error(f"发送通知消息失败: {str(e)}")
                    await unsuccessful_notice_queue.put(to_be_send)
                await asyncio.sleep(1)
                continue
            to_be_send: MessageBase = await notice_queue.get()
            try:
                send_status = await message_send_instance.message_send(to_be_send)
                if send_status:
                    notice_queue.task_done()
                else:
                    await unsuccessful_notice_queue.put(to_be_send)
            except Exception as e:
                logger.error(f"发送通知消息失败: {str(e)}")
                await unsuccessful_notice_queue.put(to_be_send)
            await asyncio.sleep(1)


notice_handler = NoticeHandler()
