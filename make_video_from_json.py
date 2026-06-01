"""
从JSON文件读取素材数据并生成视频（向后兼容入口）

本文件保留向后兼容，新功能请使用 main.py：
    python main.py --mode json --json-file data/xxx.json
    python main.py --mode json --json-file data/xxx.json --count 1
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 从新模块导入
from app.services.json_video_service import (
    download_materials_from_json, process_json_material, main_json_mode
)
from app.config.settings import MATERIAL_BASE_DIR
from app.services.material_service import download_file, save_text
from app.core.jianying import call_jianying_automation


def main():
    """JSON 模式入口 - 调用新模块"""
    main_json_mode()


if __name__ == '__main__':
    main()
