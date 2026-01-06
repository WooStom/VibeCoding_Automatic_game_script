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
        self.last_click_ts: float = 0.0

    def run(self) -> None:
        state = State.S0_START
        self.logger.info(f"进入状态 {state.value}")
        try:
            while True:
                if state == State.S0_START:
                    if not self.ensure_game_running():
                        self.fail(state, "未检测到游戏进程且启动失败")
                        return
                    if not self.wait_game_ready():
                        self.fail(state, "等待游戏窗口就绪超时")
                        return
                    if not self.ensure_foreground():
                        self.fail(state, "无法找到或激活游戏窗口")
                        return
                    state = State.S1_WAIT_LOGIN
                    self.logger.info(f"切换到 {state.value}")

                elif state == State.S1_WAIT_LOGIN:
                    state = self.wait_login_with_safe_clicks(state)
                    if state is None:
                        return
                    self.logger.info(f"切换到 {state.value}")

                elif state == State.S2_CLICK_LOGIN:
                    if not self.ensure_foreground():
                        self.fail(state, "无法激活窗口执行点击")
                        return

                    point = screen.window_safe_click_point(config.GAME_WINDOW_TITLE)
                    if point is None:
                        self.fail(state, "无法获取安全点击位置")
                        return

                    screen.click_point(point)
                    self.logger.info(f"执行登录点击 {point}")

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
        best_score = -1.0
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

    def fail(self, state: State, reason: str, kill: bool = True) -> None:
        self.logger.error(f"[{state.value}] 失败: {reason}")
        img = screen.capture_window(config.GAME_WINDOW_TITLE)
        shot_path = screen.save_screenshot(img, state.value, prefix="fail")
        self.logger.info(f"[{state.value}] 失败截图保存到: {shot_path}")
        if kill:
            self.kill_game()
        sys.exit(1)

    def ensure_game_running(self) -> bool:
        if self._has_running_game_process():
            return True
        self.logger.info("未检测到游戏进程，尝试通过 Steam 启动")
        if self._launch_game_via_steam():
            return self._wait_for_process(config.STATE_TIMEOUTS["GAME_BOOT"])
        return False

    def wait_game_ready(self) -> bool:
        self.logger.info("等待游戏就绪…")
        start = time.time()
        while time.time() - start <= config.GAME_READY_TIMEOUT:
            hwnd = screen.get_window_handle(config.GAME_WINDOW_TITLE)
            has_hwnd = hwnd is not None
            focused = screen.focus_window(hwnd) if hwnd else False
            image, source, (width, height) = screen.capture_window_with_info(config.GAME_WINDOW_TITLE)
            is_valid_shape = width > 0 and height > 0
            black = screen.is_mostly_black(image)
            self.logger.info(
                f"[{State.S0_START.value}] hwnd={'Y' if has_hwnd else 'N'}, focus={'Y' if focused else 'N'}, "
                f"截图来源={source}, 尺寸={width}x{height}, 黑屏={black}"
            )
            if (has_hwnd and focused) or (is_valid_shape and not black):
                return True
            time.sleep(config.GAME_READY_CHECK_INTERVAL)
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

    def wait_login_with_safe_clicks(self, state: State) -> Optional[State]:
        start = time.time()
        best_mainmenu = -1.0
        best_connecting = -1.0

        while time.time() - start <= config.STATE_TIMEOUTS["S1_WAIT_LOGIN"]:
            img = screen.capture_window(config.GAME_WINDOW_TITLE)

            connecting_hit, _, connecting_score = screen.template_match(img, config.CONNECTING_MARKER)
            if connecting_score > best_connecting:
                best_connecting = connecting_score
                self.logger.info(f"[{state.value}] 连接最高分更新为 {best_connecting:.4f}")
            if connecting_hit:
                self.logger.info(f"[{state.value}] 检测到连接标记，停止点击，匹配分 {connecting_score:.4f}")
                return State.S3_WAIT_MAINMENU

            main_hit, _, main_score = screen.template_match(img, config.MAINMENU_MARKER)
            if main_score > best_mainmenu:
                best_mainmenu = main_score
                self.logger.info(f"[{state.value}] 主菜单最高分更新为 {best_mainmenu:.4f}")
            if main_hit:
                self.logger.info(f"[{state.value}] 检测到主菜单，匹配分 {main_score:.4f}")
                return State.S_OK

            now = time.time()
            since_click = now - self.last_click_ts
            if since_click < config.CLICK_COOLDOWN:
                remaining = config.CLICK_COOLDOWN - since_click
                self.logger.info(f"[{state.value}] 冷却中跳过点击，剩余 {remaining:.2f}s")
            else:
                if not self.ensure_foreground():
                    self.fail(state, "无法激活窗口执行安全点击")
                    return None
                point = screen.window_safe_click_point(config.GAME_WINDOW_TITLE)
                if point is None:
                    self.fail(state, "无法获取窗口安全点击位置")
                    return None
                screen.click_point(point)
                self.last_click_ts = now
                self.logger.info(f"[{state.value}] 安全点击窗口坐标 {point}")

            time.sleep(config.CHECK_INTERVAL)

        self.fail(
            state,
            f"登录等待超时，主菜单最高分 {best_mainmenu:.4f}，连接最高分 {best_connecting:.4f}",
        )
        return None


def main() -> None:
    machine = StateMachine()
    machine.run()


if __name__ == "__main__":
    main()
