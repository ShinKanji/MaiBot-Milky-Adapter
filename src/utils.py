import aiohttp
import json
import base64
import uuid
import urllib3
import ssl
import io

from src.database import BanUser, db_manager
from .logger import logger
from .milky_com_layer import milky_com

from PIL import Image
from typing import Union, List, Tuple, Optional


class SSLAdapter(urllib3.PoolManager):
    def __init__(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.set_ciphers("DEFAULT@SECLEVEL=1")
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = context
        super().__init__(*args, **kwargs)


async def get_group_info(group_id: int) -> dict | None:
    """
    获取群相关信息

    返回值需要处理可能为空的情况
    """
    logger.debug("获取群聊信息中")
    result = await milky_com.get_group_info(group_id)
    if result:
        logger.debug(f"群信息获取成功: {result}")
    return result


async def get_group_detail_info(group_id: int) -> dict | None:
    """
    获取群详细信息

    返回值需要处理可能为空的情况
    """
    logger.debug("获取群详细信息中")
    # Milky 可能没有单独的详细群信息 API，暂时使用普通群信息
    result = await milky_com.get_group_info(group_id)
    if result:
        logger.debug(f"群详细信息获取成功: {result}")
    return result


async def get_member_info(group_id: int, user_id: int) -> dict | None:
    """
    获取群成员信息

    返回值需要处理可能为空的情况
    """
    logger.debug("获取群成员信息中")
    result = await milky_com.get_group_member_info(group_id, user_id)
    if result:
        logger.debug(f"群成员信息获取成功: {result}")
    return result


async def get_image_base64(url: str) -> str:
    # sourcery skip: raise-specific-error
    """获取图片/表情包的Base64"""
    logger.debug(f"下载图片: {url}")
    http = SSLAdapter()
    try:
        response = http.request("GET", url, timeout=10)
        if response.status != 200:
            raise Exception(f"HTTP Error: {response.status}")
        image_bytes = response.data
        return base64.b64encode(image_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"图片下载失败: {str(e)}")
        raise


def convert_image_to_gif(image_base64: str) -> str:
    # sourcery skip: extract-method
    """
    将Base64编码的图片转换为GIF格式
    Parameters:
        image_base64: str: Base64编码的图片数据
    Returns:
        str: Base64编码的GIF图片数据
    """
    logger.debug("转换图片为GIF格式")
    try:
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        output_buffer = io.BytesIO()
        image.save(output_buffer, format="GIF")
        output_buffer.seek(0)
        return base64.b64encode(output_buffer.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"图片转换为GIF失败: {str(e)}")
        return image_base64


async def get_self_info() -> dict | None:
    """
    获取自身信息
    Returns:
        data: dict: 返回的自身信息
    """
    logger.debug("获取自身信息中")
    result = await milky_com.get_login_info()
    if result:
        logger.debug(f"自身信息获取成功: {result}")
    return result


def get_image_format(raw_data: str) -> str:
    """
    从Base64编码的数据中确定图片的格式。
    Parameters:
        raw_data: str: Base64编码的图片数据。
    Returns:
        format: str: 图片的格式（例如 'jpeg', 'png', 'gif'）。
    """
    image_bytes = base64.b64decode(raw_data)
    return Image.open(io.BytesIO(image_bytes)).format.lower()


async def get_stranger_info(user_id: int) -> dict | None:
    """
    获取陌生人信息
    Parameters:
        user_id: 用户ID
    Returns:
        dict: 返回的陌生人信息
    """
    logger.debug("获取陌生人信息中")
    result = await milky_com.get_stranger_info(user_id)
    if result:
        logger.debug(f"陌生人信息获取成功: {result}")
    return result


async def get_message_detail(message_seq: Union[str, int]) -> dict | None:
    """
    获取消息详情，可能为空
    Parameters:
        message_seq: 消息序列号
    Returns:
        dict: 返回的消息详情
    """
    logger.debug("获取消息详情中")
    # Milky 需要知道消息场景，这里暂时使用 group 作为默认值
    # TODO: 根据实际使用场景确定正确的 message_scene
    params = {
        "message_scene": "group",
        "peer_id": 0,  # 需要根据实际情况确定
        "message_seq": message_seq
    }
    result = await milky_com.get_message("group", 0, message_seq)
    if result:
        logger.debug(f"消息详情获取成功: {result}")
    return result


async def get_record_detail(file: str, file_id: Optional[str] = None) -> dict | None:
    """
    获取语音消息内容
    Parameters:
        file: 文件名
        file_id: 文件ID
    Returns:
        dict: 返回的语音消息详情
    """
    logger.debug("获取语音消息详情中")
    result = await milky_com.get_record(file, file_id)
    if result:
        logger.debug(f"语音消息详情获取成功: {str(result)[:200]}...")  # 防止语音的超长base64编码导致日志过长
    return result


async def read_ban_list() -> Tuple[List[BanUser], List[BanUser]]:
    """
    从根目录下的data文件夹中的文件读取禁言列表。
    同时自动更新已经失效禁言
    Returns:
        Tuple[
            一个仍在禁言中的用户的BanUser列表,
            一个已经自然解除禁言的用户的BanUser列表,
        ]
    """
    try:
        ban_list = db_manager.get_ban_records()
        lifted_list: List[BanUser] = []
        logger.info("已经读取禁言列表")
        
        for ban_record in ban_list:
            if ban_record.user_id == 0:
                # 全体禁言检查
                fetched_group_info = await get_group_info(ban_record.group_id)
                if fetched_group_info is None:
                    logger.warning(f"无法获取群信息，群号: {ban_record.group_id}，默认禁言解除")
                    lifted_list.append(ban_record)
                    ban_list.remove(ban_record)
                    continue
                    
                # Milky 可能不直接提供全体禁言状态，暂时跳过检查
                # TODO: 实现 Milky 的全体禁言状态检查
                
            else:
                # 个人禁言检查
                fetched_member_info = await get_member_info(ban_record.group_id, ban_record.user_id)
                if fetched_member_info is None:
                    logger.warning(
                        f"无法获取群成员信息，用户ID: {ban_record.user_id}, 群号: {ban_record.group_id}，默认禁言解除"
                    )
                    lifted_list.append(ban_record)
                    ban_list.remove(ban_record)
                    continue
                    
                # Milky 可能不直接提供禁言状态，暂时跳过检查
                # TODO: 实现 Milky 的禁言状态检查
                
        db_manager.update_ban_record(ban_list)
        return ban_list, lifted_list
    except Exception as e:
        logger.error(f"读取禁言列表失败: {e}")
        return [], []


def save_ban_record(list: List[BanUser]):
    return db_manager.update_ban_record(list)
