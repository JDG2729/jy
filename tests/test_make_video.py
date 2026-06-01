#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：连接 PostgreSQL 数据库并生成视频
"""

import sys
import os

# 导入 make_video.py 中的函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_video import (
    get_pending_records,
    process_single_record,
    batch_process,
    cleanup_pending_drafts,
    init_database_fields,
    logger
)
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
import time

# PostgreSQL 数据库配置（覆盖 make_video.py 中的配置）
DB_CONFIG = {
    "host": "",
    "user": "",
    "password": "",
    "port": 5432,
    "database": "",
}

# 临时覆盖 make_video.py 中的 DB_CONFIG
import make_video
make_video.DB_CONFIG = DB_CONFIG

def init_database_fields_test():
    """
    检查数据库连接和表结构（只检查 subtasks_tasks5 表，不检查 subtasks 表）
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("📋 检查数据库连接和表结构...")
        
        # 只检查 subtasks_tasks5 表是否存在
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'subtasks_tasks5'
            );
        """)
        subtasks_tasks5_exists = cursor.fetchone()[0]
        
        if not subtasks_tasks5_exists:
            print("❌ subtasks_tasks5 表不存在")
            return False
        
        print("✅ 数据库表结构检查完成（subtasks_tasks5 表存在）")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ 检查数据库失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_db_connection():
    """获取数据库连接"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"✅ 成功连接到数据库: {DB_CONFIG['host']}/{DB_CONFIG['database']}")
        return conn
    except Exception as e:
        print(f"❌ 连接数据库失败: {e}")
        raise

