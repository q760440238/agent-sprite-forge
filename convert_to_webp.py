#!/usr/bin/env python3
"""将所有预览图转换为WebP格式"""

from pathlib import Path
from PIL import Image
import sys

def convert_to_webp(input_dir: Path, quality: int = 75, max_size: int = 512):
    """转换目录下所有图片文件为WebP格式，并压缩尺寸"""
    # 支持多种图片格式
    image_files = []
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG', '*.webp']:
        image_files.extend(input_dir.glob(ext))
    png_files = image_files
    
    if not png_files:
        print("未找到图片文件")
        return
    
    print(f"找到 {len(png_files)} 个图片文件")
    print("=" * 60)
    
    success_count = 0
    failed = []
    
    for png_path in png_files:
        try:
            webp_path = png_path.with_suffix('.webp')
            
            # 如果已经是WebP格式，需要重新压缩
            if png_path.suffix.lower() == '.webp':
                # 创建临时文件名
                temp_path = png_path.with_suffix('.webp.tmp')
                
                # 打开并重新压缩WebP
                with Image.open(png_path) as img:
                    # 压缩尺寸：如果图片较大，缩小到max_size
                    if img.width > max_size or img.height > max_size:
                        original_size_val = (img.width, img.height)
                        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                        print(f"  缩放: {original_size_val} -> {img.size}")
                    
                    # 如果有透明通道，保留它
                    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                        img.save(temp_path, 'WEBP', quality=quality, lossless=False)
                    else:
                        img.save(temp_path, 'WEBP', quality=quality)
                
                # 检查文件大小
                original_size = png_path.stat().st_size / 1024  # KB
                webp_size = temp_path.stat().st_size / 1024  # KB
                reduction = (1 - webp_size / original_size) * 100
                
                print(f"✓ {png_path.name} 重新压缩 ({original_size:.1f}KB -> {webp_size:.1f}KB, 减少 {reduction:.1f}%)")
                success_count += 1
                
                # 替换原文件
                png_path.unlink()
                temp_path.rename(png_path)
                continue
            
            # 打开图片并转换为WebP
            with Image.open(png_path) as img:
                # 压缩尺寸：如果图片较大，缩小到max_size
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # 如果有透明通道，保留它
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img.save(webp_path, 'WEBP', quality=quality, lossless=False)
                else:
                    img.save(webp_path, 'WEBP', quality=quality)
            
            # 检查文件大小
            original_size = png_path.stat().st_size / 1024  # KB
            webp_size = webp_path.stat().st_size / 1024  # KB
            reduction = (1 - webp_size / original_size) * 100
            
            print(f"✓ {png_path.name} -> {webp_path.name} ({original_size:.1f}KB -> {webp_size:.1f}KB, 减少 {reduction:.1f}%)")
            success_count += 1
            
            # 删除原文件
            png_path.unlink()
            
        except Exception as e:
            print(f"✗ {png_path.name} 失败: {e}")
            failed.append(png_path.name)
    
    print("=" * 60)
    print(f"总结: {success_count}/{len(png_files)} 成功转换")
    if failed:
        print(f"失败: {', '.join(failed)}")
    print("=" * 60)

if __name__ == "__main__":
    import sys
    
    # 支持命令行参数指定目录
    if len(sys.argv) > 1:
        preview_dir = Path(sys.argv[1])
    else:
        preview_dir = Path(__file__).parent / "webui" / "static" / "style_previews"
    
    if not preview_dir.exists():
        print(f"目录不存在: {preview_dir}")
        sys.exit(1)
    
    print(f"处理目录: {preview_dir.absolute()}")
    convert_to_webp(preview_dir)
