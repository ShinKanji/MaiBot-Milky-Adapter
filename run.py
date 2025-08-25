#!/usr/bin/env python3
"""
MaiBot Milky 适配器启动脚本
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from main import main, graceful_shutdown
import asyncio
import signal


def signal_handler(signum, frame):
    """信号处理器"""
    print(f"\n收到信号 {signum}，正在优雅关闭...")
    asyncio.create_task(graceful_shutdown())


async def run_adapter():
    """运行适配器"""
    try:
        await main()
    except KeyboardInterrupt:
        print("\n收到中断信号，正在优雅关闭...")
        await graceful_shutdown()
    except Exception as e:
        print(f"适配器运行异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # 设置信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("启动 MaiBot Milky 适配器...")
    print("按 Ctrl+C 停止适配器")
    
    # 运行适配器
    asyncio.run(run_adapter())
