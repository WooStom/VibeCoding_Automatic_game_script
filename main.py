import os
import subprocess
import sys
import time
from enum import Enum
from typing import Optional, Tuple

import psutil
import pyautogui

import config
from utils.logger import setup_logger
from utils import screen


class State(Enum):
    S0_START = "S0_START"
    S1_WAIT_LOGIN = "S1_WAIT_LOGIN"
    S2_CLICK_LOGIN = "S2_CLICK_LOGIN"
    S3_WAIT_MAINMENU = "S3_WAIT_MAINMENU"
    S_OK = "S_OK"
    S_FAIL = "S_FAIL"


class StateMachine:
    def __init__(self) -> None:
        self.logger = setup_logger()
        self.last_marker_position: Optional[Tuple[int, int]] = None

    def run(self) -> None:
        state = State.S0_START
        self.logger.info(f"进入状态 {state.value}")
        try:
            while True:
                if state == State.S0_START:
                    if not self.ensure_game_running():
                        self.fail(state, "未检测到游戏进程且启动失败")
                        return
                    if not self.ensure_foreground():
                        self.fail(state, "无法找到或激活游戏窗口")
                        return
                    state = State.S1_WAIT_LOGIN
                    self.logger.info(f"切换到 {state.value}")
                    self.capture_debug_snapshot(state)

                elif state == State.S1_WAIT_LOGIN:
                    pos, best_score = self.wait_for_marker(
                        marker_path=config.LOGIN_MARKER,
                        timeout=config.STATE_TIMEOUTS["S1_WAIT_LOGIN"],
                        state=state,
                    )
                    if pos is None:
                        self.fail(state, f"未检测到登录界面标记，最高分 {best_score:.4f}")
                        return
                    self.last_marker_position = pos
                    state = State.S2_CLICK_LOGIN
                    self.logger.info(f"切换到 {state.value}")
                    self.capture_debug_snapshot(state)

                elif state == State.S2_CLICK_LOGIN:
                    if self.last_marker_position:
                        screen.click_point(self.last_marker_position)
                        self.logger.info("执行登录点击")
                    else:
                        self.logger.warning("缺少登录标记位置，使用屏幕中心点击")
                        width, height = pyautogui.size()
                        screen.click_point((width // 2, height // 2))

                    if not self.wait_for_transition(
                        expected_marker=config.CONNECTING_MARKER,
                        timeout=config.STATE_TIMEOUTS["S2_CLICK_LOGIN"],
                        state=state,
                    ):
                        self.fail(state, "登录点击后未进入连接状态")
                        return

                    state = State.S3_WAIT_MAINMENU
                    self.logger.info(f"切换到 {state.value}")
                    self.capture_debug_snapshot(state)

                elif state == State.S3_WAIT_MAINMENU:
                    pos, best_score = self.wait_for_marker(
                        marker_path=config.MAINMENU_MARKER,
                        timeout=config.STATE_TIMEOUTS["S3_WAIT_MAINMENU"],
                        state=state,
                    )
                    if pos is None:
                        self.fail(state, f"未检测到主菜单标记，最高分 {best_score:.4f}")
                        return
                    self.logger.info("检测到主菜单")
                    state = State.S_OK

                if state == State.S_OK:
                    self.logger.info("流程完成")
                    print("成功进入主菜单")
                    pyautogui.alert("成功进入主菜单")
                    return
        except Exception as exc:  # noqa: BLE001
            self.fail(state, f"异常: {exc!r}")

    def wait_for_marker(self, marker_path, timeout: float, state: State) -> Tuple[Optional[Tuple[int, int]], float]:
        start = time.time()
        best_score = 0.0
        while time.time() - start <= timeout:
            img = screen.capture_window(config.GAME_WINDOW_TITLE)
            matched, pos, score = screen.template_match(img, marker_path)
            if score > best_score:
                best_score = score
                self.logger.info(f"[{state.value}] 当前最高分 {best_score:.4f}")
            if matched:
                self.logger.info(f"[{state.value}] 找到标记 {marker_path.name} at {pos}，匹配分 {score:.4f}")
                return pos, best_score
            time.sleep(config.CHECK_INTERVAL)
        self.logger.error(f"[{state.value}] 超时未找到标记 {marker_path.name}，最高分 {best_score:.4f}")
        return None, best_score

    def wait_for_transition(self, expected_marker, timeout: float, state: State) -> bool:
        start = time.time()
        while time.time() - start <= timeout:
            img = screen.capture_window(config.GAME_WINDOW_TITLE)
            matched, _, score = screen.template_match(img, expected_marker)
            if matched:
                self.logger.info(f"[{state.value}] 发现过渡标记 {expected_marker.name}，匹配分 {score:.4f}")
                return True
            time.sleep(config.CHECK_INTERVAL)
        self.logger.error(f"[{state.value}] 过渡超时 {expected_marker.name}")
        return False

    def fail(self, state: State, reason: str) -> None:
        self.logger.error(f"[{state.value}] 失败: {reason}")
        img = screen.capture_window(config.GAME_WINDOW_TITLE)
        shot_path = screen.save_screenshot(img, state.value, prefix="fail")
        self.logger.info(f"[{state.value}] 失败截图保存到: {shot_path}")
        self.kill_game()
        sys.exit(1)

    def capture_debug_snapshot(self, state: State) -> None:
        img = screen.capture_window(config.GAME_WINDOW_TITLE)
        shot_path = screen.save_screenshot(img, state.value, prefix="debug")
        self.logger.info(f"[{state.value}] 进入状态截图: {shot_path}")

    def ensure_game_running(self) -> bool:
        if self._has_running_game_process():
            return True
        self.logger.info("未检测到游戏进程，尝试通过 Steam 启动")
        if self._launch_game_via_steam():
            return self._wait_for_process(config.STATE_TIMEOUTS["GAME_BOOT"])
        return False

    def ensure_foreground(self) -> bool:
        hwnd = screen.get_window_handle(config.GAME_WINDOW_TITLE)
        if hwnd is None:
            return False
        focused = screen.focus_window(hwnd)
        if not focused:
            self.logger.warning("尝试激活窗口失败")
        return focused

    def _has_running_game_process(self) -> bool:
        for proc in psutil.process_iter(attrs=["name"]):
            try:
                if proc.info["name"] in config.GAME_PROCESS_NAMES:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def _launch_game_via_steam(self) -> bool:
        try:
            if os.name == "nt":
                os.startfile(config.STEAM_GAME_URI)  # type: ignore[attr-defined]
                return True
        except OSError:
            self.logger.warning("steam:// URI 启动失败，尝试使用 steam.exe")

        try:
            subprocess.Popen(config.STEAM_APP_LAUNCH)
            return True
        except OSError as exc:
            self.logger.error(f"Steam 启动失败: {exc!r}")
            return False

    def _wait_for_process(self, timeout: float) -> bool:
        start = time.time()
        while time.time() - start <= timeout:
            if self._has_running_game_process():
                self.logger.info("检测到游戏进程已启动")
                return True
            time.sleep(1.0)
        self.logger.error("等待游戏进程超时")
        return False

    def kill_game(self) -> None:
        for proc in psutil.process_iter(attrs=["name", "pid"]):
            try:
                if proc.info["name"] in config.GAME_PROCESS_NAMES:
                    self.logger.info(f"结束进程 {proc.info['name']} ({proc.info['pid']})")
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


def main() -> None:
    machine = StateMachine()
    machine.run()


if __name__ == "__main__":
    main()
