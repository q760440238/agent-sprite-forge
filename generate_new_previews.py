#!/usr/bin/env python3
"""生成指定ID的预览图"""

import asyncio
from pathlib import Path
from webui.catalog import ART_STYLES
from webui.imagegen import generate

TARGET_IDS = [
    "realistic_urban_supernatural",
    "realistic_ancient_supernatural",
    "realistic_chinese_battlefield",
    "realistic_european_battlefield",
    "realistic_warcraft",
    "realistic_heroes_might_magic",
]

async def generate_style_preview(style: dict, output_dir: Path) -> bool:
    """生成单个画风的预览图"""
    style_id = style['id']
    label = style['label']
    prompt = style.get('prompt', '')
    
    print(f"正在生成: {label} ({style_id})... ", end='', flush=True)
    
    try:
        image_bytes = await generate(
            prompt=prompt,
            size="1024x1024",
            quality="auto"
        )
        
        if image_bytes:
            output_path = output_dir / f"{style_id}.webp"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print("✓ 成功")
            return True
        else:
            print("✗ 失败: 未返回图片数据")
            return False
            
    except Exception as e:
        print(f"✗ 失败: {str(e)}")
        return False

async def main():
    """主函数"""
    output_dir = Path("webui/static/style_previews")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    target_styles = [s for s in ART_STYLES if s['id'] in TARGET_IDS]
    
    print(f"需要生成 {len(target_styles)} 个预览图\n")
    
    tasks = [generate_style_preview(style, output_dir) for style in target_styles]
    results = await asyncio.gather(*tasks)
    
    success_count = sum(results)
    failed_count = len(results) - success_count
    
    print(f"\n生成完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {failed_count}")

if __name__ == "__main__":
    asyncio.run(main())
