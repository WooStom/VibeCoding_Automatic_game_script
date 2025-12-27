import time
from pathlib import Path
from typing import Optional, Tuple

import cv2  # noqa: F401  # imported for future template matching
import mss
import numpy as np
import pyautogui
import win32con
import win32gui
import win32ui

import config

Point = Tuple[int, int]


def _get_window_rect(title: str) -> Optional[Tuple[int, int, int, int]]:
    hwnd = win32gui.FindWindow(None, title)
    if hwnd == 0:
        return None
    rect = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def capture_window(title: str) -> np.ndarray:
    rect = _get_window_rect(title)
    if rect is None:
        with mss.mss() as sct:
            monitor = sct.monitors[config.MONITOR_INDEX]
            shot = sct.grab(monitor)
            img = np.array(shot)
            return img

    left, top, width, height = rect
    hdesktop = win32gui.GetDesktopWindow()
    desktop_dc = win32gui.GetWindowDC(hdesktop)
    img_dc = win32ui.CreateDCFromHandle(desktop_dc)
    mem_dc = img_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(img_dc, width, height)
    mem_dc.SelectObject(bitmap)
    mem_dc.BitBlt((0, 0), (width, height), img_dc, (left, top), win32con.SRCCOPY)

    bmp_info = bitmap.GetInfo()
    bmp_str = bitmap.GetBitmapBits(True)
    img = np.frombuffer(bmp_str, dtype=np.uint8)
    img.shape = (bmp_info['bmHeight'], bmp_info['bmWidth'], 4)

    win32gui.DeleteObject(bitmap.GetHandle())
    mem_dc.DeleteDC()
    img_dc.DeleteDC()
    win32gui.ReleaseDC(hdesktop, desktop_dc)

    return img


def save_screenshot(image: np.ndarray, state_name: str, prefix: str) -> Path:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = config.LOG_DIR / f"{prefix}_{state_name}_{timestamp}.png"
    if image.ndim == 3 and image.shape[2] == 4:
        bgr_image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    elif image.ndim == 3:
        bgr_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    else:
        bgr_image = image
    cv2.imwrite(str(path), bgr_image)
    return path


def click_point(point: Point) -> None:
    x, y = point
    pyautogui.click(x, y)


def template_match(screen: np.ndarray, template_path: Path) -> Tuple[bool, Optional[Point]]:
    if not template_path.is_file():
        return False, None

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        return False, None

    if screen.ndim == 3 and screen.shape[2] == 4:
        haystack = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
    elif screen.ndim == 3:
        haystack = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
    else:
        haystack = screen

    if haystack.shape[0] < template.shape[0] or haystack.shape[1] < template.shape[1]:
        return False, None

    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    matched = max_val >= config.TEMPLATE_MATCH_THRESHOLD
    if not matched:
        return False, None

    center_x = max_loc[0] + template.shape[1] // 2
    center_y = max_loc[1] + template.shape[0] // 2
    return True, (center_x, center_y)
