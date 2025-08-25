#!/usr/bin/env python3
"""
MaiBot-Milky-Adapter 测试运行器
从项目根目录运行所有测试
"""

import asyncio
import sys
import os
import subprocess
from pathlib import Path

def run_test_file(test_file: str):
    """运行单个测试文件"""
    test_path = Path("tests") / test_file
    if not test_path.exists():
        print(f"✗ 测试文件不存在: {test_path}")
        return False
    
    print(f"\n{'='*60}")
    print(f"运行测试: {test_file}")
    print(f"{'='*60}")
    
    try:
        # 使用 subprocess 运行测试，确保环境正确
        result = subprocess.run([
            sys.executable, str(test_path)
        ], capture_output=True, text=True, cwd=Path.cwd())
        
        if result.returncode == 0:
            print(f"✓ {test_file} 测试通过")
            if result.stdout:
                print("输出:")
                print(result.stdout)
        else:
            print(f"✗ {test_file} 测试失败 (返回码: {result.returncode})")
            if result.stderr:
                print("错误输出:")
                print(result.stderr)
            if result.stdout:
                print("标准输出:")
                print(result.stdout)
            return False
            
    except Exception as e:
        print(f"✗ 运行 {test_file} 时发生错误: {e}")
        return False
    
    return True

def main():
    """主函数：运行所有测试"""
    print("MaiBot-Milky-Adapter 测试套件")
    print("=" * 60)
    
    # 测试文件列表
    test_files = [
        "test_api.py",                    # 测试 API 调用
        "test_milky.py",                  # 测试 Milky 通信层
        "test_milky_api_compliance.py",   # 测试 API 合规性
        "test_websocket_compliance.py",   # 测试 WebSocket 合规性
    ]
    
    passed = 0
    failed = 0
    
    for test_file in test_files:
        if run_test_file(test_file):
            passed += 1
        else:
            failed += 1
    
    # 测试结果汇总
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"总计: {len(test_files)}")
    
    if failed == 0:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n❌ 有 {failed} 个测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
