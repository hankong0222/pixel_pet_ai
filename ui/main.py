from __future__ import annotations

import json
import random
import sys
from ctypes import byref, c_int, sizeof, windll
from json import JSONDecodeError
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QMovie
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QWidget


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_ROOT = PROJECT_ROOT / "asset" / "export"
DEFAULT_CAT = "cat-1-64-64"
DEFAULT_ANIMATION = "sit"
DEFAULT_SCALE = 4
DEFAULT_MOVIE_SPEED = 55
RANDOM_BEHAVIOR_MIN_MS = 3500
RANDOM_BEHAVIOR_MAX_MS = 7000
WALK_STEP_MS = 110
WALK_STEP_PX = 10
WALK_STEP_RANGE = (18, 42)


ACTION_ALIASES = {
    "idle_sit": "idle-sit",
    "idle_stand": "idle-stand",
    "sit": "sit",
    "idle_lie": "idle-lie",
    "walk_down": "walk-down",
    "walk_up": "walk-up",
    "walk_left": "walk-left",
    "walk_right": "walk-right",
    "run_down": "run-down",
    "run_up": "run-up",
    "run_left": "run-left",
    "run_right": "run-right",
    "eat_front": "eat-food-stand-front",
    "eat_back": "eat-food-stand-back",
    "eat_left": "eat-food-stand-left",
    "eat_right": "eat-food-stand-right",
    "hiss_left": "hiss-front-left",
    "hiss_right": "hiss-front-right",
    "jump_back": "jump-back",
    "jump_left": "jump-left",
    "jump_right": "jump-right",
    "on_hind_legs": "on-hind-legs",
    "yawn": "yawn-sit-front",
}


IDLE_SLUGS = [
    "idle-sit",
    "idle-stand",
    "sit",
    "idle-lie",
    "tail-wag-sit-front",
    "tail-wag-sit-left",
    "tail-wag-sit-right",
    "tail-wag-stand-left",
    "tail-wag-stand-right",
    "tail-wag-lie-left",
    "tail-wag-lie-right",
]

EMOTE_SLUGS = [
    "lick-paw-sit-front",
    "lick-paw-lie-front",
    "meow-sit-front",
    "meow-lie-front",
    "meow-stand-front",
    "scratch-sit-left",
    "scratch-sit-right",
    "eat-food-stand-front",
    "eat-food-stand-left",
    "eat-food-stand-right",
    "hiss-front-left",
    "hiss-front-right",
    "jump-left",
    "jump-right",
    "jump-back",
    "on-hind-legs",
    "yawn-sit-front",
]

SLEEP_SLUGS = [
    "sleep-1-left-front",
    "sleep-1-right-front",
    "sleep-1-left-back",
    "sleep-1-right-back",
    "sleep-2-left-front",
    "sleep-2-right-front",
    "sleep-3-left-front",
    "sleep-3-right-front",
    "sleep-4-left-front",
    "sleep-4-right-front",
    "sleep-5-left-front",
    "sleep-5-right-front",
]


def load_manifest(cat_name: str) -> dict:
    manifest_path = EXPORT_ROOT / cat_name / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    raw_manifest = manifest_path.read_bytes()

    for encoding in ("utf-8", "utf-8-sig", "gbk", "cp1251", "cp866"):
        try:
            return json.loads(raw_manifest.decode(encoding))
        except (UnicodeDecodeError, JSONDecodeError):
            continue

    return json.loads(raw_manifest.decode("utf-8", errors="replace"))


