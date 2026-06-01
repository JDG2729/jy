"""
JSON 驱动的视频生成服务
从 JSON 文件读取素材数据并生成视频（make_video_from_json.py 的逻辑）
"""

import sys
import os
import json
import time
import logging
from typing import Dict, List, Optional
from pathlib import Path

from app.config.settings import MATERIAL_BASE_DIR
from app.services.material_service import download_file, save_text
from app.core.jianying import call_jianying_automation

logger = logging.getLogger(__name__)


def download_materials_from_json(material_data: Dict, record_id: str) -> Optional[Dict]:
    """
    从JSON格式的素材数据下载所有素材到本地
    """
    import shutil

    try:
        material_dir = f"{MATERIAL_BASE_DIR}/{record_id}"

        if os.path.exists(material_dir):
            logger.warning(f"   ⚠️ 素材文件夹已存在，先清理旧文件: {material_dir}")
            try:
                shutil.rmtree(material_dir, ignore_errors=True)
                logger.info(f"   ✅ 已清理旧文件夹")
            except Exception as e:
                logger.warning(f"   ⚠️ 清理旧文件夹失败: {e}")

        output_dirs = {
            "cover": f"{material_dir}/cover",
            "audio": f"{material_dir}/audio",
            "image": f"{material_dir}/image",
            "subtitles": f"{material_dir}/subtitles",
            "background": f"{material_dir}/background"
        }

        for dir_path in output_dirs.values():
            os.makedirs(dir_path, exist_ok=True)

        logger.info(f"📁 已为记录 {record_id} 创建素材文件夹: {material_dir}")

        success_count = 0
        total_count = 0

        all_fengmian = material_data.get('fengmian', [])
        all_langdu = material_data.get('langdu', [])
        all_tupian = material_data.get('tupian', [])
        all_zimu = material_data.get('zimu', [])
        all_beijing_pic = material_data.get('beijing_pic', [])
        all_content = material_data.get('content', [])
        yn_koutu_value = material_data.get('yn_koutu', 'no').lower()

        if not isinstance(all_fengmian, list):
            all_fengmian = [all_fengmian] if all_fengmian else []
        if not isinstance(all_langdu, list):
            all_langdu = [all_langdu] if all_langdu else []
        if not isinstance(all_tupian, list):
            all_tupian = [all_tupian] if all_tupian else []
        if not isinstance(all_zimu, list):
            all_zimu = [all_zimu] if all_zimu else []
        if not isinstance(all_beijing_pic, list):
            all_beijing_pic = [all_beijing_pic] if all_beijing_pic else []

        cover_count = len(all_fengmian)
        audio_count = len(all_langdu)
        image_count = len(all_tupian)
        subtitle_count = len(all_zimu)
        background_count = len(all_beijing_pic) if yn_koutu_value == 'yes' else 0
        total_expected = cover_count + audio_count + image_count + subtitle_count + background_count

        logger.info(f"   📊 素材统计: 封面={cover_count}, 音频={audio_count}, 图片={image_count}, 字幕={subtitle_count}, 背景={background_count}, 总计={total_expected}")

        # 下载封面
        if all_fengmian:
            logger.info(f"   📷 下载封面 ({cover_count} 个)...")
            for i, cover_url in enumerate(all_fengmian):
                if cover_url:
                    total_count += 1
                    filename = "cover.png" if i == 0 else f"cover_{i + 1}.png"
                    success, _ = download_file(cover_url, output_dirs["cover"], filename)
                    if success:
                        success_count += 1

        # 下载音频
        if all_langdu:
            logger.info(f"   🎵 下载音频 ({audio_count} 个)...")
            for i, audio_url in enumerate(all_langdu):
                if audio_url:
                    total_count += 1
                    success, _ = download_file(audio_url, output_dirs["audio"], f"{i + 1}.mp3")
                    if success:
                        success_count += 1
                        if i < len(all_langdu) - 1:
                            time.sleep(0.3)

        # 下载图片
        if all_tupian:
            logger.info(f"   🖼️  下载图片 ({image_count} 个)...")
            for i, image_url in enumerate(all_tupian):
                if image_url:
                    total_count += 1
                    import re
                    scene_match = re.search(r'scene_(\d+)', image_url, re.IGNORECASE)
                    if scene_match:
                        scene_num = int(scene_match.group(1))
                        filename = f"{scene_num}.jpg"
                    else:
                        filename = f"{i + 1}.jpg"
                    success, _ = download_file(image_url, output_dirs["image"], filename)
                    if success:
                        success_count += 1
                        if i < len(all_tupian) - 1:
                            time.sleep(0.5)

        # 保存字幕
        if all_zimu:
            logger.info(f"   📝 保存字幕 ({subtitle_count} 个)...")
            for i, subtitle_text in enumerate(all_zimu):
                if subtitle_text:
                    total_count += 1
                    if save_text(str(subtitle_text), output_dirs["subtitles"], f"{i + 1}.txt"):
                        success_count += 1

        # 下载背景图片
        if yn_koutu_value == 'yes' and all_beijing_pic:
            logger.info(f"   🖼️  下载背景图片 ({background_count} 个)...")
            for i, background_url in enumerate(all_beijing_pic):
                if background_url:
                    total_count += 1
                    success, _ = download_file(background_url, output_dirs["background"], f"{i + 1}.jpg")
                    if success:
                        success_count += 1

        if all_content:
            logger.info(f"   📋 场景信息: {len(all_content)} 个场景")

        if success_count == total_expected:
            logger.info(f"✅ 素材下载完成: {success_count}/{total_count} 成功")
            return {
                'material_dir': material_dir,
                'yn_koutu': yn_koutu_value,
                'content': all_content
            }
        else:
            failed_count = total_count - success_count
            logger.error(f"❌ 素材有 {failed_count} 个未成功下载")
            return None

    except Exception as e:
        logger.error(f"❌ 下载素材失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_json_material(material_item: Dict, output_base_dir: str = None) -> Dict:
    """处理JSON中的一条素材记录"""
    start_time = time.time()
    index = material_item.get('index', 0)
    original_record = material_item.get('original_record', {})
    generated_material = material_item.get('generated_material', {})

    title = original_record.get('title', f'video_{index}')
    content_type = original_record.get('content_type', '')
    fengge = original_record.get('fengge', '')
    task_id = original_record.get('task_id', f'task_{index}')
    record_id = task_id

    try:
        logger.info(f"🚀 开始处理记录 {index}: {title}")
        logger.info(f"   📋 content_type: {content_type}, fengge: {fengge}")

        logger.info(f"📥 开始下载素材...")
        download_result = download_materials_from_json(generated_material, record_id)

        if not download_result:
            logger.error(f"❌ 素材下载失败")
            return {
                'index': index, 'status': 'failed',
                'error': '素材下载失败', 'duration': time.time() - start_time
            }

        material_dir = download_result['material_dir']
        yn_koutu = download_result.get('yn_koutu', 'no')
        content = download_result.get('content', [])

        # 根据content_type确定growth_category
        growth_category = None
        if content_type:
            if '减脂' in content_type or '减肥' in content_type:
                growth_category = '减脂'
            elif '养生' in content_type:
                growth_category = '养生'
            elif '护肤' in content_type:
                growth_category = '护肤'

        logger.info(f"🎬 开始剪映自动化剪辑...")
        video_path = call_jianying_automation(
            material_dir, record_id, title,
            yn_koutu=yn_koutu, content=content,
            content_type=content_type, growth_category=growth_category
        )

        if not video_path:
            logger.error(f"❌ 剪映剪辑失败")
            return {
                'index': index, 'status': 'failed',
                'error': '剪映剪辑失败', 'duration': time.time() - start_time
            }

        # 导出成功后删除素材文件夹
        try:
            import shutil
            if os.path.exists(material_dir):
                shutil.rmtree(material_dir, ignore_errors=False)
                logger.info(f"🗑️ [清理] 已删除素材文件夹: {material_dir}")
        except Exception as cleanup_err:
            logger.warning(f"⚠️ [清理] 删除素材文件夹失败: {cleanup_err}")

        duration = time.time() - start_time
        logger.info(f"✅ 记录 {index} 视频生成完成 - 耗时: {duration:.2f}s")

        return {
            'index': index, 'status': 'success',
            'video_path': video_path, 'duration': duration
        }

    except Exception as e:
        logger.error(f"❌ 处理记录 {index} 失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'index': index, 'status': 'error',
            'error': str(e), 'duration': time.time() - start_time
        }


def main_json_mode():
    """JSON 模式入口"""
    import argparse

    parser = argparse.ArgumentParser(description='从JSON文件读取素材数据并生成视频')
    parser.add_argument('json_file', type=str, help='JSON文件路径')
    parser.add_argument('--index', type=int, default=None, help='只处理指定索引的记录')
    parser.add_argument('--count', type=int, default=None, help='最多处理多少条记录')
    parser.add_argument('--retry-failed', action='store_true', help='重新运行失败的记录')

    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        logger.error(f"❌ JSON文件不存在: {json_path}")
        return

    logger.info(f"📖 读取JSON文件: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    metadata = data.get('metadata', {})
    materials = data.get('materials', [])

    logger.info(f"📊 JSON文件信息:")
    logger.info(f"   总记录数: {metadata.get('total_records', len(materials))}")
    logger.info(f"   成功记录数: {metadata.get('success_count', 0)}")
    logger.info(f"   实际materials数量: {len(materials)}")

    # 确定要处理的记录
    if args.retry_failed:
        failed_file = json_path.parent / f"{json_path.stem}_failed_indices.json"
        if not failed_file.exists():
            logger.error(f"❌ 失败索引文件不存在: {failed_file}")
            return
        with open(failed_file, 'r', encoding='utf-8') as f:
            failed_data = json.load(f)
            failed_indices = failed_data.get('failed_indices', [])
        if not failed_indices:
            logger.info(f"✅ 没有失败的记录需要重新运行")
            return
        materials_to_process = [materials[idx] for idx in failed_indices if idx < len(materials)]
        logger.info(f"🔄 重新运行 {len(materials_to_process)} 条失败的记录")
    elif args.index is not None:
        if args.index < len(materials):
            materials_to_process = [materials[args.index]]
        else:
            logger.error(f"❌ 索引 {args.index} 超出范围")
            return
    elif args.count is not None:
        materials_to_process = materials[:args.count]
    else:
        materials_to_process = materials

    # 处理
    results = []
    failed_indices = []

    for i, material in enumerate(materials_to_process):
        logger.info(f"\n{'=' * 80}")
        logger.info(f"处理进度: {i+1}/{len(materials_to_process)}")
        logger.info(f"{'=' * 80}")

        result = process_json_material(material)
        results.append(result)

        if result['status'] == 'success':
            logger.info(f"✅ 记录 {result['index']} 处理成功")
        else:
            logger.error(f"❌ 记录 {result['index']} 处理失败: {result.get('error', '未知错误')}")
            failed_indices.append(result['index'])

    # 统计
    logger.info(f"\n{'=' * 80}")
    logger.info(f"处理完成 - 统计报告")
    logger.info(f"{'=' * 80}")
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] != 'success')
    logger.info(f"✅ 成功: {success_count} 条")
    logger.info(f"❌ 失败: {failed_count} 条")
    logger.info(f"📊 成功率: {success_count/len(results)*100:.1f}%")

    if failed_indices:
        failed_file = json_path.parent / f"{json_path.stem}_failed_indices.json"
        with open(failed_file, 'w', encoding='utf-8') as f:
            json.dump({'failed_indices': failed_indices}, f, indent=2, ensure_ascii=False)
        logger.info(f"📝 失败记录索引已保存到: {failed_file}")
