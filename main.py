"""
剪映自动化视频生成系统 - 统一入口

使用方法:
    # 数据库模式（从 PostgreSQL 读取素材并生成视频）
    python main.py                     # 持续运行模式
    python main.py --count 5           # 处理指定数量
    python main.py --id 123            # 处理指定ID的记录
    python main.py --init-db           # 只初始化数据库字段

    # JSON 模式（从本地 JSON 文件读取素材并生成视频）
    python main.py --mode json --json-file data/xxx.json
    python main.py --mode json --json-file data/xxx.json --count 1
    python main.py --mode json --json-file data/xxx.json --index 0

环境变量:
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME  # 数据库配置
    JIANYING_DRAFT_PATH, JIANYING_EXE_PATH  # 剪映路径
    BGM_DIR, BGM_VOLUME                     # BGM 配置
"""

import sys
import os
import time
import argparse
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.settings import DB_CONFIG
from app.database.repository import (
    init_database_fields, get_pending_records, get_record_by_id,
    reset_stuck_status_video_flags
)
from app.services.video_service import (
    process_single_record, batch_process, cleanup_pending_drafts, stats
)
from app.services.json_video_service import main_json_mode


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main_db_mode(args):
    """数据库模式主函数"""
    print()
    print("=" * 80)
    print("  剪映自动化视频生成系统 - 数据库模式")
    print("=" * 80)
    print(f"  数据库: {DB_CONFIG['host']}/{DB_CONFIG['database']}")
    print()

    # 1. 初始化数据库字段
    logger.info("步骤1: 初始化数据库字段...")
    if not init_database_fields():
        logger.error("❌ 初始化失败，程序退出")
        return

    if args.init_db:
        logger.info("✅ 数据库字段初始化完成，程序退出")
        return

    # 2. 如果指定了ID，直接处理指定ID的记录
    if args.id:
        logger.info(f"🎯 指定ID模式：处理记录 ID={args.id}")
        record = get_record_by_id(args.id)
        if not record:
            logger.error(f"❌ 未找到ID={args.id} 的记录")
            return

        from app.database.repository import update_status_video_flag
        try:
            update_status_video_flag([args.id], 1)
        except Exception as e:
            logger.warning(f"⚠️ 标记 status_video 失败: {e}")

        try:
            result = process_single_record(record)
            logger.info(f"✅ 处理完成: {result}")
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            from app.core.jianying import cleanup_pending_drafts
            cleanup_pending_drafts()
        return

    # 3. 持续运行模式
    count = args.count
    cycle_count = 0

    logger.info("🔄 开始持续运行模式...")
    logger.info("   按 Ctrl+C 可停止程序")
    print()

    try:
        while True:
            cycle_count += 1
            logger.info("=" * 80)
            logger.info(f"🔄 第 {cycle_count} 次循环 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 80)

            # 重置卡住的记录
            reset_stuck_status_video_flags()

            # 获取待处理记录
            records = get_pending_records(count=count)
            logger.info(f"📥 本次抓取记录数: {len(records)} 条")

            if not records:
                logger.info("⚠️ 当前没有待处理记录，1分钟后再次检查...")
                time.sleep(60)
                continue

            # 处理记录
            try:
                target_count = count if count is not None else len(records)
                batch_process(records, target_count=target_count)
                logger.info("✅ 本轮任务已完成！")
            except Exception as e:
                logger.error(f"❌ 处理失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                from app.core.jianying import cleanup_pending_drafts
                cleanup_pending_drafts()

            logger.info("🔁 本轮处理完成，等待1分钟后开始下一轮...")
            time.sleep(60)

    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断执行，程序退出")
        from app.core.jianying import cleanup_pending_drafts
        cleanup_pending_drafts()
    except Exception as e:
        logger.error(f"❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        from app.core.jianying import cleanup_pending_drafts
        cleanup_pending_drafts()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='剪映自动化视频生成系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 数据库模式
  python main.py                    # 持续运行
  python main.py --count 5          # 处理5条
  python main.py --id 123           # 处理指定ID

  # JSON模式
  python main.py --mode json --json-file data/xxx.json
  python main.py --mode json --json-file data/xxx.json --count 1
        """
    )
    parser.add_argument('--mode', type=str, default='db', choices=['db', 'json'],
                        help='运行模式: db=数据库模式, json=JSON文件模式 (默认: db)')
    parser.add_argument('--count', type=int, default=None, help='每批处理的视频数量（最多12条）')
    parser.add_argument('--id', type=str, default=None, help='指定要处理的记录ID')
    parser.add_argument('--init-db', action='store_true', help='只初始化数据库字段')
    parser.add_argument('--json-file', type=str, default=None, help='JSON文件路径（json模式）')
    parser.add_argument('--index', type=int, default=None, help='只处理指定索引的记录（json模式）')
    parser.add_argument('--retry-failed', action='store_true', help='重新运行失败的记录（json模式）')

    args = parser.parse_args()

    if args.mode == 'json':
        if not args.json_file:
            logger.error("❌ JSON 模式需要指定 --json-file 参数")
            parser.print_help()
            return
        main_json_mode()
    else:
        main_db_mode(args)


if __name__ == '__main__':
    main()
