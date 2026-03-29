from __future__ import annotations

import json
import random
import sys
from ctypes import byref, c_int, sizeof, windll
from json import JSONDecodeError
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QMovie, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QWidget


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_ROOT = PROJECT_ROOT / "asset" / "export"
DEFAULT_CAT = "all-cats-black"
DEFAULT_ANIMATION = "idle"
DEFAULT_SCALE = 4
DEFAULT_MOVIE_SPEED = 55
RANDOM_BEHAVIOR_MIN_MS = 3500
RANDOM_BEHAVIOR_MAX_MS = 7000
WALK_STEP_MS = 110
WALK_STEP_PX = 10
WALK_STEP_RANGE = (18, 42)
JUMP_STEP_COUNT = 8
JUMP_STEP_MS = 55
JUMP_STEP_PX = 14
CLICK_DRAG_THRESHOLD = 12
PET_HOLD_MS = 600
LOOK_RADIUS_PX = 220
FOLLOW_RADIUS_PX = 170
FOLLOW_STEP_PX = 8
CLICK_STREAK_RESET_MS = 900
ANNOYED_HOLD_MS = 1200
ANNOYED_ESCAPE_STEPS = (20, 34)


ACTION_ALIASES = {
    "idle": "idle",
    "happy": "happy",
    "full": "full",
    "sleeping": "sleeping",
    "chilling": "chilling",
    "prone": "prone",
    "stay_box": "stay-box",
    "hide_in_box": "hide-in-box",
    "out_of_box": "out-of-box",
    "cry": "cry",
    "dance": "dance",
    "tickle": "tickle",
    "supprised": "supprised",
    "jumping": "jumping",
    "dying": "dying",
    "running": "running",
    "running_left": "running-left",
    "get_hurts": "get-hurts",
    "attack": "attack",
    "excited": "excited",
}


IDLE_SLUGS = [
    "idle",
    "chilling",
    "happy",
    "full",
]

EMOTE_SLUGS = [
    "happy",
    "full",
    "stay-box",
    "hide-in-box",
    "out-of-box",
    "cry",
    "dance",
    "tickle",
    "supprised",
    "jumping",
    "dying",
    "get-hurts",
    "attack",
    "excited",
]

SLEEP_SLUGS = [
    "sleeping",
    "prone",
    "chilling",
]