def query_subtasks_tasks5(limit=10):
    """
    查询 subtasks_tasks5 表的数据
    
    Args:
        limit: 查询记录数量限制，默认10条
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 查询数据
        sql = """
        SELECT 
            subtask_id, title, topic, full_text,
            output, status, error_message, 
            material_generated_at, created_at, updated_at,
            account_id, card_link, account_name, use
        FROM subtasks_tasks5
        ORDER BY created_at DESC
        LIMIT %s
        """
        
        cursor.execute(sql, (limit,))
        results = cursor.fetchall()
        
        print(f"\n📊 查询结果：共 {len(results)} 条记录\n")
        print("=" * 80)
        
        # 打印每条记录
        for idx, row in enumerate(results, 1):
            print(f"\n【记录 {idx}/{len(results)}】")
            print("-" * 80)
            print(f"subtask_id: {row.get('subtask_id')}")
            print(f"title: {row.get('title')}")
            print(f"topic: {row.get('topic')}")
            print(f"status: {row.get('status')}")
            print(f"use: {row.get('use')}")
            print(f"account_id: {row.get('account_id')}")
            print(f"account_name: {row.get('account_name')}")
            print(f"created_at: {row.get('created_at')}")
            print(f"updated_at: {row.get('updated_at')}")
            
            # 如果有 output 字段，尝试解析 JSON
            output = row.get('output')
            if output:
                print(f"\noutput 字段:")
                if isinstance(output, str):
                    try:
                        output_json = json.loads(output)
                        print(f"  (JSON 格式，已解析)")
                        # 打印 output 中的关键字段
                        if isinstance(output_json, dict):
                            print(f"  - fengmian (封面): {len(output_json.get('fengmian', []))} 个")
                            print(f"  - langdu (音频): {len(output_json.get('langdu', []))} 个")
                            print(f"  - tupian (图片): {len(output_json.get('tupian', []))} 个")
                            print(f"  - zimu (字幕): {len(output_json.get('zimu', []))} 个")
                            print(f"  - yn_koutu: {output_json.get('yn_koutu')}")
                    except json.JSONDecodeError:
                        print(f"  (字符串格式，无法解析为 JSON)")
                        print(f"  内容: {output[:200]}...")
                elif isinstance(output, dict):
                    print(f"  (字典格式)")
                    print(f"  - fengmian (封面): {len(output.get('fengmian', []))} 个")
                    print(f"  - langdu (音频): {len(output.get('langdu', []))} 个")
                    print(f"  - tupian (图片): {len(output.get('tupian', []))} 个")
                    print(f"  - zimu (字幕): {len(output.get('zimu', []))} 个")
                    print(f"  - yn_koutu: {output.get('yn_koutu')}")
            
            print("-" * 80)
        
        cursor.close()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_table_info():
    """获取 subtasks_tasks5 表的基本信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询表的总记录数
        cursor.execute("SELECT COUNT(*) FROM subtasks_tasks5")
        total_count = cursor.fetchone()[0]
        
        # 查询表的字段信息
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'subtasks_tasks5'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        
        print(f"\n📋 表信息：subtasks_tasks5")
        print("=" * 80)
        print(f"总记录数: {total_count}")
        print(f"\n字段列表:")
        for col in columns:
            col_name, data_type, max_length = col
            if max_length:
                print(f"  - {col_name}: {data_type}({max_length})")
            else:
                print(f"  - {col_name}: {data_type}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ 获取表信息失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='测试脚本：生成视频')
    parser.add_argument('--count', type=int, default=None, help='每批处理的视频数量（最多12条，如果不提供则处理最多12条）')
    parser.add_argument('--id', type=str, default=None, help='指定要处理的记录ID（直接处理指定ID的记录，不抓取）')
    parser.add_argument('--query-only', action='store_true', help='只查询数据，不生成视频')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("测试脚本：生成视频")
    print("=" * 80)
    print(f"数据库: {DB_CONFIG['host']}/{DB_CONFIG['database']}")
    print()
    
    # 1. 初始化数据库字段
    print("【步骤 1】初始化数据库字段...")
    if not init_database_fields_test():
        print("❌ 初始化失败，程序退出")
        sys.exit(1)
    print("✅ 数据库字段初始化完成\n")
    
    if args.query_only:
        # 只查询数据
        print("【步骤 2】查询数据（不生成视频）")
        get_table_info()
        results = query_subtasks_tasks5(limit=args.count)
        if results:
            print(f"\n✅ 查询完成！共获取 {len(results)} 条记录")
        else:
            print("\n❌ 查询失败")
    else:
        # 生成视频
        if args.id:
            # 指定ID处理
            print(f"【步骤 2】处理指定ID的记录: {args.id}")
            from make_video import get_subtasks_tasks5_materials
            
            # 从 subtasks_tasks5 表获取数据
            materials = get_subtasks_tasks5_materials(args.id)
            if not materials:
                print(f"❌ 未找到ID={args.id} 的记录")
                sys.exit(1)
            
            record = materials[0]  # 取第一条记录
            
            # 转换为 process_single_record 需要的格式
            record_dict = {
                'id': record['subtask_id'],  # 使用 subtask_id 作为 id
                'task_id': None,  # subtasks_tasks5 表没有 task_id
                'growth_category': None,  # subtasks_tasks5 表没有 growth_category
                'title': record.get('title'),
                'output': record.get('output'),
            }
            
            result = process_single_record(record_dict)
            print(f"\n✅ 处理完成！状态: {result.get('status')}")
            if result.get('error'):
                print(f"   错误: {result.get('error')}")
        else:
            # 持续运行模式：处理完一批后等待1分钟再抓取下一批
            count = args.count
            cycle_count = 0
            
            logger.info("🔄 开始持续运行模式，处理完一批后等待1分钟再抓取下一批...")
            logger.info("   按 Ctrl+C 可停止程序")
            print()
            
            try:
                while True:
                    cycle_count += 1
                    logger.info("="*80)
                    logger.info(f"🔄 第 {cycle_count} 次循环 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    logger.info("="*80)
                    
                    # 获取待处理记录（最多12条）
                    records = get_pending_records(count=count)
                    logger.info(f"📥 本次抓取记录数: {len(records)} 条")
                    
                    if not records:
                        logger.info("⚠️ 当前没有待处理记录（use=0），1分钟后再次检查...")
                        logger.info("")
                        logger.info("⏰ 等待1分钟...")
                        logger.info("")
                        time.sleep(60)  # 1分钟 = 60秒
                        continue
                    else:
                        pending_total = len(records)
                        logger.info(f"📊 当前待处理记录: {pending_total} 条（use=0，最多12条）")
                        if count is not None:
                            actual_count = min(count, 12)
                            if count > 12:
                                logger.info(f"   - 目标数量: {count}（已限制为最多12条）")
                            else:
                                logger.info(f"   - 目标数量: {count}")
                        else:
                            logger.info("   - 未指定数量，将处理最多12条待处理记录")
                        print()
                        
                        # 开始处理
                        try:
                            target_count = count if count is not None else pending_total
                            batch_process(records, target_count=target_count)
                            logger.info("✅ 本轮任务已完成！")
                        except Exception as e:
                            logger.error(f"❌ 处理失败: {e}")
                            import traceback
                            traceback.print_exc()
                        finally:
                            cleanup_pending_drafts()
                        
                        logger.info("")
                        logger.info("🔁 本轮处理完成，等待1分钟后开始下一轮抓取...")
                        logger.info("")
                        time.sleep(60)  # 等待1分钟
                    
            except KeyboardInterrupt:
                logger.warning("\n⚠️ 用户中断执行，程序退出")
                cleanup_pending_drafts()
            except Exception as e:
                logger.error(f"❌ 执行失败: {e}")
                import traceback
                traceback.print_exc()
                cleanup_pending_drafts()
