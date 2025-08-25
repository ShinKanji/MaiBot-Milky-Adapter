#!/usr/bin/env python3
"""
测试环境设置脚本
用于准备测试环境
"""

import os
import shutil
from pathlib import Path

def setup_test_environment():
    """设置测试环境"""
    print("设置 MaiBot-Milky-Adapter 测试环境...")
    
    # 检查配置文件
    config_file = Path("config.toml")
    test_config_file = Path("tests/test_config.toml")
    
    if not config_file.exists():
        if test_config_file.exists():
            print("复制测试配置文件...")
            shutil.copy(test_config_file, config_file)
            print("✓ 配置文件已创建，请根据实际情况修改 config.toml")
        else:
            print("⚠ 未找到配置文件模板，请手动创建 config.toml")
    else:
        print("✓ 配置文件已存在")
    
    # 创建数据目录
    data_dir = Path("data")
    if not data_dir.exists():
        print("创建数据目录...")
        data_dir.mkdir(exist_ok=True)
        print("✓ 数据目录已创建")
    else:
        print("✓ 数据目录已存在")
    
    # 检查依赖
    print("\n检查依赖包...")
    try:
        import aiohttp
        print("✓ aiohttp 已安装")
    except ImportError:
        print("✗ aiohttp 未安装，请运行: pip install aiohttp")
    
    try:
        import websockets
        print("✓ websockets 已安装")
    except ImportError:
        print("✗ websockets 未安装，请运行: pip install websockets")
    
    try:
        import tomlkit
        print("✓ tomlkit 已安装")
    except ImportError:
        print("✗ tomlkit 未安装，请运行: pip install tomlkit")
    
    try:
        import loguru
        print("✓ loguru 已安装")
    except ImportError:
        print("✗ loguru 未安装，请运行: pip install loguru")
    
    try:
        import PIL
        print("✓ Pillow 已安装")
    except ImportError:
        print("✗ Pillow 未安装，请运行: pip install Pillow")
    
    # 检查 Milky 服务
    print("\n检查 Milky 服务...")
    print("请确保 Milky 服务正在运行，并且配置的端口可访问")
    
    # 检查 MaiBot 服务
    print("\n检查 MaiBot 服务...")
    print("请确保 MaiBot 服务正在运行，并且配置的端口可访问")
    
    print("\n" + "="*60)
    print("测试环境设置完成！")
    print("="*60)
    print("\n下一步操作：")
    print("1. 修改 config.toml 中的配置（如需要）")
    print("2. 启动 Milky 服务")
    print("3. 启动 MaiBot 服务")
    print("4. 运行测试: python run_tests.py")
    print("\n注意事项：")
    print("- 确保 Milky 和 MaiBot 服务都在运行")
    print("- 检查端口配置是否正确")
    print("- 验证 access_token 是否有效")

if __name__ == "__main__":
    setup_test_environment()
