"""
剪映自动化核心模块
负责创建剪映草稿、添加轨道、添加素材、导出视频
"""

import os
import json
import time
import random
import shutil
import logging
import subprocess
import threading
from typing import Dict, Any, Optional, List

from app.config.settings import (
    JIANYING_DRAFT_PATH, JIANYING_EXE_PATH,
    BGM_DIR, BGM_VOLUME, VIDEO_EXPORT_DIR
)
from app.utils.dialog_handler import detect_and_close_error_dialog
from app.utils.process_manager import close_all_jianying_processes, HAS_PSUTIL

logger = logging.getLogger(__name__)

# 按需导入
import importlib.util
if HAS_PSUTIL:
    psutil = importlib.import_module("psutil")

# 草稿清理队列
drafts_pending_cleanup = set()


def queue_draft_for_cleanup(draft_name: str):
    """记录需要清理的草稿"""
    if draft_name:
        drafts_pending_cleanup.add(draft_name)


def cleanup_pending_drafts():
    """批量清理已记录的草稿"""
    if not drafts_pending_cleanup:
        return
    logger.info(f"🧹 开始批量清理草稿，共 {len(drafts_pending_cleanup)} 个")
    for draft_name in list(drafts_pending_cleanup):
        _delete_draft(draft_name)


def _delete_draft(draft_name: str) -> bool:
    """删除剪映草稿文件夹"""
    try:
        draft_dir = os.path.join(JIANYING_DRAFT_PATH, draft_name)
        if os.path.exists(draft_dir) and os.path.isdir(draft_dir):
            shutil.rmtree(draft_dir)
            logger.info(f"   🗑️  已删除草稿文件夹: {draft_name}")
            drafts_pending_cleanup.discard(draft_name)
            return True
        else:
            logger.debug(f"   ⚠️ 草稿文件夹不存在: {draft_dir}")
            drafts_pending_cleanup.discard(draft_name)
            return False
    except Exception as e:
        logger.warning(f"   ⚠️ 删除草稿文件夹失败: {e}")
        drafts_pending_cleanup.discard(draft_name)
        return False


def get_random_bgm() -> Optional[str]:
    """从 BGM 目录中随机选择一首背景音乐"""
    try:
        if not os.path.exists(BGM_DIR) or not os.path.isdir(BGM_DIR):
            logger.warning(f"   ⚠️ BGM 目录不存在: {BGM_DIR}")
            return None

        audio_extensions = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg')
        bgm_files = [f for f in os.listdir(BGM_DIR)
                     if f.lower().endswith(audio_extensions)]

        if not bgm_files:
            logger.warning(f"   ⚠️ BGM 目录中没有找到音频文件: {BGM_DIR}")
            return None

        selected_bgm = random.choice(bgm_files)
        bgm_path = os.path.join(BGM_DIR, selected_bgm)
        logger.info(f"   🎵 随机选择 BGM: {selected_bgm}")
        return bgm_path

    except Exception as e:
        logger.warning(f"   ⚠️ 获取 BGM 失败: {e}")
        return None


def _copy_cover_image(material_dir: str, video_output_dir: str, record_id):
    """复制封面图片到视频导出文件夹"""
    try:
        cover_source = os.path.join(material_dir, "cover", "cover.png")
        cover_dest = os.path.join(video_output_dir, f"{record_id}.png")

        if os.path.exists(cover_source):
            shutil.copy2(cover_source, cover_dest)
            logger.info(f"   📷 已复制封面图片: {cover_dest}")
        else:
            logger.debug(f"   ⚠️ 封面图片不存在: {cover_source}")
    except Exception as e:
        logger.warning(f"   ⚠️ 复制封面图片失败: {e}")


