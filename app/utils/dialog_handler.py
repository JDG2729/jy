"""
弹窗检测与关闭模块
自动检测并关闭剪映的错误弹窗
"""

import time
import importlib
import importlib.util
import logging

logger = logging.getLogger(__name__)

# 按需导入 GUI 相关库
_win32gui_spec = importlib.util.find_spec("win32gui")
if _win32gui_spec:
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

_pyautogui_spec = importlib.util.find_spec("pyautogui")
if _pyautogui_spec:
    pyautogui = importlib.import_module("pyautogui")
    HAS_PYAUTOGUI = True
else:
    pyautogui = None
    HAS_PYAUTOGUI = False

_uiautomation_spec = importlib.util.find_spec("uiautomation")
if _uiautomation_spec:
    try:
        uiautomation = importlib.import_module("uiautomation")
        HAS_UIAUTOMATION = True
    except ImportError:
        uiautomation = None
        HAS_UIAUTOMATION = False
else:
    uiautomation = None
    HAS_UIAUTOMATION = False


def detect_and_close_error_dialog(max_attempts: int = 3) -> bool:
    """
    检测并自动关闭剪映的错误弹窗（如"草稿箱错误"等）

    Args:
        max_attempts: 最大尝试次数

    Returns:
        是否成功关闭了弹窗
    """
    try:
        # 方法1: 使用 Windows API 检测弹窗窗口
        if HAS_WIN32GUI:
            try:
                def enum_windows_callback(hwnd, windows):
                    if win32gui.IsWindowVisible(hwnd):
                        window_text = win32gui.GetWindowText(hwnd)
                        class_name = win32gui.GetClassName(hwnd)
                        error_keywords = [
                            '错误', 'error', '失败', '提示', '警告',
                            '草稿箱', '草稿列表', '列表异常', 'draft',
                            'box', '异常', 'anomaly'
                        ]
                        window_text_lower = window_text.lower()
                        if any(keyword in window_text_lower for keyword in error_keywords):
                            try:
                                rect = win32gui.GetWindowRect(hwnd)
                                width = rect[2] - rect[0]
                                height = rect[3] - rect[1]
                                if 200 <= width <= 800 and 100 <= height <= 400:
                                    windows.append((hwnd, window_text, class_name))
                            except Exception:
                                windows.append((hwnd, window_text, class_name))
                    return True

                error_windows = []
                win32gui.EnumWindows(enum_windows_callback, error_windows)

                for hwnd, window_text, class_name in error_windows:
                    logger.info(f"   🔍 检测到可能的错误弹窗: '{window_text}' (类名: {class_name})")

                    # 特殊处理："草稿列表异常"弹窗需要点击"取消"按钮
                    if '草稿列表异常' in window_text or '列表异常' in window_text:
                        clicked = False
                        if HAS_UIAUTOMATION:
                            try:
                                uia = uiautomation
                                win = uia.WindowControl(SubName="草稿列表异常", searchDepth=5)
                                if win.Exists(0):
                                    btn = win.ButtonControl(SubName="取消", searchDepth=10)
                                    if not btn.Exists(0):
                                        btn = win.TextControl(SubName="取消", searchDepth=10)
                                    if btn.Exists(0):
                                        btn.Click(simulateMove=False)
                                        logger.info(f"   ✅ 已通过控件名点击'取消'关闭'草稿列表异常'弹窗")
                                        clicked = True
                            except Exception as e:
                                logger.debug(f"   uiautomation 查找'取消'失败: {e}")
                        if not clicked and HAS_WIN32GUI:
                            try:
                                rect = win32gui.GetWindowRect(hwnd)
                                cancel_button_x = rect[2] - 100
                                cancel_button_y = rect[3] - 40
                                win32gui.SetForegroundWindow(hwnd)
                                time.sleep(0.3)
                                win32api.SetCursorPos((cancel_button_x, cancel_button_y))
                                time.sleep(0.2)
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                time.sleep(0.1)
                                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                logger.info(f"   ✅ 已通过坐标点击'取消'关闭'草稿列表异常'弹窗")
                                clicked = True
                            except Exception as e:
                                logger.warning(f"   ⚠️ 坐标点击'取消'失败: {e}")
                        if clicked:
                            time.sleep(0.5)
                            return True

                    # 发送 ESC 键
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.2)
                        win32api.keybd_event(0x1B, 0, 0, 0)
                        time.sleep(0.1)
                        win32api.keybd_event(0x1B, 0, win32con.KEYEVENTF_KEYUP, 0)
                        logger.info(f"   ✅ 已尝试按 ESC 键关闭弹窗: '{window_text}'")
                        time.sleep(0.5)
                        return True
                    except Exception as e:
                        logger.debug(f"   使用 ESC 键关闭弹窗失败: {e}")

                    # 发送 WM_CLOSE 消息
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.2)
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        logger.info(f"   ✅ 已尝试发送关闭消息关闭弹窗: '{window_text}'")
                        time.sleep(0.5)
                        return True
                    except Exception as e:
                        logger.debug(f"   发送关闭消息失败: {e}")

                if not error_windows:
                    return False

            except Exception as e:
                logger.debug(f"   使用 Windows API 检测弹窗失败: {e}")

        # 方法2: 使用 pyautogui（备选）
        if HAS_PYAUTOGUI and not HAS_WIN32GUI:
            try:
                screen_width, screen_height = pyautogui.size()
                click_x = screen_width // 2
                click_y = screen_height // 2 + 100
                pyautogui.click(click_x, click_y)
                logger.info(f"   ✅ 已尝试点击屏幕中心位置关闭弹窗 ({click_x}, {click_y})")
                time.sleep(0.5)
                return True
            except Exception as e:
                logger.debug(f"   使用 pyautogui 点击弹窗失败: {e}")

        return False

    except Exception as e:
        logger.debug(f"   检测弹窗时出错: {e}")
        return False
