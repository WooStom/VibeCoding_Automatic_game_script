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
                    state = State.S1_WAIT_LOGIN
                    self.logger.info(f"切换到 {state.value}")

                elif state == State.S1_WAIT_LOGIN:
                    pos = self.wait_for_marker(
                        marker_path=config.LOGIN_MARKER,
                        timeout=config.STATE_TIMEOUTS["S1_WAIT_LOGIN"],
                        state=state,
                    )
                    if pos is None:
                        self.fail(state, "未检测到登录界面标记")
                        return
                    self.last_marker_position = pos
                    state = State.S2_CLICK_LOGIN
                    self.logger.info(f"切换到 {state.value}")

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

                elif state == State.S3_WAIT_MAINMENU:
                    pos = self.wait_for_marker(
                        marker_path=config.MAINMENU_MARKER,
                        timeout=config.STATE_TIMEOUTS["S3_WAIT_MAINMENU"],
                        state=state,
                    )
                    if pos is None:
                        self.fail(state, "未检测到主菜单标记")
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

    def wait_for_marker(self, marker_path, timeout: float, state: State) -> Optional[Tuple[int, int]]:
        start = time.time()
        while time.time() - start <= timeout:
            img = screen.capture_window(config.GAME_WINDOW_TITLE)
            matched, pos = screen.template_match(img, marker_path)
            if matched:
                self.logger.info(f"[{state.value}] 找到标记 {marker_path.name} at {pos}")
                return pos
            time.sleep(config.CHECK_INTERVAL)
        self.logger.error(f"[{state.value}] 超时未找到标记 {marker_path.name}")
        return None

    def wait_for_transition(self, expected_marker, timeout: float, state: State) -> bool:
        start = time.time()
        while time.time() - start <= timeout:
            img = screen.capture_window(config.GAME_WINDOW_TITLE)
            matched, _ = screen.template_match(img, expected_marker)
            if matched:
                self.logger.info(f"[{state.value}] 发现过渡标记 {expected_marker.name}")
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