def call_jianying_automation(
    material_dir: str, record_id: int, title: str,
    yn_koutu: str = "no", content: List[Dict] = None,
    content_type: Optional[str] = None,
    growth_category: Optional[str] = None
) -> Optional[str]:
    """
    调用剪映自动化工具进行视频剪辑

    Returns:
        导出视频的路径，失败返回 None
    """
    try:
        import pyJianYingDraft as draft
        from pyJianYingDraft import trange, TrackType, VideoSegment, AudioSegment, TextSegment, AudioMaterial
        from pyJianYingDraft import TextStyle, TextBorder, FontType, ClipSettings, KeyframeProperty
        from pyJianYingDraft import TextIntro, TextOutro, IntroType, OutroType, TransitionType, tim

        from video_config import get_style_config

        style_config = get_style_config(yn_koutu=yn_koutu, growth_category=growth_category)
        logger.info(f"🎨 使用视频配置: {style_config['display_name']} (类型={growth_category or '未指定'}, 风格={'有背景' if yn_koutu.lower() == 'yes' else '无背景'})")

        video_width = style_config['video']['width']
        video_height = style_config['video']['height']
        subtitle_config = style_config['subtitle']
        image_config = style_config.get('image', {})
        audio_config = style_config.get('audio', {})
        features = style_config.get('features', {})
        effects_config = style_config.get('effects', {})

        # 字体映射
        def get_font_type(font_name: str):
            font_name_variants = {
                '抖音美好体': ['抖音美好体'],
                '得意黑': ['得意黑'],
                '阿里妈妈数黑体 Bold': [
                    '阿里妈妈数黑体_Bold', '阿里妈妈数黑体Bold',
                    '阿里妈妈数黑体', '数黑体',
                ],
            }
            variants = font_name_variants.get(font_name, ['得意黑'])
            for attr_name in variants:
                try:
                    font_type = getattr(FontType, attr_name)
                    if font_type is not None:
                        return font_type
                except AttributeError:
                    continue
            logger.warning(f"   ⚠️ 未找到字体 '{font_name}'，使用默认字体 '得意黑'")
            return FontType.得意黑

        font_type_name = style_config['fonts'].get('default_font', '得意黑')
        try:
            font_type = get_font_type(font_type_name)
        except Exception as e:
            logger.warning(f"⚠️ 字体映射失败: {e}，使用默认字体 '得意黑'")
            font_type = FontType.得意黑

        # 特效映射
        def get_text_intro(effect_name: str):
            if not effect_name or effect_name.lower() in ['无', 'none', '']:
                return None
            try:
                return getattr(TextIntro, effect_name)
            except AttributeError:
                logger.warning(f"⚠️ 未找到文字入场动画 '{effect_name}'")
                return None

        def get_text_outro(effect_name: str):
            if not effect_name or effect_name.lower() in ['无', 'none', '']:
                return None
            try:
                return getattr(TextOutro, effect_name)
            except AttributeError:
                return None

        def get_video_intro(effect_name: str):
            if not effect_name or effect_name.lower() in ['无', 'none', '']:
                return None
            try:
                return getattr(IntroType, effect_name)
            except AttributeError:
                return None

        def get_video_outro(effect_name: str):
            if not effect_name or effect_name.lower() in ['无', 'none', '']:
                return None
            try:
                return getattr(OutroType, effect_name)
            except AttributeError:
                return None

        def get_video_transition(effect_name: str):
            if not effect_name or effect_name.lower() in ['无', 'none', '']:
                return None
            try:
                return getattr(TransitionType, effect_name)
            except AttributeError:
                return None

        logger.info(f"🎬 开始剪映自动化剪辑...")

        draft_name = None

        cover_dir = f"{material_dir}/cover"
        audio_dir = f"{material_dir}/audio"
        image_dir = f"{material_dir}/image"
        subtitle_dir = f"{material_dir}/subtitles"
        background_dir = f"{material_dir}/background"

        video_output_dir = f"{VIDEO_EXPORT_DIR}/{record_id}"
        os.makedirs(video_output_dir, exist_ok=True)

        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:30]
        draft_name = f"video_{record_id}_{int(time.time())}"
        queue_draft_for_cleanup(draft_name)

        logger.info(f"   📝 草稿名称: {draft_name}")

        draft_dir = os.path.join(JIANYING_DRAFT_PATH, draft_name)
        if os.path.exists(draft_dir):
            shutil.rmtree(draft_dir)
            logger.debug(f"   已删除旧草稿: {draft_name}")

        draft_folder = draft.DraftFolder(JIANYING_DRAFT_PATH)
        script = draft_folder.create_draft(draft_name, video_width, video_height)
        logger.info(f"   📐 视频尺寸: {video_width}x{video_height}")

        background_files = sorted([f for f in os.listdir(background_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]) if os.path.isdir(background_dir) else []
        has_background = len(background_files) > 0

        if has_background:
            script.add_track(TrackType.video, "背景")
            script.add_track(TrackType.video, "内容")
            logger.info(f"   📹 添加背景轨道和内容轨道")
        else:
            script.add_track(TrackType.video)
        script.add_track(TrackType.audio, "主音频")
        script.add_track(TrackType.audio, "背景音乐")
        logger.info(f"   🎵 已创建背景音乐轨道")
        script.add_track(TrackType.text, "字幕主")
        script.add_track(TrackType.text, "免责声明")

        current_total_duration = 0.0
        one_frame_duration = 1/30.0  # COVER_CONFIG duration

        # 添加封面
        cover_files = sorted([f for f in os.listdir(cover_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]) if os.path.isdir(cover_dir) else []
        if cover_files:
            cover_path = os.path.join(cover_dir, cover_files[0])
            logger.info(f"   ✅ 添加封面: {cover_files[0]}")
            cover_segment = VideoSegment(cover_path, target_timerange=trange(0, f"{one_frame_duration}s"))
            if has_background:
                script.add_segment(cover_segment, track_name="内容")
            else:
                script.add_segment(cover_segment)
            current_total_duration = one_frame_duration * 1000000
        else:
            logger.info("   ⚠️ 未找到封面图片")

        # 获取音频和图片文件列表
        if os.path.isdir(audio_dir):
            audio_files = sorted([f for f in os.listdir(audio_dir) if f.lower().endswith('.mp3')])
        else:
            audio_files = []
            logger.error(f"   ❌ 音频目录不存在: {audio_dir}")

        if os.path.isdir(image_dir):
            import re as _re
            def extract_number(filename):
                match = _re.search(r'(\d+)', filename)
                return int(match.group(1)) if match else 0
            image_files = sorted(
                [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))],
                key=extract_number
            )
        else:
            image_files = []
            logger.error(f"   ❌ 图片目录不存在: {image_dir}")

        num_audio_files = len(audio_files)
        num_image_files = len(image_files)
        logger.info(f"   ✅ 添加音频 {num_audio_files} 个，图片 {num_image_files} 张...")

        use_scene_grouping = content and len(content) > 0 and num_image_files > 0

        if use_scene_grouping:
            logger.info(f"   📋 使用场景分组模式: {len(content)} 个场景")
            sorted_content = sorted(content, key=lambda x: x.get('scene_number', 0))
            current_audio_index = 1

            for scene_idx, scene in enumerate(sorted_content):
                scene_number = scene.get('scene_number', scene_idx + 1)
                segments = scene.get('segments', [])
                num_segments = len(segments)
                if num_segments == 0:
                    continue

                image_filename = f"{scene_number}.jpg"
                current_image_path = os.path.join(image_dir, image_filename)

                if not os.path.exists(current_image_path):
                    if num_image_files > 0:
                        image_index = (scene_number - 1) % num_image_files
                        if image_index < len(image_files):
                            current_image_path = os.path.join(image_dir, image_files[image_index])
                        else:
                            continue
                    else:
                        continue

                if not os.path.exists(current_image_path):
                    continue

                logger.info(f"   🎬 场景 {scene_number}: 图片={os.path.basename(current_image_path)}, 音频/字幕={num_segments}个")

                scene_total_duration = 0.0
                scene_audio_durations = []
                scene_start_time = current_total_duration

                for seg_idx in range(num_segments):
                    audio_idx = current_audio_index + seg_idx
                    if audio_idx > num_audio_files:
                        break
                    audio_path = os.path.join(audio_dir, f"{audio_idx}.mp3")
                    if os.path.exists(audio_path):
                        audio_dur = AudioMaterial(audio_path).duration
                        scene_audio_durations.append(audio_dur)
                        scene_total_duration += audio_dur

                if scene_total_duration > 0 and num_image_files > 0:
                    img_segment = VideoSegment(
                        current_image_path,
                        target_timerange=trange(scene_start_time, scene_total_duration)
                    )
                    if 'scale' in image_config:
                        scale_value = image_config.get('scale', 1.0)
                        img_segment.add_keyframe(KeyframeProperty.scale_x, 0, scale_value)
                        img_segment.add_keyframe(KeyframeProperty.scale_y, 0, scale_value)
                    else:
                        scale_start = image_config.get('scale_start', 1.0)
                        scale_end = image_config.get('scale_end', 1.3)
                        img_segment.add_keyframe(KeyframeProperty.scale_x, 0, scale_start)
                        img_segment.add_keyframe(KeyframeProperty.scale_y, 0, scale_start)
                        img_segment.add_keyframe(KeyframeProperty.scale_x, scene_total_duration, scale_end)
                        img_segment.add_keyframe(KeyframeProperty.scale_y, scene_total_duration, scale_end)

                    video_intro = get_video_intro(effects_config.get('video_intro', ''))
                    if video_intro:
                        img_segment.add_animation(video_intro)
                    video_outro = get_video_outro(effects_config.get('video_outro', ''))
                    if video_outro:
                        img_segment.add_animation(video_outro)
                    video_transition = get_video_transition(effects_config.get('video_transition', ''))
                    if video_transition:
                        img_segment.add_transition(video_transition)

                    if has_background:
                        script.add_segment(img_segment, track_name="内容")
                    else:
                        script.add_segment(img_segment)

                for seg_idx in range(num_segments):
                    audio_idx = current_audio_index + seg_idx
                    if audio_idx > num_audio_files:
                        break

                    audio_path = os.path.join(audio_dir, f"{audio_idx}.mp3")
                    if not os.path.exists(audio_path):
                        logger.warning(f"      ⚠️ 跳过，未找到音频文件 {audio_idx}.mp3")
                        continue

                    segment_start_time = current_total_duration
                    audio_duration = scene_audio_durations[seg_idx] if seg_idx < len(scene_audio_durations) else AudioMaterial(audio_path).duration

                    audio_volume = audio_config.get('bgm_volume', 1.0)
                    script.add_segment(
                        AudioSegment(audio_path, target_timerange=trange(segment_start_time, audio_duration), volume=audio_volume),
                        track_name="主音频"
                    )

                    if has_background:
                        background_index = (audio_idx - 1) % len(background_files)
                        background_path = os.path.join(background_dir, background_files[background_index])
                        bg_segment = VideoSegment(background_path, target_timerange=trange(segment_start_time, audio_duration))
                        script.add_segment(bg_segment, track_name="背景")

                    text_content = None
                    if seg_idx < len(segments) and segments[seg_idx]:
                        text_content = str(segments[seg_idx]).strip()
                    else:
                        subtitle_path = os.path.join(subtitle_dir, f"{audio_idx}.txt")
                        if os.path.exists(subtitle_path):
                            with open(subtitle_path, 'r', encoding='utf-8') as f:
                                text_content = f.read().strip()

                    if text_content:
                        target_track = "字幕主"
                        base_position_y = subtitle_config.get('position_y', -0.3)
                        text_style = TextStyle(
                            size=subtitle_config.get('font_size', 40.0),
                            color=tuple(subtitle_config.get('color', (1.0, 1.0, 1.0))),
                            auto_wrapping=subtitle_config.get('auto_wrap', True),
                            max_line_width=subtitle_config.get('max_line_width', 0.85),
                            align=subtitle_config.get('align', 1)
                        )
                        text_border = TextBorder(
                            color=tuple(subtitle_config.get('border_color', (0.0, 0.0, 0.0))),
                            width=subtitle_config.get('border_width', 2.0)
                        )
                        text_segment = TextSegment(
                            text_content,
                            trange(segment_start_time, audio_duration),
                            font=font_type,
                            style=text_style,
                            border=text_border,
                            clip_settings=ClipSettings(transform_y=base_position_y)
                        )
                        text_intro = get_text_intro(effects_config.get('text_intro', ''))
                        if text_intro:
                            text_segment.add_animation(text_intro, duration=tim("0.5s"))
                        text_outro = get_text_outro(effects_config.get('text_outro', ''))
                        if text_outro:
                            text_segment.add_animation(text_outro, duration=tim("0.5s"))
                        script.add_segment(text_segment, track_name=target_track)

                    current_total_duration += audio_duration

                current_audio_index += num_segments

        else:
            logger.info(f"   📋 使用传统模式: 每个音频对应一张图片（循环使用）")
            for i in range(1, num_audio_files + 1):
                audio_path = os.path.join(audio_dir, f"{i}.mp3")
                subtitle_path = os.path.join(subtitle_dir, f"{i}.txt")

                if not os.path.exists(audio_path):
                    logger.warning(f"      ⚠️ 跳过，未找到音频文件 {i}.mp3")
                    continue

                segment_start_time = current_total_duration
                audio_duration = AudioMaterial(audio_path).duration

                audio_volume = audio_config.get('bgm_volume', 1.0)
                script.add_segment(
                    AudioSegment(audio_path, target_timerange=trange(segment_start_time, audio_duration), volume=audio_volume),
                    track_name="主音频"
                )

                if has_background:
                    background_index = (i - 1) % len(background_files)
                    background_path = os.path.join(background_dir, background_files[background_index])
                    bg_segment = VideoSegment(background_path, target_timerange=trange(segment_start_time, audio_duration))
                    script.add_segment(bg_segment, track_name="背景")

                if num_image_files > 0:
                    image_index = (i - 1) % num_image_files
                    current_image_path = os.path.join(image_dir, image_files[image_index])

                    img_segment = VideoSegment(current_image_path, target_timerange=trange(segment_start_time, audio_duration))

                    if 'scale' in image_config:
                        scale_value = image_config.get('scale', 1.0)
                        img_segment.add_keyframe(KeyframeProperty.scale_x, 0, scale_value)
                        img_segment.add_keyframe(KeyframeProperty.scale_y, 0, scale_value)
                    else:
                        scale_start = image_config.get('scale_start', 1.0)
                        scale_end = image_config.get('scale_end', 1.3)
                        img_segment.add_keyframe(KeyframeProperty.scale_x, 0, scale_start)
                        img_segment.add_keyframe(KeyframeProperty.scale_y, 0, scale_start)
                        img_segment.add_keyframe(KeyframeProperty.scale_x, audio_duration, scale_end)
                        img_segment.add_keyframe(KeyframeProperty.scale_y, audio_duration, scale_end)

                    video_intro = get_video_intro(effects_config.get('video_intro', ''))
                    if video_intro:
                        img_segment.add_animation(video_intro)
                    video_outro = get_video_outro(effects_config.get('video_outro', ''))
                    if video_outro:
                        img_segment.add_animation(video_outro)
                    video_transition = get_video_transition(effects_config.get('video_transition', ''))
                    if video_transition:
                        img_segment.add_transition(video_transition)

                    if has_background:
                        script.add_segment(img_segment, track_name="内容")
                    else:
                        script.add_segment(img_segment)
                else:
                    raise FileNotFoundError("图片未下载，image 目录为空。")

                if os.path.exists(subtitle_path):
                    with open(subtitle_path, 'r', encoding='utf-8') as f:
                        text_content = f.read().strip()

                    if text_content:
                        target_track = "字幕主"
                        base_position_y = subtitle_config.get('position_y', -0.3)
                        text_style = TextStyle(
                            size=subtitle_config.get('font_size', 40.0),
                            color=tuple(subtitle_config.get('color', (1.0, 1.0, 1.0))),
                            auto_wrapping=subtitle_config.get('auto_wrap', True),
                            max_line_width=subtitle_config.get('max_line_width', 0.85),
                            align=subtitle_config.get('align', 1)
                        )
                        text_border = TextBorder(
                            color=tuple(subtitle_config.get('border_color', (0.0, 0.0, 0.0))),
                            width=subtitle_config.get('border_width', 2.0)
                        )
                        text_segment = TextSegment(
                            text_content,
                            trange(segment_start_time, audio_duration),
                            font=font_type,
                            style=text_style,
                            border=text_border,
                            clip_settings=ClipSettings(transform_y=base_position_y)
                        )
                        text_intro = get_text_intro(effects_config.get('text_intro', ''))
                        if text_intro:
                            text_segment.add_animation(text_intro, duration=tim("0.5s"))
                        text_outro = get_text_outro(effects_config.get('text_outro', ''))
                        if text_outro:
                            text_segment.add_animation(text_outro, duration=tim("0.5s"))
                        script.add_segment(text_segment, track_name=target_track)

                current_total_duration += audio_duration

        # 添加卡片图片到视频末尾
        original_video_duration = current_total_duration
        if current_total_duration > 0:
            card_image_path = None
            try:
                if os.path.isdir(material_dir):
                    for item in os.listdir(material_dir):
                        item_path = os.path.join(material_dir, item)
                        if item in ['cover', 'audio', 'image', 'subtitles', 'background']:
                            continue
                        if os.path.isdir(item_path):
                            for file in os.listdir(item_path):
                                if file.lower().startswith('card.') and file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                                    card_image_path = os.path.join(item_path, file)
                                    logger.info(f"   🎴 找到卡片图片: {card_image_path}")
                                    break
                        if card_image_path:
                            break

                if card_image_path and os.path.exists(card_image_path):
                    card_duration = 5.0
                    card_start_time = current_total_duration
                    card_segment = VideoSegment(card_image_path, target_timerange=trange(int(card_start_time), f"{card_duration}s"))
                    if has_background:
                        script.add_segment(card_segment, track_name="内容")
                    else:
                        script.add_segment(card_segment)
                    current_total_duration += card_duration * 1000000
                    logger.info(f"   🎴 ✅ 已添加卡片图片到视频末尾 (增加5秒)")
            except Exception as e:
                logger.warning(f"   ⚠️ 添加卡片图片失败: {e}")

        # 添加 BGM
        bgm_path = get_random_bgm()
        if bgm_path and current_total_duration > 0:
            try:
                bgm_dur_micro = AudioMaterial(bgm_path).duration
                bgm_dur_sec = bgm_dur_micro / 1000000
                video_dur_sec = current_total_duration / 1000000

                if bgm_dur_sec < video_dur_sec:
                    loops_needed = int(video_dur_sec / bgm_dur_sec) + 1
                    bgm_start = 0.0
                    added = 0
                    for loop in range(loops_needed):
                        loop_dur = min(bgm_dur_sec, video_dur_sec - bgm_start)
                        if loop_dur <= 0:
                            break
                        bgm_segment = AudioSegment(bgm_path, target_timerange=trange(int(bgm_start * 1000000), f"{loop_dur}s"), volume=BGM_VOLUME)
                        script.add_segment(bgm_segment, track_name="背景音乐")
                        bgm_start += loop_dur
                        added += 1
                    logger.info(f"   🎵 ✅ 已添加 BGM (循环 {added} 次, 音量: {BGM_VOLUME})")
                else:
                    bgm_segment = AudioSegment(bgm_path, target_timerange=trange(0, f"{video_dur_sec}s"), volume=BGM_VOLUME)
                    script.add_segment(bgm_segment, track_name="背景音乐")
                    logger.info(f"   🎵 ✅ 已添加 BGM (音量: {BGM_VOLUME})")
            except Exception as e:
                logger.error(f"   ❌ 添加 BGM 失败: {e}")

        # 添加免责声明
        disclaimer_config = style_config.get('disclaimer', {})
        disclaimer_enabled = disclaimer_config.get('enabled', False)
        allowed_content_keywords = ["护肤", "减脂", "养生"]
        content_type_matches = False
        if content_type:
            for keyword in allowed_content_keywords:
                if keyword in str(content_type):
                    content_type_matches = True
                    break

        should_add_disclaimer = disclaimer_enabled and current_total_duration > 0 and content_type is not None and content_type_matches

        if should_add_disclaimer:
            try:
                disclaimer_text = disclaimer_config.get('text', '内容仅供参考如有不适请线下就医')
                vertical_text = '\n'.join(list(disclaimer_text))

                disclaimer_start_time = one_frame_duration * 1000000
                original_video_duration_seconds = original_video_duration / 1000000
                disclaimer_duration = original_video_duration_seconds - one_frame_duration

                text_style = TextStyle(
                    size=disclaimer_config.get('font_size', 12),
                    color=tuple(disclaimer_config.get('color', (1.0, 1.0, 1.0))),
                    auto_wrapping=False,
                    max_line_width=1.0,
                    align=disclaimer_config.get('align', 1)
                )
                text_border = TextBorder(
                    color=tuple(disclaimer_config.get('border_color', (0.0, 0.0, 0.0))),
                    width=disclaimer_config.get('border_width', 2)
                )
                disclaimer_segment = TextSegment(
                    vertical_text,
                    trange(disclaimer_start_time, f"{disclaimer_duration}s"),
                    font=font_type,
                    style=text_style,
                    border=text_border,
                    clip_settings=ClipSettings(
                        transform_x=disclaimer_config.get('position_x', 0.85),
                        transform_y=disclaimer_config.get('position_y', 0.0)
                    )
                )
                script.add_segment(disclaimer_segment, track_name="免责声明")
                logger.info(f"   📝 ✅ 已添加右侧免责声明文字")
            except Exception as e:
                logger.warning(f"   ⚠️ 添加免责声明文字失败: {e}")

        # 保存草稿
        logger.info(f"   💾 保存草稿...")
        script.save()
        logger.info(f"   ✅ 草稿已保存: {draft_name}")

        # 更新 draft_meta_info.json
        draft_dir = os.path.join(JIANYING_DRAFT_PATH, draft_name)
        meta_info_path = os.path.join(draft_dir, 'draft_meta_info.json')
        draft_content_path = os.path.join(draft_dir, 'draft_content.json')

        if os.path.exists(meta_info_path):
            try:
                with open(meta_info_path, 'r', encoding='utf-8') as f:
                    meta_info = json.load(f)
                current_timestamp = int(time.time() * 1000000)
                meta_info['draft_name'] = draft_name
                meta_info['draft_fold_path'] = draft_dir.replace('\\', '/')
                meta_info['draft_root_path'] = JIANYING_DRAFT_PATH.replace('\\', '/')
                meta_info['tm_draft_create'] = current_timestamp
                meta_info['tm_draft_modified'] = current_timestamp

                try:
                    if os.path.exists(draft_content_path):
                        with open(draft_content_path, 'r', encoding='utf-8') as f:
                            draft_content = json.load(f)
                        meta_info['tm_duration'] = draft_content.get('duration', 0)
                except Exception:
                    pass

                with open(meta_info_path, 'w', encoding='utf-8') as f:
                    json.dump(meta_info, f, ensure_ascii=False, indent='\t')
                logger.info(f"   ✅ 已更新 draft_meta_info.json")
            except Exception as e:
                logger.warning(f"   ⚠️ 无法更新 draft_meta_info.json: {e}")

        # 更新时间戳
        try:
            ct = time.time()
            if os.path.exists(draft_dir):
                os.utime(draft_dir, (ct, ct))
            if os.path.exists(draft_content_path):
                os.utime(draft_content_path, (ct, ct))
            if os.path.exists(meta_info_path):
                os.utime(meta_info_path, (ct, ct))
        except Exception:
            pass

        time.sleep(5)  # 等待草稿渲染
        logger.info(f"   ⏰ 等待草稿渲染和剪映识别（5秒）...")

        if not os.path.exists(draft_dir):
            raise FileNotFoundError(f"草稿目录不存在: {draft_dir}")

        # 导出视频
        logger.info(f"   📤 开始导出视频...")
        if os.path.isdir(video_output_dir):
            for f in os.listdir(video_output_dir):
                if f.lower().endswith('.mp4'):
                    try:
                        os.remove(os.path.join(video_output_dir, f))
                    except OSError:
                        pass

        try:
            if HAS_PSUTIL:
                jianying_alive = False
                try:
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            if 'JianyingPro' in proc.info['name']:
                                jianying_alive = True
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    if not jianying_alive:
                        logger.warning(f"   ⚠️ 剪映进程不存在，重新启动...")
                        if os.path.exists(JIANYING_EXE_PATH):
                            subprocess.Popen([JIANYING_EXE_PATH])
                            time.sleep(15)
                except Exception:
                    pass

            try:
                ctrl = draft.JianyingController()
            except Exception as ctrl_error:
                error_msg = str(ctrl_error)
                logger.error(f"   ❌ 创建剪映控制器失败: {error_msg}")
                if "0xC0000005" in error_msg or "Access Violation" in error_msg or "访问冲突" in error_msg:
                    logger.warning(f"   ⚠️ 检测到访问冲突，完全关闭并重启剪映...")
                    close_all_jianying_processes()
                    time.sleep(1)
                    if os.path.exists(JIANYING_EXE_PATH):
                        time.sleep(3)
                        subprocess.Popen([JIANYING_EXE_PATH])
                        time.sleep(20)
                        ctrl = draft.JianyingController()
                    else:
                        raise
                else:
                    raise

            # 导出逻辑（简化版，保持与原逻辑一致）
            output_filename = f"{record_id}.mp4"
            max_export_attempts = 3
            export_timeout = 180

            def restart_jianying():
                close_all_jianying_processes()
                time.sleep(1)
                if os.path.exists(JIANYING_EXE_PATH):
                    subprocess.Popen([JIANYING_EXE_PATH])
                    time.sleep(20)
                    return draft.JianyingController()
                else:
                    raise Exception(f"❌ 剪映可执行文件不存在: {JIANYING_EXE_PATH}")

            for attempt in range(1, max_export_attempts + 1):
                try:
                    if detect_and_close_error_dialog():
                        time.sleep(1)

                    export_result = {'success': False, 'error': None}
                    export_exception = None

                    def export_worker():
                        nonlocal export_exception
                        try:
                            detect_and_close_error_dialog()
                            ctrl.export_draft(draft_name, video_output_dir)
                            export_result['success'] = True
                        except Exception as e:
                            export_result['error'] = str(e)
                            export_exception = e

                    export_thread = threading.Thread(target=export_worker, daemon=True)
                    export_thread.start()
                    export_thread.join(timeout=export_timeout)

                    if export_thread.is_alive():
                        if attempt < max_export_attempts:
                            ctrl = restart_jianying()
                            continue
                        else:
                            raise TimeoutError(f"导出命令超时（{export_timeout}秒）")

                    if export_result['error']:
                        raise export_exception if export_exception else Exception(export_result['error'])

                    if export_result['success']:
                        break
                except TimeoutError:
                    raise
                except Exception as export_error:
                    if "剪映窗口未找到" in str(export_error) or "窗口未找到" in str(export_error):
                        if attempt < max_export_attempts:
                            ctrl = restart_jianying()
                            continue
                        else:
                            raise
                    if attempt < max_export_attempts:
                        ctrl = restart_jianying()
                        continue
                    else:
                        raise

            # 等待导出完成
            logger.info(f"   ⏰ 等待导出完成（最多5分钟）...")
            output_video_path = os.path.join(video_output_dir, output_filename)
            max_wait = 300

            for wait_count in range(max_wait // 10):
                if os.path.exists(output_video_path):
                    _copy_cover_image(material_dir, video_output_dir, record_id)
                    return output_video_path

                if not os.path.exists(video_output_dir):
                    time.sleep(10)
                    continue

                try:
                    video_files = [f for f in os.listdir(video_output_dir) if f.endswith('.mp4')]
                except Exception:
                    time.sleep(10)
                    continue

                if video_files:
                    latest_video = sorted(video_files, key=lambda x: os.path.getmtime(os.path.join(video_output_dir, x)))[-1]
                    latest_video_path = os.path.join(video_output_dir, latest_video)
                    if latest_video != output_filename:
                        if os.path.exists(output_video_path):
                            os.remove(output_video_path)
                        os.rename(latest_video_path, output_video_path)
                    _copy_cover_image(material_dir, video_output_dir, record_id)
                    return output_video_path

                time.sleep(10)

            logger.error(f"   ❌ 导出超时（{max_wait}秒）")
            return None

        except Exception as e:
            logger.error(f"   ❌ 导出视频失败: {e}")
            return None

    except Exception as e:
        logger.error(f"❌ 剪映剪辑失败: {e}")
        import traceback
        traceback.print_exc()
        return None