class PetWindow(QWidget):
    def __init__(self, cat_name: str = DEFAULT_CAT, animation_slug: str = DEFAULT_ANIMATION) -> None:
        super().__init__()
        self.cat_name = cat_name
        self.manifest = load_manifest(cat_name)
        self.animations_by_slug = {
            animation["slug"]: animation for animation in self.manifest["animations"]
        }
        self.drag_offset = QPoint()
        self.current_animation_slug = ""
        self.current_animation_dir = ""
        self.scale = DEFAULT_SCALE
        self.movie_speed = DEFAULT_MOVIE_SPEED
        self.current_movie: QMovie | None = None
        self.walk_direction = 0
        self.walk_steps_remaining = 0

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setWindowTitle("Pixel Pet")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )

        self.behavior_timer = QTimer(self)
        self.behavior_timer.setSingleShot(True)
        self.behavior_timer.timeout.connect(self.play_random_behavior)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.advance_walk)
        self.walk_timer.setInterval(WALK_STEP_MS)

        self.play_action(animation_slug)
        self.move_to_visible_spot()
        self.start_random_behavior()

    def animation_for_slug(self, slug: str) -> dict | None:
        return self.animations_by_slug.get(slug)

    def call_action(self, action_name: str) -> None:
        if hasattr(self, action_name):
            method = getattr(self, action_name)
            if callable(method):
                method()
                return

        slug = ACTION_ALIASES.get(action_name, action_name.replace("_", "-"))
        self.play_action(slug)

    def set_animation_by_directory(self, animation_dir: str) -> None:
        animation = next(
            (item for item in self.manifest["animations"] if item["directory"] == animation_dir),
            None,
        )
        if animation is None:
            return

        gif_path = EXPORT_ROOT / self.cat_name / animation_dir / "animation.gif"
        if not gif_path.exists():
            return

        movie = QMovie(str(gif_path))
        if not movie.isValid():
            raise RuntimeError(f"Invalid GIF: {gif_path}")

        base_size = self.manifest.get("cellSize", 64)
        scaled_size = QSize(base_size * self.scale, base_size * self.scale)
        movie.setScaledSize(scaled_size)
        movie.setSpeed(self.movie_speed)

        self.current_animation_slug = animation["slug"]
        self.current_animation_dir = animation_dir
        self.current_movie = movie
        self.label.setMovie(movie)
        self.label.move(0, 0)
        self.label.setFixedSize(scaled_size)
        self.setFixedSize(scaled_size)
        movie.start()

    def play_action(self, slug: str) -> None:
        self.stop_walk()
        animation = self.animation_for_slug(slug)
        if animation is None:
            return
        self.set_animation_by_directory(animation["directory"])

    def play_random_from(self, slugs: list[str]) -> None:
        available = [slug for slug in slugs if slug in self.animations_by_slug]
        if not available:
            return
        self.play_action(random.choice(available))

    def idle_sit(self) -> None:
        self.play_action("idle-sit")

    def idle_stand(self) -> None:
        self.play_action("idle-stand")

    def sit(self) -> None:
        self.play_action("sit")

    def idle_lie(self) -> None:
        self.play_action("idle-lie")

    def walk_left(self) -> None:
        self.start_walk("walk-left", -1)

    def walk_right(self) -> None:
        self.start_walk("walk-right", 1)

    def run_left(self) -> None:
        self.play_action("run-left")

    def run_right(self) -> None:
        self.play_action("run-right")

    def run_up(self) -> None:
        self.play_action("run-up")

    def run_down(self) -> None:
        self.play_action("run-down")

    def eat(self) -> None:
        self.play_random_from(
            ["eat-food-stand-front", "eat-food-stand-left", "eat-food-stand-right"],
        )

    def sleep(self) -> None:
        self.play_random_from(SLEEP_SLUGS)

    def hiss(self) -> None:
        self.play_random_from(["hiss-front-left", "hiss-front-right"])

    def jump(self) -> None:
        self.play_random_from(["jump-left", "jump-right", "jump-back"])

    def yawn(self) -> None:
        self.play_action("yawn-sit-front")

    def random_idle(self) -> None:
        self.play_random_from(IDLE_SLUGS)

    def random_emote(self) -> None:
        self.play_random_from(EMOTE_SLUGS)

    def random_walk(self) -> None:
        if random.choice((True, False)):
            self.walk_left()
        else:
            self.walk_right()

    def start_walk(self, slug: str, direction: int) -> None:
        animation = self.animation_for_slug(slug)
        if animation is None:
            return

        self.set_animation_by_directory(animation["directory"])
        self.walk_direction = direction
        self.walk_steps_remaining = random.randint(*WALK_STEP_RANGE)
        self.walk_timer.start()

    def stop_walk(self) -> None:
        self.walk_timer.stop()
        self.walk_direction = 0
        self.walk_steps_remaining = 0

    def start_random_behavior(self) -> None:
        self.schedule_random_behavior()

    def stop_random_behavior(self) -> None:
        self.behavior_timer.stop()

    def schedule_random_behavior(self) -> None:
        delay = random.randint(RANDOM_BEHAVIOR_MIN_MS, RANDOM_BEHAVIOR_MAX_MS)
        self.behavior_timer.start(delay)

    def play_random_behavior(self) -> None:
        choice = random.choice(
            ["idle", "idle", "emote", "walk", "walk", "sleep"],
        )

        if choice == "idle":
            self.random_idle()
        elif choice == "emote":
            self.random_emote()
        elif choice == "sleep":
            self.sleep()
        else:
            self.random_walk()

        self.schedule_random_behavior()

    def advance_walk(self) -> None:
        if self.walk_steps_remaining <= 0:
            self.stop_walk()
            self.random_idle()
            return

        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        next_x = self.x() + (WALK_STEP_PX * self.walk_direction)
        next_y = self.y()

        if next_x < available.left():
            self.walk_direction = 1
            self.set_left_facing(False)
            next_x = available.left()
        elif next_x + self.width() > available.right():
            self.walk_direction = -1
            self.set_left_facing(True)
            next_x = available.right() - self.width()

        self.move(next_x, next_y)
        self.walk_steps_remaining -= 1

    def set_left_facing(self, left_facing: bool) -> None:
        target_slug = "walk-left" if left_facing else "walk-right"
        if self.current_animation_slug != target_slug:
            animation = self.animation_for_slug(target_slug)
            if animation is not None:
                self.set_animation_by_directory(animation["directory"])

    def move_to_visible_spot(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(120, 120)
            return

        available = screen.availableGeometry()
        x = available.left() + 80
        y = available.bottom() - self.height() - 120
        self.move(x, max(available.top() + 40, y))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.apply_windows_borderless_fix()

    def apply_windows_borderless_fix(self) -> None:
        if sys.platform != "win32":
            return

        hwnd = int(self.winId())
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWA_BORDER_COLOR = 34
        DWMWCP_DONOTROUND = 1
        DWMWA_NCRENDERING_POLICY = 2
        DWMNCRP_DISABLED = 1
        DWMWA_COLOR_NONE = 0xFFFFFFFE

        try:
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                byref(c_int(DWMWCP_DONOTROUND)),
                sizeof(c_int),
            )
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                byref(c_int(DWMWA_COLOR_NONE)),
                sizeof(c_int),
            )
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_NCRENDERING_POLICY,
                byref(c_int(DWMNCRP_DISABLED)),
                sizeof(c_int),
            )
        except Exception:
            pass

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)

        behavior_action = QAction("Random Behavior", self)
        behavior_action.setCheckable(True)
        behavior_action.setChecked(self.behavior_timer.isActive())
        behavior_action.triggered.connect(self.toggle_random_behavior)
        menu.addAction(behavior_action)

        walk_action = QAction("Random Walk Now", self)
        walk_action.triggered.connect(self.random_walk)
        menu.addAction(walk_action)

        idle_action = QAction("Idle Now", self)
        idle_action.triggered.connect(self.random_idle)
        menu.addAction(idle_action)

        menu.addSeparator()
        animation_menu = menu.addMenu("Animations")

        for animation in self.manifest["animations"]:
            action = QAction(animation["label"], self)
            action.setCheckable(True)
            action.setChecked(animation["directory"] == self.current_animation_dir)
            action.triggered.connect(
                lambda checked=False, directory=animation["directory"]: self.set_animation_by_directory(directory)
            )
            animation_menu.addAction(action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        menu.exec(QCursor.pos())
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def toggle_random_behavior(self, enabled: bool) -> None:
        if enabled:
            self.start_random_behavior()
            return
        self.stop_random_behavior()


def main() -> int:
    app = QApplication(sys.argv)
    window = PetWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