def load_manifest(cat_name: str) -> dict:
    cat_root = EXPORT_ROOT / cat_name
    manifest_candidates = [
        cat_root / "manifest.named.json",
        cat_root / "manifest.json",
    ]
    manifest_path = next((path for path in manifest_candidates if path.exists()), None)
    if manifest_path is None:
        raise FileNotFoundError(f"Manifest not found in: {cat_root}")
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
        self.drag_start_global = QPoint()
        self.press_global_pos = QPoint()
        self.was_dragging = False
        self.current_animation_slug = ""
        self.current_animation_dir = ""
        self.scale = DEFAULT_SCALE
        self.movie_speed = DEFAULT_MOVIE_SPEED
        self.current_movie: QMovie | None = None
        self.walk_direction = 0
        self.walk_steps_remaining = 0
        self.jump_direction = 0
        self.jump_steps_remaining = 0
        self.click_streak = 0
        self.interaction_locked = False
        self.pending_jump_direction: int | None = None
        self.annoyed_escape_active = False

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

        self.pet_timer = QTimer(self)
        self.pet_timer.setSingleShot(True)
        self.pet_timer.timeout.connect(self.react_to_pet_hold)

        self.click_streak_timer = QTimer(self)
        self.click_streak_timer.setSingleShot(True)
        self.click_streak_timer.timeout.connect(self.reset_click_streak)

        self.annoyed_timer = QTimer(self)
        self.annoyed_timer.setSingleShot(True)
        self.annoyed_timer.timeout.connect(self.finish_annoyed_sequence)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.advance_walk)
        self.walk_timer.setInterval(WALK_STEP_MS)

        self.jump_timer = QTimer(self)
        self.jump_timer.timeout.connect(self.advance_jump)
        self.jump_timer.setInterval(JUMP_STEP_MS)

        self.play_action(animation_slug)
        self.move_to_visible_spot()
        self.start_random_behavior()

    def animation_for_slug(self, slug: str) -> dict | None:
        return self.animations_by_slug.get(slug)

    def has_slug(self, slug: str) -> bool:
        return slug in self.animations_by_slug

    def play_first_available(self, slugs: list[str]) -> None:
        for slug in slugs:
            if self.has_slug(slug):
                self.play_action(slug)
                return

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
        self.label.setPixmap(QPixmap())
        self.label.setMovie(movie)
        self.label.move(0, 0)
        self.label.setFixedSize(scaled_size)
        self.setFixedSize(scaled_size)
        movie.start()

    def set_still_frame(self, slug: str, frame_name: str = "frame-01.png") -> None:
        animation = self.animation_for_slug(slug)
        if animation is None:
            return

        image_path = EXPORT_ROOT / self.cat_name / animation["directory"] / frame_name
        if not image_path.exists():
            self.play_action(slug)
            return

        base_size = self.manifest.get("cellSize", 64)
        scaled_size = QSize(base_size * self.scale, base_size * self.scale)
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.play_action(slug)
            return

        scaled_pixmap = pixmap.scaled(
            scaled_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

        if self.current_movie is not None:
            self.current_movie.stop()

        self.current_animation_slug = animation["slug"]
        self.current_animation_dir = animation["directory"]
        self.current_movie = None
        self.label.setMovie(None)
        self.label.setPixmap(scaled_pixmap)
        self.label.move(0, 0)
        self.label.setFixedSize(scaled_size)
        self.setFixedSize(scaled_size)

    def play_action(self, slug: str) -> None:
        self.stop_walk()
        self.stop_jump()
        animation = self.animation_for_slug(slug)
        if animation is None:
            fallback = self.manifest["animations"][0] if self.manifest.get("animations") else None
            if fallback is None:
                return
            self.set_animation_by_directory(fallback["directory"])
            return
        self.set_animation_by_directory(animation["directory"])

    def play_random_from(self, slugs: list[str]) -> None:
        available = [slug for slug in slugs if slug in self.animations_by_slug]
        if not available:
            return
        self.play_action(random.choice(available))

    def idle(self) -> None:
        self.play_first_available(["idle"])

    def happy(self) -> None:
        self.play_first_available(["happy"])

    def full(self) -> None:
        self.play_first_available(["full"])

    def sleeping(self) -> None:
        self.play_first_available(["sleeping"])

    def chilling(self) -> None:
        self.play_first_available(["chilling"])

    def prone(self) -> None:
        self.play_first_available(["prone"])

    def stay_box(self) -> None:
        self.play_first_available(["stay-box"])

    def hide_in_box(self) -> None:
        self.play_first_available(["hide-in-box"])

    def out_of_box(self) -> None:
        self.play_first_available(["out-of-box"])

    def cry(self) -> None:
        self.play_first_available(["cry"])

    def dance(self) -> None:
        self.play_first_available(["dance"])

    def tickle(self) -> None:
        self.play_first_available(["tickle"])

    def supprised(self) -> None:
        self.play_first_available(["supprised"])

    def jumping(self) -> None:
        self.play_first_available(["jumping"])

    def dying(self) -> None:
        self.play_first_available(["dying"])

    def running(self) -> None:
        self.play_first_available(["running"])

    def running_left(self) -> None:
        self.play_first_available(["running-left"])

    def get_hurts(self) -> None:
        self.play_first_available(["get-hurts"])

    def attack(self) -> None:
        self.play_first_available(["attack"])

    def excited(self) -> None:
        self.play_first_available(["excited"])

    def walk_left(self) -> None:
        if self.has_slug("running-left"):
            self.start_walk("running-left", -1)
            return
        self.play_first_available(["running"])

    def walk_right(self) -> None:
        if self.has_slug("running"):
            self.start_walk("running", 1)
            return
        self.play_first_available(["running-left", "running"])

    def eat(self) -> None:
        self.play_random_from(
            ["full", "stay-box", "hide-in-box", "out-of-box"],
        )

    def sleep(self) -> None:
        self.play_random_from(SLEEP_SLUGS)

    def hiss(self) -> None:
        self.play_random_from(["attack", "get-hurts", "cry"])

    def jump(self) -> None:
        if self.has_slug("jumping") or self.has_slug("excited"):
            self.play_random_from(["jumping", "excited"])
            return
        direction = random.choice((-1, 1))
        self.start_jump(direction)

    def random_idle(self) -> None:
        self.play_random_from(IDLE_SLUGS)

    def random_emote(self) -> None:
        self.play_random_from(EMOTE_SLUGS)

    def random_walk(self) -> None:
        if random.choice((True, False)):
            self.walk_left()
        else:
            self.walk_right()

    def react_to_click(self, global_pos: QPoint) -> None:
        self.stop_random_behavior()
        self.register_click()

        if self.click_streak >= 3:
            self.react_to_annoyance(global_pos)
            self.reset_click_streak()
            return

        local_pos = self.mapFromGlobal(global_pos)
        clicked_left_side = local_pos.x() < self.width() // 2

        if clicked_left_side:
            self.play_random_from(
                ["happy", "tickle", "hide-in-box", "attack"],
            )
        else:
            self.play_random_from(
                ["happy", "out-of-box", "supprised", "excited"],
            )

        self.schedule_random_behavior()

    def register_click(self) -> None:
        self.click_streak += 1
        self.click_streak_timer.start(CLICK_STREAK_RESET_MS)

    def reset_click_streak(self) -> None:
        self.click_streak = 0

    def react_to_annoyance(self, global_pos: QPoint) -> None:
        self.stop_random_behavior()
        self.stop_walk()
        self.stop_jump()
        self.interaction_locked = True
        self.annoyed_escape_active = True
        pet_center_x = self.frameGeometry().center().x()
        if global_pos.x() < pet_center_x:
            self.set_still_frame("hiss-front-left")
            self.pending_jump_direction = 1
        else:
            self.set_still_frame("hiss-front-right")
            self.pending_jump_direction = -1
        self.annoyed_timer.start(ANNOYED_HOLD_MS)

    def finish_annoyed_sequence(self) -> None:
        direction = self.pending_jump_direction
        self.pending_jump_direction = None
        self.interaction_locked = False
        if direction is not None:
            self.start_escape(direction)

    def start_escape(self, direction: int) -> None:
        slug = "running-left" if direction < 0 else "running"
        animation = self.animation_for_slug(slug)
        if animation is None:
            self.annoyed_escape_active = False
            self.schedule_random_behavior()
            self.play_random_from(["attack", "get-hurts", "cry"])
            return

        self.set_animation_by_directory(animation["directory"])
        self.walk_direction = direction
        self.walk_steps_remaining = random.randint(*ANNOYED_ESCAPE_STEPS)
        self.walk_timer.start()

    def react_to_pet_hold(self) -> None:
        self.stop_random_behavior()
        self.play_random_from(
            [
                "happy",
                "tickle",
                "idle",
                "stay-box",
            ],
        )
        self.schedule_random_behavior()

    def react_to_cursor_proximity(self, global_pos: QPoint) -> None:
        if self.interaction_locked:
            return
        if self.walk_timer.isActive() or self.jump_timer.isActive():
            return

        pet_center = self.frameGeometry().center()
        distance = (global_pos - pet_center).manhattanLength()
        if distance > LOOK_RADIUS_PX:
            return

        if global_pos.x() < pet_center.x():
            self.play_random_from(["supprised", "idle", "happy"])
        else:
            self.play_random_from(["supprised", "idle", "happy"])

        if distance <= FOLLOW_RADIUS_PX:
            self.follow_cursor(global_pos)

    def follow_cursor(self, global_pos: QPoint) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        pet_center_x = self.frameGeometry().center().x()
        direction = -1 if global_pos.x() < pet_center_x else 1
        next_x = self.x() + (FOLLOW_STEP_PX * direction)
        next_x = max(available.left(), min(next_x, available.right() - self.width()))
        self.move(next_x, self.y())

    def start_walk(self, slug: str, direction: int) -> None:
        animation = self.animation_for_slug(slug)
        if animation is None:
            return

        self.stop_jump()
        self.set_animation_by_directory(animation["directory"])
        self.walk_direction = direction
        self.walk_steps_remaining = random.randint(*WALK_STEP_RANGE)
        self.walk_timer.start()

    def stop_walk(self) -> None:
        self.walk_timer.stop()
        self.walk_direction = 0
        self.walk_steps_remaining = 0

    def start_jump(self, direction: int) -> None:
        self.stop_walk()
        self.stop_jump()

        slug = "jump-right" if direction < 0 else "jump-left"
        animation = self.animation_for_slug(slug)
        if animation is None:
            return

        self.set_animation_by_directory(animation["directory"])
        self.jump_direction = direction
        self.jump_steps_remaining = JUMP_STEP_COUNT
        self.jump_timer.start()

    def jump_toward(self, global_pos: QPoint) -> None:
        pet_center_x = self.frameGeometry().center().x()
        direction = -1 if global_pos.x() < pet_center_x else 1
        self.start_jump(direction)

    def stop_jump(self) -> None:
        self.jump_timer.stop()
        self.jump_direction = 0
        self.jump_steps_remaining = 0

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
            if self.annoyed_escape_active:
                self.annoyed_escape_active = False
                self.schedule_random_behavior()
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
        if self.has_slug("running-left") and self.has_slug("running"):
            target_slug = "running-left" if left_facing else "running"
        else:
            target_slug = "running"
        if self.current_animation_slug != target_slug:
            animation = self.animation_for_slug(target_slug)
            if animation is not None:
                self.set_animation_by_directory(animation["directory"])

    def advance_jump(self) -> None:
        if self.jump_steps_remaining <= 0:
            self.stop_jump()
            self.random_idle()
            return

        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        next_x = self.x() + (JUMP_STEP_PX * self.jump_direction)
        next_y = self.y()

        if next_x < available.left():
            next_x = available.left()
        elif next_x + self.width() > available.right():
            next_x = available.right() - self.width()

        self.move(next_x, next_y)
        self.jump_steps_remaining -= 1

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
            if self.interaction_locked:
                event.accept()
                return
            self.press_global_pos = event.globalPosition().toPoint()
            self.drag_start_global = event.globalPosition().toPoint()
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.was_dragging = False
            self.pet_timer.start(PET_HOLD_MS)
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self.react_to_cursor_proximity(event.globalPosition().toPoint())
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self.interaction_locked:
                event.accept()
                return
            moved_distance = (event.globalPosition().toPoint() - self.press_global_pos).manhattanLength()
            if moved_distance > CLICK_DRAG_THRESHOLD and self.pet_timer.isActive():
                self.pet_timer.stop()
            if moved_distance > CLICK_DRAG_THRESHOLD:
                self.was_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self.interaction_locked:
                event.accept()
                return
            if self.pet_timer.isActive():
                self.pet_timer.stop()
            release_pos = event.globalPosition().toPoint()
            moved_distance = (release_pos - self.drag_start_global).manhattanLength()
            if moved_distance <= CLICK_DRAG_THRESHOLD:
                self.react_to_click(release_pos)
            elif self.was_dragging:
                self.react_to_drag_release()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self.interaction_locked:
                event.accept()
                return
            self.stop_random_behavior()
            self.jump_toward(event.globalPosition().toPoint())
            self.schedule_random_behavior()
            event.accept()

    def toggle_random_behavior(self, enabled: bool) -> None:
        if enabled:
            self.start_random_behavior()
            return
        self.stop_random_behavior()

    def react_to_drag_release(self) -> None:
        self.stop_random_behavior()
        self.play_random_from(
            ["idle", "happy", "chilling"],
        )
        self.schedule_random_behavior()


def main() -> int:
    app = QApplication(sys.argv)
    window = PetWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
