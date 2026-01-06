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


def _get_window_handle(title: str) -> Optional[int]:
    hwnd = win32gui.FindWindow(None, title)
    if hwnd == 0:
        return None
    return hwnd


def _get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    try:
        rect = win32gui.GetWindowRect(hwnd)
    except win32gui.error:
        return None
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def get_window_rect(title: str) -> Optional[Tuple[int, int, int, int]]:
    hwnd = _get_window_handle(title)
    if hwnd is None:
        return None
    return _get_window_rect(hwnd)


def focus_window(hwnd: int) -> bool:
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except win32gui.error:
        return False


def capture_window(title: str) -> np.ndarray:
    hwnd = _get_window_handle(title)
    rect = _get_window_rect(hwnd) if hwnd else None
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


def click_point(point: Point) -> None:
    x, y = point
    pyautogui.click(x, y)


def window_safe_click_point(title: str, rx: float = 0.70, ry: float = 0.55) -> Optional[Point]:
    rect = get_window_rect(title)
    if rect is None:
        return None
    left, top, width, height = rect
    x = left + int(width * rx)
    y = top + int(height * ry)
    return x, y


def template_match(screen: np.ndarray, template_path: Path) -> Tuple[bool, Optional[Point], float]:
    if not template_path.is_file():
        return False, None, 0.0

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        return False, None, 0.0

    if screen.ndim == 3 and screen.shape[2] == 4:
        haystack = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
    elif screen.ndim == 3:
        haystack = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
    else:
        haystack = screen

    if haystack.shape[0] < template.shape[0] or haystack.shape[1] < template.shape[1]:
        return False, None, 0.0

    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    matched = max_val >= config.TEMPLATE_MATCH_THRESHOLD
    if not matched:
        return False, None, float(max_val)

    center_x = max_loc[0] + template.shape[1] // 2
    center_y = max_loc[1] + template.shape[0] // 2
    return True, (center_x, center_y), float(max_val)


def get_window_handle(title: str) -> Optional[int]:
    return _get_window_handle(title)


def capture_window_with_info(title: str) -> Tuple[np.ndarray, str, Tuple[int, int]]:
    hwnd = _get_window_handle(title)
    rect = _get_window_rect(hwnd) if hwnd else None
    if rect is None:
        with mss.mss() as sct:
            monitor = sct.monitors[config.MONITOR_INDEX]
            shot = sct.grab(monitor)
            img = np.array(shot)
            height, width = img.shape[0], img.shape[1]
            return img, "monitor", (width, height)

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

    return img, "window", (width, height)


def is_mostly_black(image: np.ndarray, mean_threshold: float = 1.0, nonzero_ratio: float = 0.01) -> bool:
    if image.size == 0:
        return True
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY) if image.shape[2] == 4 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    mean_val = float(gray.mean())
    ratio = float(np.count_nonzero(gray)) / gray.size
    return mean_val <= mean_threshold or ratio <= nonzero_ratio


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
