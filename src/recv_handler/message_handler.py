from src.logger import logger
from src.config import global_config
from src.utils import get_image_base64,get_member_info, get_user_profile
from .qq_emoji_list import qq_face
from .message_sending import message_send_instance
from . import RealMessageType, MessageType, ACCEPT_FORMAT

import time
import json
from typing import List, Tuple, Optional, Dict

from maim_message import (
    UserInfo,
    GroupInfo,
    Seg,
    BaseMessageInfo,
    MessageBase,
    TemplateInfo,
    FormatInfo,
    SenderInfo,
    ReceiverInfo,
)


class MessageHandler:
    def __init__(self):
        self.bot_id_list: Dict[int, bool] = {}

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
        # 添加详细日志，记录原始消息内容
        logger.debug(f"收到原始消息: {raw_message}")
        
        # 从 Milky 事件中提取消息数据
        event_data = raw_message.get("data", {})
        logger.debug(f"提取的事件数据: {event_data}")
        
        # 直接提取内层 data 字段（Milky 数据结构必定嵌套）
        actual_message_data = event_data.get("data", {})
        logger.debug(f"提取内层消息数据: {actual_message_data}")
        
        # 判断消息类型
        message_scene = actual_message_data.get("message_scene")
        logger.debug(f"消息场景: {message_scene}")
        
        # 如果 message_scene 为空，尝试从其他字段推断
        if not message_scene:
            if "group" in actual_message_data:
                message_scene = "group"
                logger.debug(f"从 group 字段推断消息场景为: {message_scene}")
            elif "friend" in actual_message_data:
                message_scene = "friend"
                logger.debug(f"从 friend 字段推断消息场景为: {message_scene}")
            elif "temp" in actual_message_data:
                message_scene = "temp"
                logger.debug(f"从 temp 字段推断消息场景为: {message_scene}")
        
        if message_scene == "friend":
            message_type = MessageType.private
            sub_type = MessageType.Private.friend
            group_id = None
        elif message_scene == "group":
            message_type = MessageType.group
            sub_type = MessageType.Group.normal
            group_id = actual_message_data.get("peer_id")
        elif message_scene == "temp":
            message_type = MessageType.private
            sub_type = MessageType.Private.group
            group_id = actual_message_data.get("peer_id")
        else:
            logger.warning(f"不支持的消息场景: {message_scene}")
            logger.debug(f"完整的事件数据结构: {actual_message_data}")
            logger.debug(f"可用的键: {list(actual_message_data.keys())}")
            return None

        # 获取消息信息
        message_seq = actual_message_data.get("message_seq")
        message_time = actual_message_data.get("time", time.time())
        
        # 获取发送者信息 - 修复数据结构解析问题
        # 尝试从不同字段获取发送者信息
        user_id = None
        user_nickname = ""
        user_cardname = ""
        
        # 优先从 group_member 获取（群聊消息）
        if "group_member" in actual_message_data:
            group_member = actual_message_data.get("group_member", {})
            user_id = group_member.get("user_id")
            user_nickname = group_member.get("nickname", "")
            user_cardname = group_member.get("card", "")
            logger.debug(f"从 group_member 获取发送者信息: user_id={user_id}, nickname={user_nickname}, card={user_cardname}")
        # 从 sender_id 获取（所有消息类型都有）
        elif "sender_id" in actual_message_data:
            user_id = actual_message_data.get("sender_id")
            logger.debug(f"从 sender_id 获取发送者ID: {user_id}")
            
            # 对于私聊消息或没有group_member的消息，调用API获取用户信息
            if message_type == MessageType.private or not group_id:
                try:
                    # 调用utils中的功能获取用户信息
                    user_info_result = await get_user_profile(user_id)
                    if user_info_result.get("status") == "ok":
                        user_data = user_info_result.get("data", {})
                        user_nickname = user_data.get("nickname", f"用户{user_id}")
                        user_cardname = user_data.get("nickname", f"用户{user_id}")
                        logger.debug(f"通过API获取到用户信息: nickname={user_nickname}")
                    else:
                        logger.warning(f"获取用户信息失败: {user_info_result}")
                        user_nickname = f"用户{user_id}"
                        user_cardname = f"用户{user_id}"
                except Exception as e:
                    logger.error(f"调用API获取用户信息时发生错误: {e}")
                    # 如果API调用失败，使用用户ID作为昵称
                    user_nickname = f"用户{user_id}"
                    user_cardname = f"用户{user_id}"
            else:
                # 群聊消息但没有group_member信息，尝试获取群成员信息
                try:
                    member_info_result = await get_member_info(group_id, user_id)
                    if member_info_result.get("status") == "ok":
                        member_data = member_info_result.get("data", {})
                        user_nickname = member_data.get("nickname", f"用户{user_id}")
                        user_cardname = member_data.get("card", f"用户{user_id}")
                        logger.debug(f"通过API获取到群成员信息: nickname={user_nickname}, card={user_cardname}")
                    else:
                        logger.warning(f"获取群成员信息失败: {member_info_result}")
                        user_nickname = f"用户{user_id}"
                        user_cardname = f"用户{user_id}"
                except Exception as e:
                    logger.error(f"调用API获取群成员信息时发生错误: {e}")
                    # 如果API调用失败，使用用户ID作为昵称
                    user_nickname = f"用户{user_id}"
                    user_cardname = f"用户{user_id}"
        
        if not user_id:
            logger.warning("无法获取发送者ID，跳过消息处理")
            return None

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
                group_name = ""
                if "group" in actual_message_data:
                    group_data = actual_message_data.get("group", {})
                    group_name = group_data.get("name", "")
                    logger.debug(f"从 group 字段获取群名称: {group_name}")
                
                group_info: GroupInfo = GroupInfo(
                    platform=global_config.maibot_server.platform_name,
                    group_id=group_id,
                    group_name=group_name,
                )
            else:
                logger.warning(f"群聊消息类型 {sub_type} 不支持")
                return None

        additional_config: dict = {}
        if global_config.voice.use_tts:
            additional_config["allow_tts"] = True

        # 创建发送者信息
        sender_info = self._create_sender_info(
            user_id=user_id,
            user_nickname=user_nickname,
            user_cardname=user_cardname,
            group_id=group_id,
            group_name=group_name,
        )
        
        # 创建接收者信息
        # 私聊时接收者是机器人，群聊时接收者是群
        receiver_info = self._create_receiver_info(
            target_user_id=event_data.get("self_id") if message_type == MessageType.private else None,
            target_user_nickname="机器人" if message_type == MessageType.private else "",
            group_id=group_id,
            group_name=group_name,
            is_bot=message_type == MessageType.private,
        )
        
        # 消息信息
        message_info: BaseMessageInfo = BaseMessageInfo(
            platform=global_config.maibot_server.platform_name,
            message_id=str(message_seq),  # 使用消息序列号作为消息ID
            time=float(message_time),
            user_info=user_info,
            group_info=group_info,
            template_info=template_info,
            format_info=format_info,
            additional_config=additional_config,
            sender_info=sender_info,
            receiver_info=receiver_info,
        )

        # 处理实际信息 - 修复 Milky 数据结构匹配问题
        # Milky 使用 segments 字段，而不是 message 字段
        if not actual_message_data.get("segments"):
            logger.warning("原始消息内容为空 (segments 字段不存在)")
            return None

        # 获取Seg列表
        seg_message: List[Seg] = await self.handle_real_message(actual_message_data)
        if not seg_message:
            logger.warning("处理后消息内容为空")
            return None
        submit_seg: Seg = Seg(
            type="seglist",
            data=seg_message,
        )
        logger.debug(f"创建的 submit_seg: {submit_seg}")
        # MessageBase创建
        # 将 raw_message 转换为 JSON 字符串，因为 MessageBase 期望字符串类型
        raw_message_str = json.dumps(raw_message, ensure_ascii=False) if raw_message else None
        message_base: MessageBase = MessageBase(
            message_info=message_info,
            message_segment=submit_seg,
            raw_message=raw_message_str,
        )

        logger.info("发送到Maibot处理信息")
        logger.debug(f"MessageBase 内容: message_info={message_info}, message_segment={submit_seg}, raw_message={raw_message}")
        await message_send_instance.message_send(message_base)

    async def handle_real_message(self, event_data: dict, in_reply: bool = False) -> List[Seg] | None:
        """
        处理实际消息
        Parameters:
            event_data: dict: Milky 事件数据
        Returns:
            seg_message: list[Seg]: 处理后的消息段列表
        """
        # 修复 Milky 数据结构匹配问题
        # Milky 使用 segments 字段，而不是 message 字段
        real_message: list = event_data.get("segments", [])
        if not real_message:
            logger.warning("segments 字段为空")
            return None
        seg_message: List[Seg] = []
        logger.debug(f"开始处理 {len(real_message)} 个消息段")
        for sub_message in real_message:
            sub_message: dict
            sub_message_type = sub_message.get("type")
            logger.debug(f"处理消息段类型: {sub_message_type}, 内容: {sub_message}")
            match sub_message_type:
                case RealMessageType.text:
                    ret_seg = await self.handle_text_message(sub_message)
                    if ret_seg:
                        seg_message.append(ret_seg)
                        logger.debug(f"成功添加文本段: {ret_seg}")
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
                case RealMessageType.mention:
                    # mention 类型等同于 at 类型，使用相同的处理方法
                    ret_seg = await self.handle_at_message(
                        sub_message,
                        event_data.get("self_id"),
                        event_data.get("peer_id"),
                    )
                    if ret_seg:
                        seg_message.append(ret_seg)
                        logger.debug(f"成功添加 mention 段: {ret_seg}")
                    else:
                        logger.warning("mention处理失败")
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
        logger.debug(f"处理文本消息: {plain_text}")
        seg = Seg(type="text", data=plain_text)
        logger.debug(f"创建的 Seg 对象: {seg}")
        return seg

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
                # Milky 使用 temp_url 字段，而不是 url 字段
                image_url = message_data.get("temp_url") or message_data.get("url")
                if image_url:
                    logger.debug(f"从 URL 获取图片: {image_url}")
                    image_base64 = await get_image_base64(image_url)
                else:
                    logger.warning("图片消息缺少文件信息 (temp_url 和 url 都不存在)")
                    logger.debug(f"可用的字段: {list(message_data.keys())}")
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
        处理at消息和mention消息
        Parameters:
            raw_message: dict: 原始消息
            self_id: int: 机器人QQ号
            group_id: int: 群号
        Returns:
            seg_data: Seg: 处理后的消息段
        """
        message_data: dict = raw_message.get("data")
        if message_data:
            # Milky 使用 user_id 字段，而不是 qq 字段
            user_id = message_data.get("user_id") or message_data.get("qq")
            if user_id:
                if str(self_id) == str(user_id):
                    logger.debug("机器人被at")
                    # Milky 可能不提供机器人信息，使用默认值
                    return Seg(type="text", data=f"@<机器人:{self_id}>")
                else:
                    # Milky 可能不提供成员信息，使用默认值
                    return Seg(type="text", data=f"@<用户:{user_id}>")
            else:
                logger.warning("at/mention 消息缺少用户ID")
                return None
        else:
            logger.warning("at/mention 消息缺少数据字段")
            return None

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

    async def handle_forward_message(self, raw_message: dict) -> Seg | None:
        """
        对外接口：处理转发消息 (IncomingForwardedMessage)
        """
        messages = await self._get_forward_message(raw_message)
        if not messages:
            return None

        seg, _ = await self._handle_forward_message(messages)
        return seg

    async def _handle_forward_message(
        self, 
        message_list: list, 
        layer: int = 0
    ) -> Tuple[Seg | None, int]:
        """
        递归处理实际转发消息
        Parameters:
            message_list: list: 转发消息列表，首层对应 messages 字段，后面对应 content 字段
            layer: int: 当前层级
        Returns:
            seg_data: Seg | None: 处理后的消息段
            image_count: int: 图片数量
        """
        if not message_list:
            logger.warning(f"_handle_forward_message: 第 {layer} 层转发消息为空")
            return Seg(type="text", data="[转发消息]"), 0

        seg_messages: list = []
        image_count = 0

        for msg in message_list:
            sender_name: str = msg.get("sender_name", "未知")
            ts: int = msg.get("time", 0)
            avatar_url: str = msg.get("avatar_url", "")

            # 遍历消息段
            for seg in msg.get("segments", []):
                seg_type = seg.get("type")
                seg_data = seg.get("data")

                if not seg_type:
                    logger.warning(f"_handle_forward_message: 无效消息段 {seg}")
                    continue

                if seg_type == "forward":
                    # 嵌套转发，递归调用
                    nested_messages = seg_data.get("messages")
                    nested_seg, nested_img_count = await self._handle_forward_message(nested_messages, layer + 1)
                    if nested_seg:
                        seg_messages.append(nested_seg)
                    image_count += nested_img_count
                elif seg_type == "image":
                    seg_messages.append(Seg(type="image", data=seg_data))
                    image_count += 1
                else:
                    seg_messages.append(Seg(type=seg_type, data=seg_data))

            # 加入来源信息
            seg_messages.append(Seg(type="text", data=f"—— 来自 {sender_name} ({ts}) ——"))
            if avatar_url:
                seg_messages.append(Seg(type="image", data={"url": avatar_url}))
                image_count += 1

        return Seg(type="forward", data={"messages": seg_messages}), image_count

    async def _get_forward_message(self, raw_message: dict) -> list[dict] | None:
        """
        从原始消息中提取转发消息列表 (IncomingForwardedMessage[])
        
        Parameters:
            raw_message: dict - 原始消息
        Returns:
            messages: list[dict] | None - 转发消息列表，如果没有则返回 None
        """
        raw_message_data: dict = raw_message.get("data")
        if not raw_message_data:
            logger.warning("_get_forward_message: 缺少 data 字段")
            return None

        messages: list = raw_message_data.get("messages")
        if not messages:
            logger.warning("_get_forward_message: data 中未找到 messages 字段")
            return None

        if not isinstance(messages, list):
            logger.warning(f"_get_forward_message: messages 类型异常，期望 list，实际 {type(messages)}")
            return None

        return messages

message_handler = MessageHandler()
