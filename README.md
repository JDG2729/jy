# 剪映自动化视频生成系统

通过 Python 自动从数据库或 JSON 文件获取素材，调用剪映（JianyingPro）批量生成短视频。

## 功能特性

- **数据库驱动模式**：自动从 PostgreSQL 读取待处理素材，批量生成视频
- **JSON 文件驱动模式**：从本地 JSON 文件读取素材数据生成视频
- **场景分组模式**：支持按场景编号将多段音频/字幕绑定到同一张图片
- **视频风格配置**：支持抠图型（default）和火柴人（fireman）两种风格
- **随机 BGM**：从 BGM 库中随机选择背景音乐并循环播放
- **并发安全**：使用 `FOR UPDATE SKIP LOCKED` 防止多机重复处理
- **自动容错**：弹窗检测关闭、剪映崩溃自动重启、下载指数退避重试
- **批量清理**：草稿自动清理、素材文件夹导出后自动删除

## 项目结构

```
├── main.py                          # 统一入口
├── make_video.py                    # 向后兼容入口（数据库模式）
├── make_video_from_json.py          # 向后兼容入口（JSON 模式）
├── video_config.py                  # 视频风格配置（字幕、特效、颜色等）
├── .env.example                     # 环境变量模板
├── requirements.txt                 # Python 依赖
│
├── app/                             # 应用核心代码
│   ├── config/
│   │   └── settings.py              # 配置管理（环境变量驱动）
│   ├── database/
│   │   └── repository.py            # 数据库 CRUD 操作
│   ├── services/
│   │   ├── material_service.py      # 素材下载（封面、音频、图片、字幕）
│   │   ├── video_service.py         # 视频处理主流程（单条 + 批量）
│   │   └── json_video_service.py    # JSON 驱动模式
│   ├── core/
│   │   └── jianying.py              # 剪映自动化（草稿创建、轨道添加、导出）
│   └── utils/
│       ├── dialog_handler.py        # 弹窗检测与关闭
│       └── process_manager.py       # 进程管理
│
├── tests/                           # 测试文件
│   ├── test_card_download.py        # 卡片下载测试
│   └── test_make_video.py           # 视频生成测试
│
├── data/                            # 数据文件
│   └── generated_by_*.json          # JSON 素材数据
├── logs/                            # 运行日志
├── docs/                            # 项目文档
├── bgm/                             # 背景音乐素材
└── screenshots/                     # 弹窗识别截图
```

## 环境要求

- **Python** >= 3.8
- **剪映专业版**（已安装并登录）
- **PostgreSQL** 数据库（数据库模式需要）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

编辑 `.env` 文件，填写数据库连接、剪映路径等信息：

```ini
DB_HOST=your_db_host
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=works_create

JIANYING_DRAFT_PATH=C:\Users\你的用户名\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft
JIANYING_EXE_PATH=C:\Users\你的用户名\AppData\Local\JianyingPro\Apps\JianyingPro.exe

BGM_DIR=D:\path\to\your\bgm
```

### 3. 运行

#### 数据库模式

```bash
# 持续运行（处理完一批等待1分钟再抓下一批）
python main.py

# 处理指定数量（最多12条/批）
python main.py --count 5

# 处理指定ID的记录
python main.py --id 123

# 只初始化数据库字段
python main.py --init-db
```

#### JSON 文件模式

```bash
# 处理 JSON 文件中的所有记录
python main.py --mode json --json-file data/generated_by_xxx.json

# 只处理指定索引的记录
python main.py --mode json --json-file data/generated_by_xxx.json --index 0

# 处理前 N 条记录
python main.py --mode json --json-file data/generated_by_xxx.json --count 5

# 重新运行失败的记录
python main.py --mode json --json-file data/generated_by_xxx.json --retry-failed
```

#### 向后兼容方式

```bash
# 旧入口仍然可用
python make_video.py --count 5
python make_video_from_json.py data/generated_by_xxx.json
```

## 数据库模式工作流

```
1. 连接 PostgreSQL
   └─ 查询 subtasks 表 status='MATERIAL_COMPLETED' 的记录（最多12条/批）

2. 读取素材数据
   └─ 从 subtasks_tasks5 表解析 output JSONB 字段
      └─ 提取：封面(fengmian)、音频(langdu)、图片(tupian)、字幕(zimu)、背景(beijing_pic)

3. 下载素材到本地
   └─ coze_workflow_works/{record_id}/cover|audio|image|subtitles|background/
   └─ 带10次重试 + 指数退避

4. 调用剪映自动生成视频
   └─ 使用 pyJianYingDraft 创建草稿
   └─ 添加封面 → 图片 → 音频 → 字幕 → BGM → 免责声明
   └─ 启动剪映并自动导出

5. 更新数据库状态
   └─ 成功 → VIDEO_COMPLETED
   └─ 失败 → VIDEO_FAILED
```

## 视频风格配置

系统支持两种视频风格，由数据库字段 `yn_koutu` 控制：

| 风格 | yn_koutu | 分辨率 | 字幕颜色 | 特点 |
|------|----------|--------|----------|------|
| 抠图型（default） | no | 1080×1440 | 深橙色 | 字幕大、居中 |
| 火柴人（fireman） | yes | 1080×1440 | 橘黄色 | 字幕小、靠上、图片固定缩放 |

修改风格参数请编辑 [video_config.py](video_config.py)。

## 数据库表结构

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `subtasks` | 任务状态管理 | id, task_id, status, status_video, growth_category |
| `subtasks_tasks5` | 素材数据存储 | subtask_id, title, output(JSONB), account_id, card_link |
| `subtasks_tasks4` | 内容类型存储 | tasks_id, content_type |

## 技术栈

| 技术 | 用途 |
|------|------|
| [pyJianYingDraft](https://github.com/boyanus/pyJianYingDraft) | 剪映草稿文件操作 |
| psycopg2 | PostgreSQL 数据库连接 |
| requests | 素材下载 |
| psutil | 进程管理 |
| pyautogui / uiautomation / win32gui | GUI 自动化（弹窗检测） |

## 许可证

内部项目，仅供内部使用。
