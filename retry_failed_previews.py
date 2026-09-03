#!/usr/bin/env python3
"""重新生成之前失败的画风预览图（使用优化后的提示词）"""

import asyncio
from pathlib import Path
from webui.imagegen import generate
from webui.catalog import ART_STYLES

# 只生成之前失败的6个画风
FAILED_STYLES = [
    s for s in ART_STYLES 
    if s['id'] in ['isaac', 'pokemon', 'horror_silent_hill', 'horror_outlast', 'horror_layers_fear', 'horror_dead_by_daylight']
]

async def generate_style_preview(style: dict, output_dir: Path) -> bool:
    """为单个画风生成预览图"""
    style_id = style['id']
    label = style['label']
    prompt = style.get('prompt', '')
    
    prompt_keyword = prompt.split(',')[0] if prompt else label
    full_prompt = f"pixel art game sprite character, {prompt_keyword}, transparent background, game asset"
    
    print(f"  [{label}] 开始生成...")
    print(f"    提示词: {prompt[:80]}...")
    
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
            print(f"  ✓ [{label}] 已保存")
            return True
    except Exception as e:
        print(f"  ✗ [{label}] 失败: {e}")
        return False

async def main():
    output_dir = Path(__file__).parent / "webui" / "static" / "style_previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"使用优化后的提示词重新生成 {len(FAILED_STYLES)} 个失败画风...")
    print("=" * 60)
    
    tasks = []
    for style in FAILED_STYLES:
        tasks.append(generate_style_preview(style, output_dir))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if r is True)
    failed = [FAILED_STYLES[i]['label'] for i, r in enumerate(results) if r is not True]
    
    print(f"\n{'='*60}")
    print(f"总结: {success_count}/{len(FAILED_STYLES)} 成功生成")
    if failed:
        print(f"仍然失败: {', '.join(failed)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
