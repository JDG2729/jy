"""
数据库操作模块
负责所有 PostgreSQL 数据库 CRUD 操作
"""

import logging
from typing import Dict, Any, Optional, List

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config.settings import DB_CONFIG

logger = logging.getLogger(__name__)


def get_db_connection():
    """获取数据库连接"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"❌ 连接数据库失败: {e}")
        raise


def init_database_fields():
    """
    检查数据库连接和表结构
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        logger.info("📋 检查数据库连接和表结构...")

        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'subtasks'
            );
        """)
        subtasks_exists = cursor.fetchone()[0]

        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'subtasks_tasks5'
            );
        """)
        subtasks_tasks5_exists = cursor.fetchone()[0]

        if not subtasks_exists:
            logger.error("❌ subtasks 表不存在")
            return False

        if not subtasks_tasks5_exists:
            logger.error("❌ subtasks_tasks5 表不存在")
            return False

        logger.info("✅ 数据库表结构检查完成")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        logger.error(f"❌ 检查数据库失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_status_video_flag(record_ids: List[Any], value: int):
    """批量更新 subtasks 表的 status_video 标记"""
    if not record_ids:
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subtasks'
              AND column_name = 'status_video'
        """)
        has_status_video = cursor.fetchone() is not None

        if not has_status_video:
            logger.debug(f"⚠️ subtasks 表没有 status_video 字段，跳过更新")
            cursor.close()
            conn.close()
            return

        record_ids_str = [str(rid) for rid in record_ids]
        cursor.execute(
            """
            UPDATE subtasks
            SET status_video = %s
            WHERE id = ANY(%s)
            """,
            (value, record_ids_str)
        )
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if affected:
            logger.info(f"🔄 已将 {affected} 条记录的 status_video 更新为 {value}（subtasks 表）")
    except Exception as e:
        logger.error(f"❌ 更新 status_video 标记失败: {e}")


def reset_stuck_status_video_flags():
    """重置因异常导致 subtasks 表卡住的记录"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subtasks'
              AND column_name = 'status_video'
        """)
        has_status_video = cursor.fetchone() is not None

        if has_status_video:
            cursor.execute("""
                UPDATE subtasks
                SET status_video = 0
                WHERE status_video = 1
                  AND status = 'MATERIAL_COMPLETED'
            """)
        else:
            cursor.execute("""
                UPDATE subtasks
                SET status = 'MATERIAL_COMPLETED'
                WHERE status = 'VIDEO_PROCESSING'
            """)

        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        if affected:
            logger.info(f"♻️ 检测到 {affected} 条卡住的记录，已重置（subtasks 表）")
    except Exception as e:
        logger.error(f"❌ 重置状态失败: {e}")


def ensure_use_column_exists():
    """确保 subtasks_tasks5 表有 use 字段"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subtasks_tasks5'
              AND column_name = 'use'
        """)
        has_use = cursor.fetchone() is not None

        if not has_use:
            cursor.execute("""
                ALTER TABLE subtasks_tasks5
                ADD COLUMN use INTEGER DEFAULT 0
            """)
            conn.commit()
            logger.info("✅ 已创建 use 字段（subtasks_tasks5 表）")
        else:
            logger.debug("✅ use 字段已存在（subtasks_tasks5 表）")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"❌ 检查/创建 use 字段失败: {e}")
        import traceback
        traceback.print_exc()


def get_pending_records(count: Optional[int] = None) -> List[Dict]:
    """
    从头遍历表，获取待处理的记录（status='MATERIAL_COMPLETED'）
    最多返回 MAX_PROCESS_COUNT 条记录

    Args:
        count: 要处理的数量

    Returns:
        记录列表
    """
    from app.config.settings import MAX_PROCESS_COUNT

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        conn.autocommit = False
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        max_count = MAX_PROCESS_COUNT
        if count is not None:
            limit_count = min(count, max_count)
        else:
            limit_count = max_count

        sql = """
        SELECT
            id, task_id, status, growth_category,
            account_id, card_link, account_name
        FROM subtasks
        WHERE status = 'MATERIAL_COMPLETED'
          AND COALESCE(status_video, 0) = 0
          AND status_leixing IN (2, 4)
        ORDER BY id ASC
        FOR UPDATE SKIP LOCKED
        LIMIT %s
        """

        cursor.execute(sql, (limit_count,))
        results = cursor.fetchall()

        record_ids = [row['id'] for row in results if row.get('id')]
        if record_ids:
            cursor.execute(
                """
                UPDATE subtasks
                SET status_video = 1
                WHERE id = ANY(%s)
                  AND COALESCE(status_video, 0) = 0
                """,
                (record_ids,)
            )
            updated_count = cursor.rowcount
            if updated_count < len(record_ids):
                logger.warning(f"⚠️ 并发检测：SELECT 到 {len(record_ids)} 条，但只更新了 {updated_count} 条")
                if updated_count == 0:
                    logger.warning(f"⚠️ 所有记录都被其他机器处理，返回空列表")
                    conn.commit()
                    cursor.close()
                    conn.close()
                    return []
                cursor.execute(
                    """
                    SELECT id, task_id, status, growth_category,
                           account_id, card_link, account_name
                    FROM subtasks
                    WHERE id = ANY(%s)
                      AND status_video = 1
                    """,
                    (record_ids,)
                )
                results = cursor.fetchall()
                logger.info(f"✅ 实际获取到 {len(results)} 条记录")

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"✅ 获取到 {len(results)} 条待处理记录（status='MATERIAL_COMPLETED'，最多{max_count}条）")
        return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"❌ 获取记录失败: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        return []


def get_record_by_id(record_id: str) -> Optional[Dict]:
    """根据指定ID获取记录"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        sql = """
        SELECT
            id, task_id, status, growth_category,
            account_id, card_link, account_name
        FROM subtasks
        WHERE id = %s
        """

        cursor.execute(sql, (record_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            logger.info(f"✅ 找到指定ID的记录: {record_id}")
            return dict(result)
        else:
            logger.warning(f"⚠️ 未找到ID={record_id} 的记录")
            return None

    except Exception as e:
        logger.error(f"❌ 获取记录失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_task_content_type(subtask_id: str) -> Optional[str]:
    """从 subtasks_tasks4 表获取 content_type 字段"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        sql = """
        SELECT content_type
        FROM subtasks_tasks4
        WHERE tasks_id = %s
        LIMIT 1
        """

        cursor.execute(sql, (subtask_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            content_type = result.get('content_type')
            logger.debug(f"✅ 从 subtasks_tasks4 获取到 content_type: {content_type}")
            return content_type
        else:
            logger.warning(f"⚠️ 未找到 tasks_id={subtask_id} 对应的 subtasks_tasks4 记录")
            return None

    except Exception as e:
        logger.error(f"❌ 获取 content_type 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_subtasks_tasks5_materials(subtask_id: str) -> List[Dict]:
    """
    从 subtasks_tasks5 表获取所有素材数据
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        sql = """
        SELECT
            subtask_id, title, topic, full_text,
            output, status, error_message, material_generated_at, created_at, updated_at,
            account_id, card_link, account_name
        FROM subtasks_tasks5
        WHERE subtask_id = %s
        ORDER BY created_at ASC
        """

        subtask_id_str = str(subtask_id) if subtask_id is not None else None
        cursor.execute(sql, (subtask_id_str,))
        results = cursor.fetchall()

        cursor.close()
        conn.close()

        logger.info(f"✅ 从 subtasks_tasks5 获取到 {len(results)} 条素材记录（subtask_id={subtask_id_str}）")

        if len(results) == 0:
            logger.warning(f"⚠️ 未找到 subtask_id={subtask_id_str} 对应的素材数据")

        return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"❌ 获取素材数据失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def mark_record_as_processing(record_id: int):
    """标记记录为正在处理"""
    logger.debug(f"✅ 开始处理记录 ID={record_id}")


def update_video_status(record_id: int, success: bool, video_path: Optional[str] = None, error_msg: Optional[str] = None):
    """
    更新视频剪辑状态

    Args:
        record_id: 记录ID
        success: 是否成功
        video_path: 导出视频路径（成功时）
        error_msg: 错误信息（失败时）
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if success:
            sql = """
            UPDATE subtasks
            SET status = 'VIDEO_COMPLETED'
            WHERE id = %s
            """
            cursor.execute(sql, (record_id,))
            logger.debug(f"✅ 已更新记录 ID={record_id} 的状态为 VIDEO_COMPLETED")
        else:
            sql = """
            UPDATE subtasks
            SET status = 'VIDEO_FAILED'
            WHERE id = %s
            """
            cursor.execute(sql, (record_id,))
            logger.debug(f"✅ 已更新记录 ID={record_id} 的状态为 VIDEO_FAILED")

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"❌ 更新状态失败: {e}")
