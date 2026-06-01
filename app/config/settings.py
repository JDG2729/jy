"""
配置管理模块
从环境变量读取所有敏感配置，带合理默认值
参考 zhognyiwenzhen 的 setting_config.py 模式
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings:
    """应用配置（从环境变量读取）"""

    # ======================== 数据库配置 ========================
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "works_create")

    @classmethod
    def get_db_config(cls) -> dict:
        """获取数据库配置字典"""
        return {
            "host": cls.DB_HOST,
            "user": cls.DB_USER,
            "password": cls.DB_PASSWORD,
            "port": cls.DB_PORT,
            "database": cls.DB_NAME,
        }

    # ======================== 剪映配置 ========================
    JIANYING_DRAFT_PATH: str = os.getenv(
        "JIANYING_DRAFT_PATH",
        r"<你的路径>\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft"
    )
    JIANYING_EXE_PATH: str = os.getenv(
        "JIANYING_EXE_PATH",
        r"<你的路径>\AppData\Local\JianyingPro\Apps\JianyingPro.exe"
    )

    # ======================== BGM 配置 ========================
    BGM_DIR: str = os.getenv("BGM_DIR", str(BASE_DIR / "bgm"))
    BGM_VOLUME: float = float(os.getenv("BGM_VOLUME", "0.02"))

    # ======================== 目录配置 ========================
    MATERIAL_BASE_DIR: str = os.getenv("MATERIAL_BASE_DIR", str(BASE_DIR / "coze_workflow_works"))
    VIDEO_EXPORT_DIR: str = os.getenv("VIDEO_EXPORT_DIR", str(BASE_DIR / "exported_videos"))

    # ======================== 处理配置 ========================
    MAX_PROCESS_COUNT: int = int(os.getenv("MAX_PROCESS_COUNT", "12"))


# 全局配置实例
settings = Settings()

# 向后兼容：提供全局常量（原 make_video.py 使用的变量名）
DB_CONFIG = settings.get_db_config()
JIANYING_DRAFT_PATH = settings.JIANYING_DRAFT_PATH
JIANYING_EXE_PATH = settings.JIANYING_EXE_PATH
BGM_DIR = settings.BGM_DIR
BGM_VOLUME = settings.BGM_VOLUME
MATERIAL_BASE_DIR = settings.MATERIAL_BASE_DIR
VIDEO_EXPORT_DIR = settings.VIDEO_EXPORT_DIR
MAX_PROCESS_COUNT = settings.MAX_PROCESS_COUNT
