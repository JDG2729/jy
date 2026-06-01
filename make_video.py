"""
数据库视频剪辑服务（向后兼容入口）

本文件保留向后兼容，新功能请使用 main.py：
    python main.py                     # 持续运行
    python main.py --count 5           # 处理5条
    python main.py --id 123            # 处理指定ID
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 从新模块导入所有函数（向后兼容）
from app.config.settings import DB_CONFIG, JIANYING_DRAFT_PATH, JIANYING_EXE_PATH
from app.config.settings import BGM_DIR, BGM_VOLUME, MATERIAL_BASE_DIR, VIDEO_EXPORT_DIR, MAX_PROCESS_COUNT
from app.database.repository import (
    get_db_connection, get_pending_records, get_record_by_id,
    update_video_status, update_status_video_flag, reset_stuck_status_video_flags,
    ensure_use_column_exists, get_task_content_type, get_subtasks_tasks5_materials,
    mark_record_as_processing, init_database_fields
)
from app.services.material_service import (
    download_file, save_text, download_materials,
    download_card_image, _get_download_session, _load_bangzhu_download
)
from app.services.video_service import (
    process_single_record, batch_process, download_record_materials,
    generate_video_from_downloaded, print_final_statistics, stats
)
from app.core.jianying import (
    call_jianying_automation, get_random_bgm,
    queue_draft_for_cleanup, cleanup_pending_drafts, _delete_draft,
    close_all_jianying_processes, HAS_PSUTIL, _copy_cover_image
)
from app.utils.dialog_handler import detect_and_close_error_dialog

logger = logging.getLogger(__name__)

# 按需导入
import importlib
import importlib.util

psutil_spec = importlib.util.find_spec("psutil")
if psutil_spec:
    psutil = importlib.import_module("psutil")
    HAS_PSUTIL = True
else:
    psutil = None
    HAS_PSUTIL = False

pyautogui_spec = importlib.util.find_spec("pyautogui")
if pyautogui_spec:
    pyautogui = importlib.import_module("pyautogui")
    HAS_PYAUTOGUI = True
else:
    pyautogui = None
    HAS_PYAUTOGUI = False

win32gui_spec = importlib.util.find_spec("win32gui")
if win32gui_spec:
    try:
        import win32gui
        import win32con
        import win32api
        HAS_WIN32GUI = True
    except ImportError:
        win32gui = None
        win32con = None
        win32api = None
        HAS_WIN32GUI = False
else:
    win32gui = None
    win32con = None
    win32api = None
    HAS_WIN32GUI = False

uiautomation_spec = importlib.util.find_spec("uiautomation")
if uiautomation_spec:
    try:
        uiautomation = importlib.import_module("uiautomation")
        HAS_UIAUTOMATION = True
    except ImportError:
        uiautomation = None
        HAS_UIAUTOMATION = False
else:
    uiautomation = None
    HAS_UIAUTOMATION = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def main():
    """主函数 - 直接调用新的 main.py 入口"""
    from main import main as new_main
    new_main()


if __name__ == '__main__':
    main()
