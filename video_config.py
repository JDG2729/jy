"""
视频参数配置模块
统一管理所有视频相关参数
从 miaoooo.py 提取的统一配置
"""

# ======================== 视频分辨率配置 ========================
# 提供两种分辨率配置：竖屏（9:16）和横屏（16:9）

# 竖屏配置（用于数据库视频剪辑服务）
VIDEO_WIDTH_PORTRAIT = 720   # 视频宽度（像素，竖屏9:16）
VIDEO_HEIGHT_PORTRAIT = 960  # 视频高度（像素，竖屏9:16）

# 横屏配置（用于 miaoooo.py）
VIDEO_WIDTH_LANDSCAPE = 960  # 视频宽度（像素，横屏16:9）
VIDEO_HEIGHT_LANDSCAPE = 720 # 视频高度（像素，横屏16:9）

# 默认使用竖屏配置（数据库视频剪辑服务是主要服务）
VIDEO_WIDTH = VIDEO_WIDTH_PORTRAIT
VIDEO_HEIGHT = VIDEO_HEIGHT_PORTRAIT

# ======================== 字幕配置 ========================
# 从 miaoooo.py 提取的参数
SUBTITLE_CONFIG = {
    'size': 20.0,                    # 字体大小（从 miaoooo.py 的 subtitle_font_size）
    'color': (1.0, 1.0, 1.0),       # 字体颜色 RGB (白色，从 miaoooo.py 的 subtitle_color)
    'border_color': (1.0, 0.0, 0.0), # 边框颜色 RGB (红色，从 miaoooo.py 的 outline_color)
    'border_width': 5.0,             # 边框宽度（从 miaoooo.py 的 outline_width）
    'position_y': 0.0,               # 垂直位置（0.0=中间，从 miaoooo.py 的 start_y）
    'max_line_width': 0.85,           # 最大行宽（85%）
    'align': 1,                       # 对齐方式（1=居中，从 miaoooo.py）
    'auto_wrapping': True,            # 自动换行
    'font': '得意黑'                  # 字体类型（从 miaoooo.py 的 FontType.得意黑）
}

# ======================== 图片配置 ========================
IMAGE_CONFIG = {
    'scale_start': 1.0,              # 缩放起始值（1.0=原始大小）
    'scale_end': 1.2,                 # 缩放结束值（0.2=缩小为原来的20%）
    'show_frequency': 2,              # 图片显示频率（每N段音频显示一张图片，2=每2段音频一张图）
}

# ======================== 音频配置 ========================
AUDIO_CONFIG = {
    'volume': 1.0,                   # 音量（0.0-1.0，1.0=100%音量）
}

# ======================== 封面配置 ========================
COVER_CONFIG = {
    'duration': 1/30.0,               # 封面显示时长（秒），1/30.0=1帧
}

# ======================== 视频类型和风格配置 ========================
# 字段说明：
# - growth_category: 决定视频类型（如："个人成长"、"减脂" 等）
# - yn_koutu: 决定视频风格（"yes"=有背景风格，"no"=无背景风格）
#
# 选择逻辑：
# 1. 先根据 growth_category 确定视频类型
# 2. 再根据 yn_koutu 在选择的类型下确定风格（有背景/无背景）
#
# 注意：目前所有类型共享相同的风格配置，未来可以根据类型进行差异化定制

# ======================== 视频风格配置 ========================
# Default 风格配置（无背景，yn_koutu="no"）
DEFAULT_STYLE = {
    "name": "default",
    "display_name": "抠图型默认样式",
    "description": "抠图型任务的默认样式配置",
    "version": "1.0.0",
    "type": "koutu",
    "video": {
        "width": 1080,
        "height": 1440,
        "fps": 30
    },
    "fonts": {
        "default_font": "抖音美好体",
        "title_font": "抖音美好体"
    },
    "subtitle": {
        # 1. 字幕改小：font_size 数值减小（原16 → 改为12）
        "font_size": 12,
        # 2. 字幕颜色改为深橙色：RGB值 (1.0, 0.5, 0.0) 对应深橙色
        "color": (1.0, 0.5, 0.0),
        "border_color": (0, 0, 0),
        "border_width": 20,  # 加粗黑色边框
        "position_x": 0.0,
        "position_y": -0.6,
        "line_spacing": 0.16,
        "align": 1,
        "max_line_width": 0.85,  # 最大行宽（85%）
        "auto_wrap": True
    },
    "title": {
        # 1. 标题改小：font_size 数值减小（原52 → 改为36）
        "font_size": 90,
        # 2. 标题颜色改为深橙色：RGB值 (1.0, 0.5, 0.0)
        "color": (1.0, 0.5, 0.0),
        "border_color": (0.0, 0.0, 0.0),
        "border_width": 4,
        "position_x": 0.5,
        "position_y": 0.8,
        "align": 0,
        "max_line_width": 0.6
    },
    "audio": {
        "bgm_volume": 0.15,
        "main_audio_volume": 1.0
    },
    "effects": {
        "text_intro": "激光雕刻",
        "text_outro": "无",
        "video_intro": "无",
        "video_outro": "无",
        "video_transition": "无",
        "auto_wrap": True
    },
    "features": {
        "use_cover_as_background": True,
        "add_title": True,
        "cleanup_drafts": True
    },
    "disclaimer": {
        "enabled": True,
        "text": "内容仅供参考如有不适请线下就医",
        "font_size": 5,
        "color": (1.0, 1.0, 1.0),  # 白色
        "border_color": (0.0, 0.0, 0.0),  # 黑色边框
        "border_width": 6,  # 边框宽度（数值越大越粗，建议 2-6）
        "position_x": 0.85,  # 右侧位置（0.85 = 85%宽度处）
        "position_y": 0.0,  # 垂直居中
        "align": 1,  # 居中对齐
        "vertical": True  # 竖排显示
    }
}


