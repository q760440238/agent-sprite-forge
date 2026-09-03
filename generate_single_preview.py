#!/usr/bin/env python3
"""生成单个预览图"""

import asyncio
from pathlib import Path
from webui.imagegen import generate

async def main():
    """主函数"""
    style_id = "realistic_resident_evil"
    label = "生化危机"
    prompt = "photorealistic survival action movie style, bio-hazard laboratory environment, protective tactical gear, cinematic quality, high detail"
    
    print(f"正在生成: {label} ({style_id})... ", end='', flush=True)
    
    try:
        image_bytes = await generate(
            prompt=prompt,
            size="1024x1024",
            quality="auto"
        )
        
        if image_bytes:
            output_path = Path("webui/static/style_previews") / f"{style_id}.webp"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print("✓ 成功")
        else:
            print("✗ 失败: 未返回图片数据")
            
    except Exception as e:
        print(f"✗ 失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
