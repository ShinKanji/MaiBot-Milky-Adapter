import aiohttp
import asyncio
import json
import websockets
from typing import Dict, Any, Optional, Callable
from .logger import logger
from .config import global_config


class MilkyComLayer:
    """Milky 通信层，处理 HTTP 请求和事件推送"""
    
    def __init__(self):
        self.base_url: str = f"http://{global_config.milky_server.host}:{global_config.milky_server.port}"
        self.ws_base_url: str = f"ws://{global_config.milky_server.host}:{global_config.milky_server.port}"
        self.event_endpoint: str = global_config.milky_server.event_endpoint
        self.api_endpoint: str = global_config.milky_server.api_endpoint
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.event_handlers: Dict[str, Callable] = {}
        self.is_running: bool = False
        
    async def start(self):
        """启动 Milky 通信层"""
        if self.is_running:
            return
            
        self.session = aiohttp.ClientSession()
        self.is_running = True
        logger.info(f"Milky 通信层已启动，连接到 {self.base_url}")
        
        # 启动 WebSocket 事件监听
        asyncio.create_task(self._listen_events())
        
    async def stop(self):
        """停止 Milky 通信层"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        # 关闭 WebSocket 连接
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            
        # 关闭 HTTP 会话
        if self.session:
            await self.session.close()
        logger.info("Milky 通信层已停止")
        
    async def _listen_events(self):
        """通过 WebSocket 监听 Milky 事件推送"""
        while self.is_running:
            try:
                # 构建 WebSocket 连接 URL，包含 access_token 参数
                ws_url = f"{self.ws_base_url}{self.event_endpoint}"
                if hasattr(global_config.milky_server, 'access_token') and global_config.milky_server.access_token:
                    ws_url += f"?access_token={global_config.milky_server.access_token}"
                
                logger.info(f"正在连接 Milky WebSocket: {ws_url}")
                
                async with websockets.connect(ws_url) as websocket:
                    self.websocket = websocket
                    logger.info("Milky WebSocket 连接已建立")
                    
                    # 持续监听事件
                    async for message in websocket:
                        if not self.is_running:
                            break
                            
                        try:
                            # 解析 JSON 事件数据
                            event_data = json.loads(message)
                            logger.debug(f"收到 Milky 事件: {event_data.get('event_type', 'unknown')}")
                            logger.debug(f"完整的事件数据: {event_data}")
                            await self._handle_event(event_data)
                        except json.JSONDecodeError as e:
                            logger.error(f"解析事件数据失败: {e}, 原始数据: {message}")
                        except Exception as e:
                            logger.error(f"处理事件时发生错误: {e}")
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Milky WebSocket 连接已关闭，正在重连...")
            except websockets.exceptions.InvalidStatusCode as e:
                if e.status_code == 401:
                    logger.error("Milky WebSocket 鉴权失败，请检查 access_token")
                else:
                    logger.error(f"Milky WebSocket 连接失败，状态码: {e.status_code}")
            except Exception as e:
                logger.error(f"监听 Milky 事件时发生错误: {e}")
                
            # 等待一段时间后重试连接
            if self.is_running:
                logger.info("等待 5 秒后重连 Milky WebSocket...")
                await asyncio.sleep(5)
            
    async def _handle_event(self, event_data: Dict[str, Any]):
        """处理接收到的事件"""
        event_type = event_data.get("event_type")
        logger.debug(f"处理事件类型: {event_type}")
        logger.debug(f"事件数据结构: {event_data}")
        
        if event_type:
            handler = self.event_handlers.get(event_type)
            if handler:
                try:
                    logger.debug(f"调用事件处理器: {event_type}")
                    await handler(event_data)
                except Exception as e:
                    logger.error(f"执行事件处理器 {event_type} 时发生错误: {e}")
            else:
                logger.debug(f"未找到事件类型 {event_type} 的处理器")
        else:
            logger.warning(f"事件数据缺少 event_type 字段: {event_data}")
            
    def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        self.event_handlers[event_type] = handler
        logger.debug(f"注册事件处理器: {event_type}")
        
    async def call_api(self, action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """调用 Milky API
        
        Args:
            action: str: API 动作名称，如 'send_private_message'
            params: Dict[str, Any]: API 参数，默认为空字典
            
        Returns:
            Dict[str, Any]: API 响应结果
        """
        if not self.session:
            raise RuntimeError("Milky 通信层未启动")
            
        # 确保参数不为 None，即使没有参数也要发送空字典
        if params is None:
            params = {}
            
        try:
            # 构建 API 端点：/api/{action}
            api_url = f"{self.base_url}/api/{action}"
            
            # 构建请求头
            headers = {
                "Content-Type": "application/json"
            }
            
            # 如果有 access_token 配置，添加到请求头
            if hasattr(global_config.milky_server, 'access_token') and global_config.milky_server.access_token:
                headers["Authorization"] = f"Bearer {global_config.milky_server.access_token}"
            
            logger.debug(f"调用 Milky API: {action}, 参数: {params}")
            
            async with self.session.post(api_url, json=params, headers=headers) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        result = json.loads(response_text)
                        logger.debug(f"API 调用成功: {action}, 响应: {result}")
                        return result
                    except json.JSONDecodeError as e:
                        logger.error(f"API 响应解析失败: {action}, 响应文本: {response_text}, 错误: {e}")
                        return {
                            "status": "failed",
                            "retcode": -500,
                            "message": f"响应解析失败: {e}"
                        }
                        
                elif response.status == 401:
                    logger.error(f"API 鉴权失败: {action}, 请检查 access_token")
                    return {
                        "status": "failed",
                        "retcode": -401,
                        "message": "鉴权凭据未提供或不匹配"
                    }
                    
                elif response.status == 404:
                    logger.error(f"API 不存在: {action}")
                    return {
                        "status": "failed",
                        "retcode": -404,
                        "message": f"请求的 API 不存在: {action}"
                    }
                    
                elif response.status == 415:
                    logger.error(f"API 请求格式不支持: {action}")
                    return {
                        "status": "failed",
                        "retcode": -415,
                        "message": "POST 请求的 Content-Type 不支持"
                    }
                    
                else:
                    logger.error(f"API 调用失败: {action}, 状态码: {response.status}, 响应: {response_text}")
                    return {
                        "status": "failed",
                        "retcode": -response.status,
                        "message": f"HTTP {response.status}: {response_text}"
                    }
                    
        except Exception as e:
            logger.error(f"调用 Milky API 时发生错误: {action}, 错误: {e}")
            return {
                "status": "failed",
                "retcode": -500,
                "message": f"请求异常: {str(e)}"
            }
            
    async def send_private_message(self, user_id: int, message: list) -> Dict[str, Any]:
        """发送私聊消息"""
        params = {
            "user_id": user_id,
            "message": message
        }
        return await self.call_api("send_private_message", params)
        
    async def send_group_message(self, group_id: int, message: list) -> Dict[str, Any]:
        """发送群聊消息"""
        params = {
            "group_id": group_id,
            "message": message
        }
        return await self.call_api("send_group_message", params)
        
    async def set_group_member_mute(self, group_id: int, user_id: int, duration: int) -> Dict[str, Any]:
        """设置群成员禁言"""
        params = {
            "group_id": group_id,
            "user_id": user_id,
            "duration": duration
        }
        return await self.call_api("set_group_member_mute", params)
        
    async def set_group_whole_mute(self, group_id: int, is_mute: bool) -> Dict[str, Any]:
        """设置群全体禁言"""
        params = {
            "group_id": group_id,
            "is_mute": is_mute
        }
        return await self.call_api("set_group_whole_mute", params)
        
    async def kick_group_member(self, group_id: int, user_id: int, reject_add_request: bool = False) -> Dict[str, Any]:
        """踢出群成员"""
        params = {
            "group_id": group_id,
            "user_id": user_id,
            "reject_add_request": reject_add_request
        }
        return await self.call_api("kick_group_member", params)
        
    async def send_group_nudge(self, group_id: int, user_id: int) -> Dict[str, Any]:
        """发送群戳一戳"""
        params = {
            "group_id": group_id,
            "user_id": user_id
        }
        return await self.call_api("send_group_nudge", params)
        
    async def recall_group_message(self, group_id: int, message_seq: int) -> Dict[str, Any]:
        """撤回群消息"""
        params = {
            "group_id": group_id,
            "message_seq": message_seq
        }
        return await self.call_api("recall_group_message", params)
        
    async def get_group_info(self, group_id: int) -> Dict[str, Any]:
        """获取群信息"""
        params = {"group_id": group_id}
        return await self.call_api("get_group_info", params)
        
    async def get_group_member_info(self, group_id: int, user_id: int, no_cache: bool = True) -> Dict[str, Any]:
        """获取群成员信息"""
        params = {
            "group_id": group_id,
            "user_id": user_id,
            "no_cache": no_cache
        }
        return await self.call_api("get_group_member_info", params)
        
    async def get_login_info(self) -> Dict[str, Any]:
        """获取登录信息"""
        return await self.call_api("get_login_info", {})
        
    async def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """获取用户个人信息"""
        params = {"user_id": user_id}
        return await self.call_api("get_user_profile", params)
        
    async def get_friend_info(self, user_id: int, no_cache: bool = False) -> Dict[str, Any]:
        """获取好友信息"""
        params = {
            "user_id": user_id,
            "no_cache": no_cache
        }
        return await self.call_api("get_friend_info", params)
        
    async def get_message(self, message_scene: str, peer_id: int, message_seq: int) -> Dict[str, Any]:
        """获取消息详情"""
        params = {
            "message_scene": message_scene,
            "peer_id": peer_id,
            "message_seq": message_seq
        }
        return await self.call_api("get_message", params)
        
    async def get_record(self, file: str, file_id: str = None) -> Dict[str, Any]:
        """获取语音消息详情"""
        params = {"file": file}
        if file_id:
            params["file_id"] = file_id
        return await self.call_api("get_record", params)


# 全局实例
milky_com = MilkyComLayer()


async def milky_start_com():
    """启动 Milky 通信层"""
    await milky_com.start()


async def milky_stop_com():
    """停止 Milky 通信层"""
    await milky_com.stop()