# Fireman 风格配置（文字移到线下面）
FIREMAN_STYLE = {
    "name": "fireman",
    "display_name": "火柴人风格",
    "video": {
        "width": 1080,
        "height": 1440,
        "fps": 30
    },
    "fonts": {
        "default_font": "抖音美好体",
        "title_font": "抖音美好体"
    },
    "subtitle": {
        "font_size": 8,
        "color": (1.0, 0.5, 0.0),  # 橘黄色
        "border_color": (0, 0, 0),
        "border_width": 5.0,  # 加粗黑色边框
        "max_line_width": 0.85,  # 最大行宽（85%）
        "align": 1,
        "position_y": -0.75,  # 调大数值，让字幕更靠上
        "line_spacing": 0.1,  # 两排字之间的间隔（数值越大间隔越大）
        "auto_wrap": True
    },
    "title": {
        "font_size": 6.0,
        "color": (1.0, 1.0, 1.0),
        "border_color": (0.0, 0.0, 0.0),
        "border_width": 14.0,
        "max_line_width": 0.4,
        "align": 0,
        "position_x": 0.0,
        "position_y": -0.8  # 调小数值，让标题移到线下方
    },
    "image": {
        "scale_start": 0.3,  # 起始缩放（保持原来的大小）
        "scale_end": 0.6,    # 结束缩放（渐变放大到0.85倍）
        "position_x": 0.0,
        "position_y": 0.0,
    },
    "audio": {
        "bgm_volume": 0.15,
        "skip_silence": True
    },
    "effects": {
        "text_intro": "激光雕刻",
        "text_outro": "无",
        "video_intro": "无",
        "video_outro": "无",
        "video_transition": "无",
        "auto_wrap": True
    },
    "features": {
        "use_cover_as_background": True,
        "add_title": True,
        "cleanup_drafts": True
    },
    "disclaimer": {
        "enabled": True,
        "text": "内容仅供参考如有不适请线下就医",
        "font_size": 5,
        "color": (1.0, 1.0, 1.0),  # 白色
        "border_color": (0.0, 0.0, 0.0),  # 黑色边框
        "border_width": 6,  # 边框宽度（数值越大越粗，建议 2-6）
        "position_x": 0.85,  # 右侧位置（0.85 = 85%宽度处）
        "position_y": 0.0,  # 垂直居中
        "align": 1,  # 居中对齐
        "vertical": True  # 竖排显示
    }
}

def get_style_config(yn_koutu: str = "no", growth_category: str = None):
    """
    根据 growth_category（视频类型）和 yn_koutu（视频风格）获取对应的视频风格配置
    
    逻辑：
    1. 先根据 growth_category 选择视频类型
    2. 然后根据 yn_koutu 在选择的类型下选择风格（有背景/无背景）
    
    Args:
        growth_category: 成长分类，决定视频类型（如 "个人成长"、"减脂" 等）
        yn_koutu: "yes" 或 "no"（不区分大小写），决定视频风格（"yes"=有背景，"no"=无背景），默认 "no"
        
    Returns:
        对应的风格配置字典
    """
    # 1. 根据 growth_category 选择视频类型
    video_type = None
    if growth_category:
        growth_category_str = str(growth_category).strip()
        
        # growth_category 到视频类型的映射
        if "个人成长" in growth_category_str:
            video_type = "personal_growth"
        elif "减脂" in growth_category_str:
            video_type = "fat_loss"
        # 可以继续添加其他类型的映射
    
    # 2. 根据 yn_koutu 选择风格（有背景/无背景）
    yn_koutu_lower = str(yn_koutu).lower() if yn_koutu else "no"
    has_background = (yn_koutu_lower == "yes")
    
    # 3. 根据类型和风格组合返回配置
    # 目前所有类型都使用相同的风格配置，但可以根据类型进行差异化
    if has_background:
        # 有背景风格（yn_koutu="yes"）
        return FIREMAN_STYLE
    else:
        # 无背景风格（yn_koutu="no"）
        return DEFAULT_STYLE







