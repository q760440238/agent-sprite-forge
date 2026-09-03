#!/usr/bin/env python3
"""生成缺失的画风预览图"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, 'webui')
from catalog import ART_STYLES
from imagegen import generate

async def generate_style_preview(style: dict, output_dir: Path) -> bool:
    """为单个画风生成预览图"""
    style_id = style['id']
    label = style['label']
    prompt = style.get('prompt', '')
    
    print(f"正在生成: {label} ({style_id})...", end=' ', flush=True)
    
    prompt_keyword = prompt.split(',')[0] if prompt else label
    full_prompt = f"2D game art sprite character, {prompt_keyword}, simple clean design, game asset style"
    
    try:
        image_bytes = await generate(
            prompt=full_prompt,
            size="1024x1024",
            quality="auto"
        )
        
        if image_bytes:
            output_path = output_dir / f"{style_id}.webp"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print(f"✓ 成功")
            return True
        else:
            print(f"✗ 失败（无图片数据）")
            return False
    except Exception as e:
        print(f"✗ 失败: {str(e)}")
        return False

async def main():
    output_dir = Path('webui/static/style_previews')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 找出所有缺失的预览图
    missing_styles = []
    for style in ART_STYLES:
        style_id = style['id']
        webp_path = output_dir / f'{style_id}.webp'
        if not webp_path.exists():
            missing_styles.append(style)
    
    if not missing_styles:
        print("✓ 所有预览图都已存在")
        return
    
    print(f"发现 {len(missing_styles)} 个缺失的预览图\n")
    
    # 并发生成所有缺失的预览图
    tasks = [generate_style_preview(style, output_dir) for style in missing_styles]
    results = await asyncio.gather(*tasks)
    
    success_count = sum(results)
    fail_count = len(results) - success_count
    
    print(f"\n生成完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")

if __name__ == "__main__":
    asyncio.run(main())
