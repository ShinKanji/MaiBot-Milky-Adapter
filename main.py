import asyncio
import sys
from src.logger import logger
from src.recv_handler.message_handler import message_handler
from src.recv_handler.meta_event_handler import meta_event_handler
from src.recv_handler.notice_handler import notice_handler
from src.recv_handler.message_sending import message_send_instance
from src.send_handler import send_handler
from src.config import global_config
from src.mmc_com_layer import mmc_start_com, mmc_stop_com, router
from src.milky_com_layer import milky_start_com, milky_stop_com
from src.event_handlers import setup_event_handlers

message_queue = asyncio.Queue()


async def message_recv():
    """从 Milky 接收消息"""
    # 设置事件处理器
    await setup_event_handlers(message_queue)
    logger.info("Milky 事件处理器设置完成")


async def message_process():
    while True:
        message = await message_queue.get()
        post_type = message.get("post_type")
        if post_type == "message":
            await message_handler.handle_raw_message(message)
        elif post_type == "meta_event":
            await meta_event_handler.handle_meta_event(message)
        elif post_type == "notice":
            await notice_handler.handle_notice(message)
        else:
            logger.warning(f"未知的post_type: {post_type}")
        message_queue.task_done()
        await asyncio.sleep(0.05)


async def main():
    message_send_instance.maibot_router = router
    _ = await asyncio.gather(milky_start_com(), message_recv(), mmc_start_com(), message_process())


async def graceful_shutdown():
    try:
        logger.info("正在关闭adapter...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 15)
        await milky_stop_com()  # 停止 Milky 通信层
        await mmc_stop_com()  # 后置避免神秘exception
        logger.info("Adapter已成功关闭")
    except Exception as e:
        logger.error(f"Adapter关闭中出现错误: {e}")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.warning("收到中断信号，正在优雅关闭...")
        loop.run_until_complete(graceful_shutdown())
    except Exception as e:
        logger.exception(f"主程序异常: {str(e)}")
        sys.exit(1)
    finally:
        if loop and not loop.is_closed():
            loop.close()
        sys.exit(0)
