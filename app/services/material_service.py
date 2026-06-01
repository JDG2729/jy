"""
素材下载服务模块
负责从 URL 下载封面、音频、图片、字幕、背景图等素材
"""

import os
import re
import json
import time
import logging
import threading
import importlib
import importlib.util
from pathlib import Path
from urllib.parse import urlparse
from typing import Tuple, Optional, List, Dict

import requests

from app.config.settings import MATERIAL_BASE_DIR

logger = logging.getLogger(__name__)

# 全局 Session 对象，用于复用连接
_download_session = None
_session_lock = threading.Lock()


def _get_download_session():
    """获取全局下载 Session，复用连接"""
    global _download_session
    if _download_session is None:
        with _session_lock:
            if _download_session is None:
                _download_session = requests.Session()
                _download_session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Referer': 'https://www.oceancloudapi.com/',
                })
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=5,
                    pool_maxsize=10,
                    max_retries=0
                )
                _download_session.mount('http://', adapter)
                _download_session.mount('https://', adapter)
    return _download_session


def _load_bangzhu_download():
    """加载 帮住.py 的 download_image 函数；失败返回 None。"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上两级到项目根目录
        project_root = os.path.dirname(os.path.dirname(base_dir))
        bangzhu_path = os.path.join(project_root, "tests", "test_card_download.py")
        if not os.path.isfile(bangzhu_path):
            # 兼容旧位置
            bangzhu_path = os.path.join(project_root, "帮住.py")
        if not os.path.isfile(bangzhu_path):
            return None
        spec = importlib.util.spec_from_file_location("_card_download_helper", bangzhu_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "download_image", None)
    except Exception:
        return None


def download_file(
    url: str, save_path: str, filename: str,
    show_progress: bool = True, max_retries: int = 10,
    simple_headers: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    下载文件并保存到指定路径

    Returns:
        (是否成功, 错误类型)
    """
    if not url or not url.strip():
        if show_progress:
            logger.debug(f"⚠️ 跳过空 URL: {filename}")
        return False, None

    if not url.startswith(('http://', 'https://')):
        logger.error(f"   ❌ URL格式不正确: {url[:100]}")
        return False, None

    _simple_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    if not simple_headers:
        session = _get_download_session()
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else None
        request_headers = {}
        if origin:
            request_headers['Referer'] = origin
    else:
        session = None
        request_headers = _simple_headers

    full_path = os.path.join(save_path, filename)
    is_connection_reset = False

    for attempt in range(1, max_retries + 1):
        try:
            if show_progress:
                logger.info(f"   📥 正在下载: {filename}... (第 {attempt}/{max_retries} 次尝试)")

            if simple_headers:
                response = requests.get(url, headers=_simple_headers, timeout=60)
                response.raise_for_status()
                with open(full_path, 'wb') as f:
                    f.write(response.content)
            else:
                response = session.get(url, stream=True, timeout=60, allow_redirects=True, headers=request_headers)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                with open(full_path, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and show_progress and downloaded % (1024 * 1024) == 0:
                                progress = (downloaded / total_size) * 100
                                logger.debug(f"      → {filename}: {progress:.1f}%")

            if show_progress:
                file_size = os.path.getsize(full_path) / 1024
                logger.info(f"   ✅ 下载完成: {filename} ({file_size:.1f} KB)")
            return True, None

        except requests.exceptions.Timeout:
            logger.error(f"   ❌ 下载超时: {filename} - 尝试 {attempt}/{max_retries}")
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') and e.response is not None else None
            if status_code == 403:
                logger.error(f"   ❌ 下载失败 (403 Forbidden): {filename}")
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
                return False, '403'
            elif status_code == 404:
                logger.error(f"   ❌ 下载失败 (404 Not Found): {filename}")
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
                return False, '404'
            else:
                logger.error(f"   ❌ 下载失败 (HTTP {status_code}): {filename}")
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass
        except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
            error_str = str(e)
            is_connection_reset = 'ConnectionResetError' in error_str or 'Connection aborted' in error_str or '10054' in error_str
            if is_connection_reset:
                logger.error(f"   ❌ 连接重置: {filename} - 尝试 {attempt}/{max_retries}")
            else:
                logger.error(f"   ❌ 下载失败: {filename} - 尝试 {attempt}/{max_retries}")
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"   ❌ 下载异常: {filename} - 尝试 {attempt}/{max_retries}")
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass

        if attempt < max_retries:
            base_wait_time = min(2 ** attempt, 30)
            wait_time = base_wait_time * 2 if is_connection_reset else base_wait_time
            if is_connection_reset:
                logger.info(f"   ⏳ 连接重置错误，等待 {wait_time} 秒后重试...")
            else:
                logger.info(f"   ⏳ 等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
            is_connection_reset = False

    logger.error(f"   ❌ 下载最终失败: {filename}")
    return False, None


def download_card_image(url: str, save_dir: str, filename: str, show_progress: bool = True) -> Tuple[bool, Optional[str]]:
    """
    卡片图下载：优先调用 test_card_download.py 的 download_image
    """
    url = (url or '').strip()
    if not url:
        return False, None
    if not url.startswith(('http://', 'https://')):
        logger.error(f"   ❌ 卡片 URL 格式不正确: {url[:100]}")
        return False, None
    save_path = os.path.join(save_dir, filename)

    bangzhu_download = _load_bangzhu_download()
    if bangzhu_download is not None:
        try:
            if show_progress:
                logger.info(f"   📥 正在下载: {filename}")
            ok = bangzhu_download(url, save_path, timeout=15)
            if ok:
                if show_progress:
                    size_kb = os.path.getsize(save_path) / 1024
                    logger.info(f"   ✅ 下载完成: {filename} ({size_kb:.1f} KB)")
                return True, None
            logger.error(f"   ❌ 卡片下载失败: {filename}")
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except Exception:
                    pass
            return False, '404'
        except Exception as e:
            logger.error(f"   ❌ 卡片下载异常: {filename} - {str(e)[:80]}")
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except Exception:
                    pass
            return False, '404'

    # 回退：内置逻辑
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else "https://yyys365.top/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Referer': origin,
        'Accept': 'image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    try:
        if show_progress:
            logger.info(f"   📥 正在下载: {filename}... (卡片专用方式)")
        response = requests.get(url, headers=headers, timeout=15, stream=True, verify=False, allow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if content_type and not content_type.startswith('image/'):
            logger.error(f"   ❌ 卡片下载失败：返回非图片 Content-Type={content_type}")
            return False, None
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        if show_progress:
            size_kb = os.path.getsize(save_path) / 1024
            logger.info(f"   ✅ 下载完成: {filename} ({size_kb:.1f} KB)")
        return True, None
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if getattr(e, 'response', None) is not None else None
        logger.error(f"   ❌ 下载失败 (HTTP {code}): {filename}")
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        return False, '403' if code == 403 else ('404' if code == 404 else None)
    except requests.exceptions.RequestException as e:
        logger.error(f"   ❌ 下载失败: {filename}")
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        return False, None


def save_text(content: str, save_path: str, filename: str, show_progress: bool = True) -> bool:
    """将文本内容保存到文件"""
    full_path = os.path.join(save_path, filename)
    try:
        if show_progress:
            logger.debug(f"   💾 保存字幕: {filename}")
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except IOError as e:
        logger.error(f"   ❌ 文件写入失败 {filename}: {e}")
        return False


def download_materials(materials_data: List[Dict], record_id: int) -> Optional[Dict]:
    """
    从 subtasks_tasks5 表的 output 字段（JSONB）下载所有素材到本地

    Returns:
        {'material_dir': str, 'yn_koutu': str, 'content': list} 或 None
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
        has_403_error = False
        has_404_error = False

        all_fengmian = []
        all_langdu = []
        all_tupian = []
        all_zimu = []
        all_beijing_pic = []
        all_content = []
        yn_koutu_value = "no"

        logger.info(f"   📋 开始解析 {len(materials_data)} 条记录的 output 字段...")
        for record_idx, material_record in enumerate(materials_data, 1):
            record_subtask_id = material_record.get('subtask_id', 'N/A')
            logger.debug(f"      记录 {record_idx}/{len(materials_data)}: subtask_id={record_subtask_id}")

            output_data = material_record.get('output')
            if not output_data:
                continue

            if isinstance(output_data, str):
                try:
                    output_data = json.loads(output_data)
                except json.JSONDecodeError:
                    logger.warning(f"   ⚠️ 无法解析 output JSON")
                    continue

            if isinstance(output_data, dict):
                if 'fengmian' in output_data and output_data['fengmian']:
                    fengmian_list = output_data['fengmian']
                    if isinstance(fengmian_list, list):
                        all_fengmian.extend([url for url in fengmian_list if url])
                    elif fengmian_list:
                        all_fengmian.append(fengmian_list)

                if 'langdu' in output_data and output_data['langdu']:
                    langdu_list = output_data['langdu']
                    if isinstance(langdu_list, list):
                        all_langdu.extend([url for url in langdu_list if url])
                    elif langdu_list:
                        all_langdu.append(langdu_list)

                if 'tupian' in output_data and output_data['tupian']:
                    tupian_list = output_data['tupian']
                    if isinstance(tupian_list, list):
                        all_tupian.extend([url for url in tupian_list if url])
                    elif tupian_list:
                        all_tupian.append(tupian_list)

                if 'zimu' in output_data and output_data['zimu']:
                    zimu_list = output_data['zimu']
                    if isinstance(zimu_list, list):
                        all_zimu.extend([text for text in zimu_list if text])
                    elif zimu_list:
                        all_zimu.append(zimu_list)

                yn_koutu = output_data.get('yn_koutu', '').lower()
                if yn_koutu:
                    yn_koutu_value = yn_koutu

                if yn_koutu == 'yes':
                    beijing_pic = output_data.get('beijing_pic', '')
                    if beijing_pic:
                        if isinstance(beijing_pic, list):
                            all_beijing_pic.extend([url for url in beijing_pic if url])
                        elif isinstance(beijing_pic, str) and beijing_pic.strip():
                            all_beijing_pic.append(beijing_pic)

                if 'content' in output_data and output_data['content']:
                    content_list = output_data['content']
                    if isinstance(content_list, list):
                        all_content.extend(content_list)
                    elif content_list:
                        all_content.append(content_list)

        card_count = 0
        for material_record in materials_data:
            account_id = material_record.get('account_id')
            card_link = material_record.get('card_link')
            account_name = material_record.get('account_name')
            if account_id and card_link and account_name:
                card_count += 1

        cover_count = len(all_fengmian)
        audio_count = len(all_langdu)
        image_count = len(all_tupian)
        subtitle_count = len(all_zimu)
        background_count = len(all_beijing_pic)

        total_expected = cover_count + audio_count + image_count + subtitle_count + background_count + card_count
        logger.info(f"   📊 素材统计: 封面={cover_count}, 音频={audio_count}, 图片={image_count}, 字幕={subtitle_count}, 背景={background_count}, 卡片={card_count}, 总计={total_expected}")

        # 1. 下载封面
        if all_fengmian:
            logger.info(f"   📷 下载封面 ({cover_count} 个)...")
            for i, cover_url in enumerate(all_fengmian):
                if cover_url:
                    total_count += 1
                    filename = "cover.png" if i == 0 else f"cover_{i + 1}.png"
                    success, error_type = download_file(cover_url, output_dirs["cover"], filename)
                    if success:
                        success_count += 1
                    elif error_type == '403':
                        has_403_error = True
                    elif error_type == '404':
                        has_404_error = True

        # 2. 下载音频
        if all_langdu:
            logger.info(f"   🎵 下载音频 ({audio_count} 个)...")
            for i, audio_url in enumerate(all_langdu):
                if audio_url:
                    total_count += 1
                    success, error_type = download_file(audio_url, output_dirs["audio"], f"{i + 1}.mp3")
                    if success:
                        success_count += 1
                    elif error_type == '403':
                        has_403_error = True
                    elif error_type == '404':
                        has_404_error = True

        # 3. 下载图片
        if all_tupian:
            logger.info(f"   🖼️  下载图片 ({image_count} 个)...")
            for i, image_url in enumerate(all_tupian):
                if image_url:
                    total_count += 1
                    scene_match = re.search(r'scene_(\d+)', image_url, re.IGNORECASE)
                    if scene_match:
                        scene_num = int(scene_match.group(1))
                        filename = f"{scene_num}.jpg"
                    else:
                        filename = f"{i + 1}.jpg"
                    success, error_type = download_file(image_url, output_dirs["image"], filename)
                    if success:
                        success_count += 1
                        if i < len(all_tupian) - 1:
                            time.sleep(0.5)
                    elif error_type == '403':
                        has_403_error = True
                    elif error_type == '404':
                        has_404_error = True

        # 4. 保存字幕
        if all_zimu:
            logger.info(f"   📝 保存字幕 ({subtitle_count} 个)...")
            for i, subtitle_text in enumerate(all_zimu):
                if subtitle_text:
                    total_count += 1
                    if save_text(str(subtitle_text), output_dirs["subtitles"], f"{i + 1}.txt"):
                        success_count += 1

        # 5. 下载背景图片
        if all_beijing_pic:
            logger.info(f"   🖼️  下载背景图片 ({background_count} 个)...")
            for i, background_url in enumerate(all_beijing_pic):
                if background_url:
                    total_count += 1
                    success, error_type = download_file(background_url, output_dirs["background"], f"{i + 1}.jpg")
                    if success:
                        success_count += 1
                    elif error_type == '403':
                        has_403_error = True
                    elif error_type == '404':
                        has_404_error = True

        # 6. 下载 card_link 图片
        if card_count > 0:
            logger.info(f"   🎴 下载卡片图片 ({card_count} 个)...")
            for material_record in materials_data:
                account_id = material_record.get('account_id')
                card_link = (material_record.get('card_link') or '').strip()
                account_name = material_record.get('account_name')

                if account_id and card_link and account_name:
                    try:
                        safe_folder_name = "".join(c for c in str(account_name) if c.isalnum() or c in (' ', '-', '_'))[:50]
                        if not safe_folder_name or not safe_folder_name.strip():
                            safe_folder_name = f"account_{account_id}"

                        card_image_dir = os.path.join(material_dir, safe_folder_name)
                        os.makedirs(card_image_dir, exist_ok=True)

                        file_ext = '.jpg'
                        if card_link:
                            path = urlparse(card_link).path or card_link
                            if '.' in path:
                                url_ext = path.split('.')[-1].lower()
                                if url_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                                    file_ext = f'.{url_ext}'

                        filename = f"card{file_ext}"
                        total_count += 1
                        success, error_type = download_card_image(card_link, card_image_dir, filename)
                        if success:
                            success_count += 1
                        elif error_type == '403':
                            has_403_error = True
                        elif error_type == '404':
                            has_404_error = True
                    except Exception as e:
                        logger.error(f"   ❌ 下载卡片图片失败: {e}")

        logger.info(f"✅ 素材下载完成: {success_count}/{total_count} 成功")

        # 特殊错误处理
        if has_403_error:
            logger.error("❌ 检测到403 Forbidden错误，直接标记为失败")
            try:
                if os.path.exists(material_dir):
                    shutil.rmtree(material_dir, ignore_errors=False)
                    logger.info(f"🗑️ [清理] 403错误，已删除素材文件夹: {material_dir}")
            except Exception:
                pass
            return {'403_error': True}

        if has_404_error:
            logger.error("❌ 检测到404 Not Found错误，直接标记为失败")
            try:
                if os.path.exists(material_dir):
                    shutil.rmtree(material_dir, ignore_errors=False)
                    logger.info(f"🗑️ [清理] 404错误，已删除素材文件夹: {material_dir}")
            except Exception:
                pass
            return {'404_error': True}

        if total_count == 0:
            logger.error("❌ 未检测到任何素材，标记为失败")
            try:
                if os.path.exists(material_dir):
                    shutil.rmtree(material_dir, ignore_errors=False)
                    logger.info(f"🗑️ [清理] 素材为空，已删除素材文件夹: {material_dir}")
            except Exception:
                pass
            return {'empty': True}

        if success_count == total_count:
            return {
                'material_dir': material_dir,
                'yn_koutu': yn_koutu_value,
                'content': all_content
            }
        else:
            failed_count = total_count - success_count
            logger.error(f"❌ 素材有 {failed_count} 个未成功下载")
            try:
                if os.path.exists(material_dir):
                    shutil.rmtree(material_dir, ignore_errors=False)
                    logger.info(f"🗑️ [清理] 下载不完整，已删除素材文件夹: {material_dir}")
            except Exception:
                pass
            return None

    except Exception as e:
        logger.error(f"❌ 下载素材失败: {e}")
        import traceback
        traceback.print_exc()
        return None
