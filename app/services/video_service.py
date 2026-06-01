"""
视频处理主服务模块
负责单条记录处理和批量处理流程
"""

import os
import time
import shutil
import logging
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config.settings import settings, DB_CONFIG
from app.database.repository import (
    get_db_connection, get_pending_records, get_record_by_id,
    update_video_status, update_status_video_flag, ensure_use_column_exists,
    get_task_content_type, get_subtasks_tasks5_materials, mark_record_as_processing
)
from app.services.material_service import download_materials
from app.core.jianying import call_jianying_automation, cleanup_pending_drafts, close_all_jianying_processes, HAS_PSUTIL

logger = logging.getLogger(__name__)

# 统计信息
stats = {
    'total': 0,
    'success': 0,
    'failed': 0,
    'start_time': None,
    'end_time': None
}


def download_record_materials(record: Dict) -> Optional[Dict]:
    """只下载素材（不生成视频）"""
    record_id = record['id']
    task_id = record.get('task_id')

    try:
        logger.info(f"📥 [下载] 开始下载记录 ID={record_id} 的素材...")

        materials_data = get_subtasks_tasks5_materials(record_id)

        if materials_data:
            for material in materials_data:
                material_subtask_id = material.get('subtask_id')
                if str(material_subtask_id) != str(record_id):
                    logger.warning(f"⚠️ [下载] 数据不匹配：查询条件 subtask_id={record_id}，但返回 subtask_id={material_subtask_id}")

        if not materials_data:
            logger.error(f"❌ [下载] 记录 ID={record_id} 未找到素材数据")
            update_video_status(record_id, False, error_msg='未找到素材数据')
            return None

        download_result = download_materials(materials_data, record_id)

        if isinstance(download_result, dict) and download_result.get('empty'):
            logger.error(f"❌ [下载] 记录 ID={record_id} 素材为空")
            update_video_status(record_id, False, error_msg='素材为空')
            return None
        elif not download_result:
            logger.error(f"❌ [下载] 记录 ID={record_id} 素材下载不完整")
            update_status_video_flag([record_id], 0)
            return None

        logger.info(f"✅ [下载] 记录 ID={record_id} 素材下载完成")
        return {
            'record': record,
            'record_id': record_id,
            'task_id': task_id,
            'material_dir': download_result['material_dir'],
            'yn_koutu': download_result.get('yn_koutu', 'no'),
            'content': download_result.get('content', []),
            'title': materials_data[0].get('title') if materials_data else f'video_{record_id}'
        }

    except Exception as e:
        logger.error(f"❌ [下载] 记录 ID={record_id} 下载异常: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        update_video_status(record_id, False, error_msg=f"下载异常: {str(e)}")
        return None


def generate_video_from_downloaded(download_info: Dict) -> Dict:
    """从已下载的素材生成视频"""
    start_time = time.time()
    record = download_info['record']
    record_id = download_info['record_id']
    material_dir = download_info['material_dir']
    yn_koutu = download_info['yn_koutu']
    content = download_info['content']
    title = download_info['title']
    growth_category = record.get('growth_category')

    try:
        logger.info(f"🎬 [生成] 开始生成记录 ID={record_id} 的视频...")

        content_type = get_task_content_type(record_id)
        logger.info(f"📋 [生成] content_type: {content_type}, growth_category: {growth_category}")

        video_path = call_jianying_automation(
            material_dir, record_id, title,
            yn_koutu=yn_koutu, content=content,
            content_type=content_type, growth_category=growth_category
        )

        if not video_path:
            logger.error(f"❌ [生成] 记录 ID={record_id} 剪映剪辑失败")
            update_video_status(record_id, False, error_msg='剪映剪辑失败')
            stats['failed'] += 1
            return {
                'id': record_id, 'status': 'failed',
                'error': '剪映剪辑失败', 'duration': time.time() - start_time
            }

        # 导出成功后删除素材文件夹
        try:
            if os.path.exists(material_dir):
                shutil.rmtree(material_dir, ignore_errors=False)
                logger.info(f"🗑️ [清理] 已删除素材文件夹: {material_dir}")
        except Exception as cleanup_err:
            logger.warning(f"⚠️ [清理] 删除素材文件夹失败: {cleanup_err}")

        duration = time.time() - start_time
        logger.info(f"✅ [生成] 记录 ID={record_id} 视频生成完成 - 耗时: {duration:.2f}s")

        stats['success'] += 1
        return {
            'id': record_id, 'status': 'success',
            'duration': duration, 'video_path': video_path
        }

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ [生成] 记录 ID={record_id} 生成异常: {e}")
        import traceback
        traceback.print_exc()
        update_video_status(record_id, False, error_msg=str(e))
        stats['failed'] += 1
        return {
            'id': record_id, 'status': 'error',
            'error': str(e), 'duration': duration
        }


def process_single_record(record: Dict) -> Dict:
    """处理单条记录"""
    start_time = time.time()
    record_id = record['id']
    task_id = record.get('task_id')
    growth_category = record.get('growth_category')

    try:
        logger.info(f"🚀 开始处理记录 ID={record_id} (task_id={task_id}, growth_category={growth_category})...")

        if not record_id:
            return {'id': record_id, 'status': 'skipped', 'error': '记录 ID 为空', 'duration': time.time() - start_time}

        mark_record_as_processing(record_id)

        if 'output' in record and record.get('output'):
            materials_data = [{
                'subtask_id': record_id, 'title': record.get('title'),
                'output': record.get('output'), 'account_id': record.get('account_id'),
                'card_link': record.get('card_link'), 'account_name': record.get('account_name'),
            }]
        else:
            logger.info(f"📦 从 subtasks_tasks5 表获取所有素材数据（subtask_id={record_id}）...")
            materials_data = get_subtasks_tasks5_materials(record_id)

        record_status = record.get('status')
        if not materials_data:
            logger.error(f"❌ 未找到素材数据")
            update_video_status(record_id, False, error_msg='未找到素材数据')
            return {'id': record_id, 'status': 'failed', 'error': '未找到素材数据', 'duration': time.time() - start_time}

        # 检查 output 是否为空
        if record_status != 1:
            output_data = materials_data[0].get('output') if materials_data else None
            is_output_empty = False
            if not output_data:
                is_output_empty = True
            elif isinstance(output_data, str):
                if output_data.lower() == 'null' or output_data.strip() == '{}':
                    is_output_empty = True
            elif isinstance(output_data, dict):
                if not output_data or len(output_data) == 0:
                    is_output_empty = True

            if is_output_empty:
                logger.error(f"❌ output 字段为空，标记为失败")
                update_video_status(record_id, False, error_msg='output 字段为空')
                return {'id': record_id, 'status': 'failed', 'error': 'output 字段为空', 'duration': time.time() - start_time}

        title = materials_data[0].get('title') if materials_data else None
        if not title:
            title = f'video_{record_id}'
        else:
            logger.info(f"   📝 标题: {title[:50]}...")

        # 下载素材
        logger.info(f"📥 开始下载素材...")
        download_result = download_materials(materials_data, record_id)

        # 处理 403/404/空/不完整
        if isinstance(download_result, dict) and download_result.get('403_error'):
            logger.error(f"❌ 检测到403 Forbidden错误，标记为失败")
            update_video_status(record_id, False, error_msg='403 Forbidden: URL已过期或需要认证')
            return {'id': record_id, 'status': 'failed', 'error': '403 Forbidden', 'duration': time.time() - start_time}
        elif isinstance(download_result, dict) and download_result.get('404_error'):
            logger.error(f"❌ 检测到404 Not Found错误，标记为失败")
            update_video_status(record_id, False, error_msg='404 Not Found: 文件不存在')
            return {'id': record_id, 'status': 'failed', 'error': '404 Not Found', 'duration': time.time() - start_time}
        elif isinstance(download_result, dict) and download_result.get('empty'):
            logger.error(f"❌ 素材为空，标记为失败")
            update_video_status(record_id, False, error_msg='素材为空')
            return {'id': record_id, 'status': 'failed', 'error': '素材为空', 'duration': time.time() - start_time}
        elif not download_result:
            logger.error(f"❌ 素材下载不完整，将 use 重置为 0")
            try:
                ensure_use_column_exists()
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE subtasks_tasks5 SET use = 0 WHERE subtask_id = %s", (str(record_id),))
                affected = cursor.rowcount
                conn.commit()
                cursor.close()
                conn.close()
                if affected > 0:
                    logger.info(f"   🔁 已将记录 ID={record_id} 的 use 重置为 0")
            except Exception as e:
                logger.warning(f"   ⚠️ 重置 use 失败: {e}")
            try:
                update_status_video_flag([record_id], 0)
            except Exception:
                pass
            return {'id': record_id, 'status': 'skipped', 'error': '素材下载不完整，use 已重置为 0', 'duration': time.time() - start_time}

        material_dir = download_result['material_dir']
        yn_koutu = download_result.get('yn_koutu', 'no')
        content = download_result.get('content', [])
        growth_category = record.get('growth_category')

        content_type = None
        if record_id:
            content_type = get_task_content_type(record_id)

        logger.info(f"🎬 开始剪映自动化剪辑...")
        video_path = call_jianying_automation(
            material_dir, record_id, title,
            yn_koutu=yn_koutu, content=content,
            content_type=content_type, growth_category=growth_category
        )

        if not video_path:
            logger.error(f"❌ 剪映剪辑失败")
            update_video_status(record_id, False, error_msg='剪映剪辑失败')
            stats['failed'] += 1
            return {'id': record_id, 'status': 'failed', 'error': '剪映剪辑失败', 'duration': time.time() - start_time}

        duration = time.time() - start_time

        # 删除素材文件夹
        try:
            if os.path.exists(material_dir):
                shutil.rmtree(material_dir, ignore_errors=False)
                logger.info(f"🗑️ [清理] 已删除素材文件夹: {material_dir}")
        except Exception as cleanup_err:
            logger.warning(f"⚠️ [清理] 删除素材文件夹失败: {cleanup_err}")

        logger.info(f"✅ 记录 ID={record_id} 处理完成 - 耗时: {duration:.2f}s")
        return {
            'id': record_id, 'status': 'success',
            'duration': duration, 'video_path': video_path
        }

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ 记录 ID={record_id} 处理异常: {e}")
        import traceback
        traceback.print_exc()
        update_video_status(record_id, False, error_msg=str(e))
        return {'id': record_id, 'status': 'error', 'error': str(e), 'duration': duration}


def batch_process(records: List[Dict], target_count: int = None):
    """批量处理记录（单通道：下载完一个处理一个）"""
    logger.info("=" * 80)
    logger.info(f"开始批量处理视频剪辑（单通道模式）")
    logger.info(f"  任务总数: {len(records)}")
    logger.info(f"  目标数量: {target_count}")
    logger.info("=" * 80)

    stats['total'] = len(records)
    stats['success'] = 0
    stats['failed'] = 0
    stats['start_time'] = datetime.now()

    # 检查并启动剪映
    logger.info("🔍 检查剪映应用状态...")
    jianying_running = False
    if HAS_PSUTIL:
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'JianyingPro' in proc.info['name']:
                        jianying_running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if jianying_running:
                logger.info(f"   ✅ 剪映应用已在运行")
        except Exception as e:
            logger.debug(f"   检查进程时出错: {e}")

    if not jianying_running:
        logger.info(f"   🚀 启动剪映应用...")
        jianying_exe = settings.JIANYING_EXE_PATH
        if os.path.exists(jianying_exe):
            subprocess.Popen([jianying_exe])
            time.sleep(15)
            logger.info(f"   ✅ 剪映应用已启动")
        else:
            logger.warning(f"   ⚠️ 剪映可执行文件不存在")

    record_ids = [r['id'] for r in records if r.get('id')]
    if record_ids:
        update_status_video_flag(record_ids, 1)

    results = []
    skipped_count = 0

    batch_size = 3
    consecutive_failures = 0
    CONSECUTIVE_FAIL_RESTART_THRESHOLD = 3

    for batch_start in range(0, len(records), batch_size):
        batch_end = min(batch_start + batch_size, len(records))
        batch_records = records[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(records) + batch_size - 1) // batch_size

        logger.info(f"📦 批次 {batch_num}/{total_batches}: 处理 {len(batch_records)} 条记录")

        if target_count is not None and stats['success'] >= target_count:
            logger.info(f"✅ 已达到目标数量 {target_count} 条，停止处理")
            break

        try:
            # 并发下载
            logger.info(f"📥 步骤1: 并发下载 {len(batch_records)} 条记录的素材...")
            lock = threading.Lock()
            batch_downloaded = []

            def download_worker(record):
                record_id = record.get('id') if record else 'unknown'
                try:
                    download_info = download_record_materials(record)
                    if download_info:
                        return (record_id, download_info)
                    else:
                        with lock:
                            stats['failed'] += 1
                        return (record_id, None)
                except Exception as e:
                    logger.error(f"   ❌ [并发下载] 记录 ID={record_id} 下载异常: {e}")
                    with lock:
                        stats['failed'] += 1
                    return (record_id, None)

            download_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Download")
            try:
                future_to_record = {
                    download_executor.submit(download_worker, record): record
                    for record in batch_records
                }
                completed_count = 0
                for future in as_completed(future_to_record, timeout=600):
                    try:
                        result = future.result(timeout=1)
                        if result:
                            record_id, download_info = result
                            batch_downloaded.append((record_id, download_info))
                            completed_count += 1
                    except Exception as e:
                        record = future_to_record.get(future)
                        record_id = record.get('id') if record else 'unknown'
                        logger.error(f"   ❌ 记录 ID={record_id} 获取结果异常: {e}")
                        with lock:
                            stats['failed'] += 1
                        batch_downloaded.append((record_id, None))
                        completed_count += 1
            finally:
                download_executor.shutdown(wait=True)

            # 单线程顺序生成
            logger.info(f"🎬 步骤2: 单线程顺序生成视频...")
            for i, (record_id, download_info) in enumerate(batch_downloaded, 1):
                if not download_info:
                    logger.error(f"   ❌ 记录 ID={record_id} 下载失败，跳过")
                    continue

                try:
                    result = generate_video_from_downloaded(download_info)
                    results.append(result)

                    if result['status'] == 'success':
                        consecutive_failures = 0
                    elif result['status'] == 'skipped':
                        consecutive_failures = 0
                        skipped_count += 1
                    elif result['status'] in ('failed', 'error'):
                        consecutive_failures += 1
                        if consecutive_failures >= CONSECUTIVE_FAIL_RESTART_THRESHOLD:
                            logger.warning(f"   ⚠️ 连续 {consecutive_failures} 个视频失败，重启剪映...")
                            close_all_jianying_processes()
                            time.sleep(1)
                            jianying_exe = settings.JIANYING_EXE_PATH
                            if os.path.exists(jianying_exe):
                                subprocess.Popen([jianying_exe])
                                time.sleep(20)
                            consecutive_failures = 0
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    logger.error(f"   ❌ 记录 ID={record_id} 生成异常: {e}")
                    results.append({'id': record_id, 'status': 'error', 'error': str(e)})
                    stats['failed'] += 1
                    consecutive_failures += 1

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as batch_error:
            logger.error(f"❌ 批次 {batch_num} 处理异常: {batch_error}")
            continue

    stats['end_time'] = datetime.now()
    print_final_statistics(results, target_count)


def print_final_statistics(results: List[Dict], target_count: int = None):
    """打印最终统计报告"""
    total_duration = (stats['end_time'] - stats['start_time']).total_seconds()
    skipped_count = len([r for r in results if r.get('status') == 'skipped'])

    print()
    print("=" * 80)
    print("  视频剪辑完成 - 统计报告")
    print("=" * 80)
    print(f"目标任务数: {stats['total']}")
    print(f"✅ 成功生成: {stats['success']} 条")
    print(f"❌ 失败: {stats['failed']} 条")
    print(f"⏭️ 跳过: {skipped_count} (output 为空)")
    print(f"成功率: {(stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0:.2f}%")
    if target_count:
        print(f"目标数量: {target_count} 条")
    print(f"总耗时: {total_duration:.2f}s ({total_duration/60:.2f}分钟)")
    print(f"平均耗时: {(total_duration / stats['total']) if stats['total'] > 0 else 0:.2f}s/任务")
    print()
    print("=" * 80)
    print(f"🎉 本次共生成 {stats['success']} 条视频")
    print("=" * 80)
