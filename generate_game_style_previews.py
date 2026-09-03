#!/usr/bin/env python3
"""为新增的热门游戏画风生成预览图"""

import asyncio
from pathlib import Path
from webui.imagegen import generate
from webui.catalog import ART_STYLES

# 只生成新增的热门游戏画风
GAME_STYLES = [
    s for s in ART_STYLES if s.get('group') == '热门游戏'
]

async def generate_style_preview(style: dict, output_dir: Path) -> bool:
    """为单个画风生成预览图"""
    style_id = style['id']
    label = style['label']
    prompt = style.get('prompt', '')
    
    prompt_keyword = prompt.split(',')[0] if prompt else label
    full_prompt = f"pixel art game sprite character, {prompt_keyword}, transparent background, game asset"
    
    print(f"  [{label}] 开始生成...")
    
    try:
        image_bytes = await generate(
            prompt=full_prompt,
            size="1024x1024",
            quality="auto"
        )
        
        if image_bytes:
            output_path = output_dir / f"{style_id}.png"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print(f"  ✓ [{label}] 已保存")
            return True
    except Exception as e:
        print(f"  ✗ [{label}] 失败: {e}")
        return False

async def generate_batch(styles: list, output_dir: Path, batch_num: int, total_batches: int) -> tuple[int, list]:
    """并发生成一批画风"""
    print(f"\n批次 {batch_num}/{total_batches} - 共 {len(styles)} 个画风")
    
    tasks = []
    for style in styles:
        tasks.append(generate_style_preview(style, output_dir))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if r is True)
    failed = [styles[i]['label'] for i, r in enumerate(results) if r is not True]
    
    return success_count, failed

async def main():
    output_dir = Path(__file__).parent / "webui" / "static" / "style_previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"开始为 {len(GAME_STYLES)} 个热门游戏画风生成预览图...")
    print("=" * 60)
    
    batch_size = 5
    batches = [GAME_STYLES[i:i+batch_size] for i in range(0, len(GAME_STYLES), batch_size)]
    
    total_success = 0
    all_failed = []
    
    for i, batch in enumerate(batches, 1):
        success, failed = await generate_batch(batch, output_dir, i, len(batches))
        total_success += success
        all_failed.extend(failed)
    
    print(f"\n{'='*60}")
    print(f"总结: {total_success}/{len(GAME_STYLES)} 成功生成")
    if all_failed:
        print(f"失败: {', '.join(all_failed)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
