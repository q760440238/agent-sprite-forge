#!/usr/bin/env python3
"""生成所有画风的参考图"""

import os
import sys
import time
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from webui.catalog import ART_STYLES
from webui.imagegen import generate


def load_env_config(env_path: str) -> dict:
    """读取 .gptEnv 配置"""
    config = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    return config


async def generate_style_preview(style: dict, output_dir: Path) -> bool:
    """为单个画风生成预览图"""
    style_id = style['id']
    label = style['label']
    prompt = style.get('prompt', '')
    
    # 构建完整的提示词：游戏角色 + 画风描述
    prompt_keyword = prompt.split(',')[0] if prompt else label
    full_prompt = f"pixel art game sprite character, {prompt_keyword}, transparent background, game asset"
    
    print(f"  [{label}] 开始生成...")
    
    try:
        # 调用图像生成（不输出详细日志）
        image_bytes = await generate(
            prompt=full_prompt,
            size="1024x1024",
            quality="auto"
        )
        
        if image_bytes:
            # 保存图片
            output_path = output_dir / f"{style_id}.png"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print(f"  ✓ [{label}] 已保存")
            return True
        else:
            print(f"  ✗ [{label}] 无返回结果")
            return False
            
    except Exception as e:
        print(f"  ✗ [{label}] 失败: {e}")
        return False


async def generate_batch(styles: list, output_dir: Path, batch_num: int, total_batches: int) -> tuple[int, list]:
    """并发生成一批画风"""
    success = 0
    failed = []
    
    print(f"\n批次 {batch_num}/{total_batches} 开始（共 {len(styles)} 个画风）")
    
    tasks = []
    for style in styles:
        tasks.append(generate_style_preview(style, output_dir))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, (style, result) in enumerate(zip(styles, results)):
        if isinstance(result, Exception):
            print(f"  ✗ [{style['label']}] 失败: {result}")
            failed.append(style['label'])
        elif result:
            success += 1
        else:
            failed.append(style['label'])
    
    print(f"批次 {batch_num}/{total_batches} 完成：成功 {success}/{len(styles)}")
    return success, failed


async def main():
    # 读取配置
    env_path = Path(__file__).parent.parent / ".gptEnv"
    if not env_path.exists():
        print(f"错误: 找不到配置文件 {env_path}")
        sys.exit(1)
    
    config = load_env_config(str(env_path))
    print(f"已加载配置: {config.get('base_url', 'N/A')}")
    print(f"模型: {config.get('model', 'N/A')}\n")
    
    # 创建输出目录
    output_dir = Path(__file__).parent / "webui" / "static" / "style_previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}\n")
    
    # 并发生成，分批处理（每批5个）
    total = len(ART_STYLES)
    batch_size = 5
    total_success = 0
    total_failed = []
    
    print(f"开始并发生成 {total} 种画风的参考图（每批 {batch_size} 个）...\n")
    print("=" * 60)
    
    # 分批处理
    batches = [ART_STYLES[i:i + batch_size] for i in range(0, total, batch_size)]
    
    for batch_num, batch in enumerate(batches, 1):
        success, failed = await generate_batch(batch, output_dir, batch_num, len(batches))
        total_success += success
        total_failed.extend(failed)
        
        # 批次之间稍微延迟
        if batch_num < len(batches):
            await asyncio.sleep(1)
    
    # 输出统计
    print("\n" + "=" * 60)
    print(f"\n生成完成！")
    print(f"  成功: {total_success}/{total}")
    print(f"  失败: {len(total_failed)}/{total}")
    
    if total_failed:
        print(f"\n失败的画风:")
        for label in total_failed:
            print(f"  - {label}")


if __name__ == "__main__":
    asyncio.run(main())
