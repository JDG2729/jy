"""
进程管理模块
负责关闭和启动剪映进程
"""

import time
import importlib.util
import logging

logger = logging.getLogger(__name__)

# 按需导入 psutil
_psutil_spec = importlib.util.find_spec("psutil")
if _psutil_spec:
    psutil = importlib.import_module("psutil")
    HAS_PSUTIL = True
else:
    psutil = None
    HAS_PSUTIL = False


def close_all_jianying_processes() -> int:
    """
    完全关闭所有剪映相关进程（名称包含 JianyingPro 的进程）

    Returns:
        关闭的进程数量
    """
    closed_count = 0
    if not HAS_PSUTIL:
        return 0
    try:
        procs_to_close = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = (proc.info or {}).get('name') or ''
                if 'JianyingPro' in name:
                    procs_to_close.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        for proc in procs_to_close:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                closed_count += 1
                logger.info(f"   🔄 已关闭剪映进程 (PID={proc.pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
            except Exception as e:
                logger.debug(f"   关闭进程 {proc.pid} 时出错: {e}")

        if closed_count > 0:
            logger.info(f"   ✅ 已完全关闭 {closed_count} 个剪映进程")
            time.sleep(2)  # 等待进程完全退出
    except Exception as e:
        logger.debug(f"   关闭剪映进程时出错: {e}")
    return closed_count
