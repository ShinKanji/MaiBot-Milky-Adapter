from src.logger import logger
from src.config import global_config
from src.utils import (
    get_group_info,
    get_member_info,
    get_image_base64,
    get_record_detail,
    get_self_info,
    get_message_detail,
)
from .qq_emoji_list import qq_face
from .message_sending import message_send_instance
from . import RealMessageType, MessageType, ACCEPT_FORMAT

import time
import json
from typing import List, Tuple, Optional, Dict, Any
import uuid

from maim_message import (
    UserInfo,
    GroupInfo,
    Seg,
    BaseMessageInfo,
    MessageBase,
    TemplateInfo,
    FormatInfo,
)


class MessageHandler:
    def __init__(self):
        self.bot_id_list: Dict[int, bool] = {}

    async def check_allow_to_chat(
        self,
        user_id: int,
        group_id: Optional[int] = None,
        ignore_bot: Optional[bool] = False,
        ignore_global_list: Optional[bool] = False,
    ) -> bool:
        # sourcery skip: hoist-statement-from-if, merge-else-if-into-elif
        """
        检查是否允许聊天
        Parameters:
            user_id: int: 用户ID
            group_id: int: 群ID
            ignore_bot: bool: 是否忽略机器人检查
            ignore_global_list: bool: 是否忽略全局黑名单检查
        Returns:
            bool: 是否允许聊天
        """
        logger.debug(f"群聊id: {group_id}, 用户id: {user_id}")
        logger.debug("开始检查聊天白名单/黑名单")
        if group_id:
            if global_config.chat.group_list_type == "whitelist" and group_id not in global_config.chat.group_list:
                logger.warning("群聊不在聊天白名单中，消息被丢弃")
                return False
            elif global_config.chat.group_list_type == "blacklist" and group_id in global_config.chat.group_list:
                logger.warning("群聊在聊天黑名单中，消息被丢弃")
                return False
        else:
            if global_config.chat.private_list_type == "whitelist" and user_id not in global_config.chat.private_list:
                logger.warning("私聊不在聊天白名单中，消息被丢弃")
                return False
            elif global_config.chat.private_list_type == "blacklist" and user_id in global_config.chat.private_list:
                logger.warning("私聊在聊天黑名单中，消息被丢弃")
                return False
        if user_id in global_config.chat.ban_user_id and not ignore_global_list:
            logger.warning("用户在全局黑名单中，消息被丢弃")
            return False

        # 暂时跳过机器人检查，因为 Milky 可能不提供这个信息
        # TODO: 实现 Milky 的机器人检查逻辑

        return True

    async def handle_raw_message(self, raw_message: dict) -> None:
        """
        从 Milky 接受的原始消息处理

        Parameters:
            raw_message: dict: 原始消息
        """
        # 从 Milky 事件中提取消息数据
        event_data = raw_message.get("data", {})
        
        # 判断消息类型
        message_scene = event_data.get("message_scene")
        if message_scene == "friend":
            message_type = MessageType.private
            sub_type = MessageType.Private.friend
            group_id = None
        elif message_scene == "group":
            message_type = MessageType.group
            sub_type = MessageType.Group.normal
            group_id = event_data.get("peer_id")
        elif message_scene == "temp":
            message_type = MessageType.private
            sub_type = MessageType.Private.group
            group_id = event_data.get("peer_id")
        else:
            logger.warning(f"不支持的消息场景: {message_scene}")
            return None

        # 获取消息信息
        message_seq = event_data.get("message_seq")
        message_time = event_data.get("time", time.time())
        
        # 获取发送者信息
        sender_info = event_data.get("sender", {})
        user_id = sender_info.get("user_id")
        user_nickname = sender_info.get("nickname", "")
        user_cardname = sender_info.get("card", "")

        template_info: TemplateInfo = None  # 模板信息，暂时为空，等待启用
        format_info: FormatInfo = FormatInfo(
            content_format=["text", "image", "emoji", "voice"],
            accept_format=ACCEPT_FORMAT,
        )  # 格式化信息

        if message_type == MessageType.private:
            if sub_type == MessageType.Private.friend:
                if not await self.check_allow_to_chat(user_id, None):
                    return None

                # 发送者用户信息
                user_info: UserInfo = UserInfo(
                    platform=global_config.maibot_server.platform_name,
                    user_id=user_id,
                    user_nickname=user_nickname,
                    user_cardname=user_cardname,
                )

                # 不存在群信息
                group_info: GroupInfo = None
            elif sub_type == MessageType.Private.group:
                """
                本部分暂时不做支持，先放着
                """
                logger.warning("群临时消息类型不支持")
                return None
        elif message_type == MessageType.group:
            if sub_type == MessageType.Group.normal:
                if not await self.check_allow_to_chat(user_id, group_id):
                    return None

                # 发送者用户信息
                user_info: UserInfo = UserInfo(
                    platform=global_config.maibot_server.platform_name,
                    user_id=user_id,
                    user_nickname=user_nickname,
                    user_cardname=user_cardname,
                )

                # 群聊信息
                group_info: GroupInfo = GroupInfo(
                    platform=global_config.maibot_server.platform_name,
                    group_id=group_id,
                    group_name="",  # Milky 可能不提供群名称
                )
            else:
                logger.warning(f"群聊消息类型 {sub_type} 不支持")
                return None

        additional_config: dict = {}
        if global_config.voice.use_tts:
            additional_config["allow_tts"] = True

        # 消息信息
        message_info: BaseMessageInfo = BaseMessageInfo(
            platform=global_config.maibot_server.platform_name,
            message_id=str(message_seq),  # 使用消息序列号作为消息ID
            time=message_time,
            user_info=user_info,
            group_info=group_info,
            template_info=template_info,
            format_info=format_info,
            additional_config=additional_config,
        )

        # 处理实际信息
        if not event_data.get("message"):
            logger.warning("原始消息内容为空")
            return None

        # 获取Seg列表
        seg_message: List[Seg] = await self.handle_real_message(event_data)
        if not seg_message:
            logger.warning("处理后消息内容为空")
            return None
        submit_seg: Seg = Seg(
            type="seglist",
            data=seg_message,
        )
        # MessageBase创建
        message_base: MessageBase = MessageBase(
            message_info=message_info,
            message_segment=submit_seg,
            raw_message=raw_message.get("raw_message"),
        )

        logger.info("发送到Maibot处理信息")
        await message_send_instance.message_send(message_base)

    async def handle_real_message(self, event_data: dict, in_reply: bool = False) -> List[Seg] | None:
        """
        处理实际消息
        Parameters:
            event_data: dict: Milky 事件数据
        Returns:
            seg_message: list[Seg]: 处理后的消息段列表
        """
        real_message: list = event_data.get("message", [])
        if not real_message:
            return None
        seg_message: List[Seg] = []
        for sub_message in real_message:
            sub_message: dict
            sub_message_type = sub_message.get("type")
            match sub_message_type:
                case RealMessageType.text:
                    ret_seg = await self.handle_text_message(sub_message)
                    if ret_seg:
                        seg_message.append(ret_seg)
                    else:
                        logger.warning("text处理失败")
                case RealMessageType.face:
                    ret_seg = await self.handle_face_message(sub_message)
                    if ret_seg:
                        seg_message.append(ret_seg)
                    else:
                        logger.warning("face处理失败或不支持")
                case RealMessageType.reply:
                    if not in_reply:
                        ret_seg = await self.handle_reply_message(sub_message)
                        if ret_seg:
                            seg_message += ret_seg
                        else:
                            logger.warning("reply处理失败")
                case RealMessageType.image:
                    ret_seg = await self.handle_image_message(sub_message)
                    if ret_seg:
                        seg_message.append(ret_seg)
                    else:
                        logger.warning("image处理失败")
                case RealMessageType.record:
                    ret_seg = await self.handle_record_message(sub_message)
                    if ret_seg:
                        seg_message.clear()
                        seg_message.append(ret_seg)
                        break  # 使得消息只有record消息
                    else:
                        logger.warning("record处理失败或不支持")
                case RealMessageType.video:
                    logger.warning("不支持视频解析")
                case RealMessageType.at:
                    ret_seg = await self.handle_at_message(
                        sub_message,
                        event_data.get("self_id"),
                        event_data.get("peer_id"),
                    )
                    if ret_seg:
                        seg_message.append(ret_seg)
                    else:
                        logger.warning("at处理失败")
                case RealMessageType.rps:
                    logger.warning("暂时不支持猜拳魔法表情解析")
                case RealMessageType.dice:
                    logger.warning("暂时不支持骰子表情解析")
                case RealMessageType.shake:
                    # 预计等价于戳一戳
                    logger.warning("暂时不支持窗口抖动解析")
                case RealMessageType.share:
                    logger.warning("暂时不支持链接解析")
                case RealMessageType.forward:
                    # Milky 可能不直接支持转发消息，暂时跳过
                    logger.warning("暂时不支持转发消息解析")
                case RealMessageType.node:
                    logger.warning("不支持转发消息节点解析")
                case _:
                    logger.warning(f"未知消息类型: {sub_message_type}")
        return seg_message

    async def handle_text_message(self, raw_message: dict) -> Seg:
        """
        处理纯文本信息
        Parameters:
            raw_message: dict: 原始消息
        Returns:
            seg_data: Seg: 处理后的消息段
        """
        message_data: dict = raw_message.get("data")
        plain_text: str = message_data.get("text")
        return Seg(type="text", data=plain_text)

    async def handle_face_message(self, raw_message: dict) -> Seg | None:
        """
        处理表情消息
        Parameters:
            raw_message: dict: 原始消息
        Returns:
            seg_data: Seg: 处理后的消息段
        """
        message_data: dict = raw_message.get("data")
        face_raw_id: str = str(message_data.get("id"))
        if face_raw_id in qq_face:
            face_content: str = qq_face.get(face_raw_id)
            return Seg(type="text", data=face_content)
        else:
            logger.warning(f"不支持的表情：{face_raw_id}")
            return None

    async def handle_image_message(self, raw_message: dict) -> Seg | None:
        """
        处理图片消息与表情包消息
        Parameters:
            raw_message: dict: 原始消息
        Returns:
            seg_data: Seg: 处理后的消息段
        """
        message_data: dict = raw_message.get("data")
        image_sub_type = message_data.get("sub_type")
        try:
            # Milky 可能直接提供 base64 数据
            image_base64 = message_data.get("base64")
            if not image_base64:
                # 如果没有 base64 数据，尝试从 URL 获取
                image_url = message_data.get("url")
                if image_url:
                    image_base64 = await get_image_base64(image_url)
                else:
                    logger.warning("图片消息缺少文件信息")
                    return None
        except Exception as e:
            logger.error(f"图片消息处理失败: {str(e)}")
            return None
            
        if image_sub_type == 0:
            """这部分认为是图片"""
            return Seg(type="image", data=image_base64)
        elif image_sub_type not in [4, 9]:
            """这部分认为是表情包"""
            return Seg(type="emoji", data=image_base64)
        else:
            logger.warning(f"不支持的图片子类型：{image_sub_type}")
            return None

    async def handle_at_message(self, raw_message: dict, self_id: int, group_id: int) -> Seg | None:
        # sourcery skip: use-named-expression
        """
        处理at消息
        Parameters:
            raw_message: dict: 原始消息
            self_id: int: 机器人QQ号
            group_id: int: 群号
        Returns:
            seg_data: Seg: 处理后的消息段
        """
        message_data: dict = raw_message.get("data")
        if message_data:
            qq_id = message_data.get("qq")
            if str(self_id) == str(qq_id):
                logger.debug("机器人被at")
                # Milky 可能不提供机器人信息，使用默认值
                return Seg(type="text", data=f"@<机器人:{self_id}>")
            else:
                # Milky 可能不提供成员信息，使用默认值
                return Seg(type="text", data=f"@<用户:{qq_id}>")

    async def handle_record_message(self, raw_message: dict) -> Seg | None:
        """
        处理语音消息
        Parameters:
            raw_message: dict: 原始消息
        Returns:
            seg_data: Seg: 处理后的消息段
        """
        message_data: dict = raw_message.get("data")
        file: str = message_data.get("file")
        if not file:
            logger.warning("语音消息缺少文件信息")
            return None
        try:
            # Milky 可能直接提供 base64 数据
            audio_base64: str = message_data.get("base64")
            if not audio_base64:
                # 如果没有 base64 数据，尝试从文件获取
                if file.startswith("base64://"):
                    audio_base64 = file[9:]  # 移除 "base64://" 前缀
                else:
                    logger.warning("语音消息缺少音频数据")
                    return None
        except Exception as e:
            logger.error(f"语音消息处理失败: {str(e)}")
            return None
        if not audio_base64:
            logger.error("语音消息处理失败，未获取到音频数据")
            return None
        return Seg(type="voice", data=audio_base64)

    async def handle_reply_message(self, raw_message: dict) -> List[Seg] | None:
        # sourcery skip: move-assign-in-block, use-named-expression
        """
        处理回复消息

        """
        raw_message_data: dict = raw_message.get("data")
        message_seq: int = None
        if raw_message_data:
            message_seq = raw_message_data.get("id")
        else:
            return None
            
        # Milky 可能不直接支持获取被引用消息，暂时返回简单回复
        seg_message: List[Seg] = []
        seg_message.append(Seg(type="text", data=f"[回复消息 {message_seq}]"))
        return seg_message

    async def handle_forward_message(self, message_list: list) -> Seg | None:
        """
        递归处理转发消息，并按照动态方式确定图片处理方式
        Parameters:
            message_list: list: 转发消息列表
        """
        # Milky 可能不直接支持转发消息，暂时返回占位符
        return Seg(type="text", data="[转发消息]")

    async def _handle_forward_message(self, message_list: list, layer: int) -> Tuple[Seg, int] | Tuple[None, int]:
        # sourcery skip: low-code-quality
        """
        递归处理实际转发消息
        Parameters:
            message_list: list: 转发消息列表，首层对应messages字段，后面对应content字段
            layer: int: 当前层级
        Returns:
            seg_data: Seg: 处理后的消息段
            image_count: int: 图片数量
        """
        # Milky 可能不直接支持转发消息，暂时返回占位符
        return Seg(type="text", data="[转发消息]"), 0

    async def _get_forward_message(self, raw_message: dict) -> Dict[str, Any] | None:
        # Milky 可能不直接支持转发消息，暂时返回 None
        logger.warning("Milky 暂不支持获取转发消息")
        return None


message_handler = MessageHandler()
