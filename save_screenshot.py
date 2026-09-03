#!/usr/bin/env python3
"""
使用websocket连接Chrome DevTools获取截图
"""
import asyncio
import websockets
import json
import base64
import sys

async def capture_screenshot():
    # 连接到Chrome DevTools
    async with websockets.connect('ws://localhost:9222/devtools/page/1') as ws:
        # 发送截图命令
        await ws.send(json.dumps({
            "id": 1,
            "method": "Page.captureScreenshot",
            "params": {
                "format": "webp",
                "quality": 85,
                "fromSurface": True
            }
        }))
        
        # 接收响应
        response = await ws.recv()
        result = json.loads(response)
        
        if 'result' in result and 'data' in result['result']:
            # 解码base64并保存
            image_data = base64.b64decode(result['result']['data'])
            with open('/Users/kylin/Documents/easywork/agent-sprite-forge/docs/webui-main.webp', 'wb') as f:
                f.write(image_data)
            print(f"截图已保存，大小: {len(image_data)/1024:.1f}KB")
            return True
        else:
            print(f"截图失败: {result}")
            return False

if __name__ == '__main__':
    try:
        result = asyncio.run(capture_screenshot())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)
