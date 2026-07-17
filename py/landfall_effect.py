# py/landfall_effect.py
"""登陆效果类（简单图标 PNG + SMCY 视频）。"""
from __future__ import annotations

import pygame
from typing import Callable, List, Tuple

from .constants.fonts import _load_font, SmartFont, FONT_FILE

_label_font = SmartFont(_load_font(FONT_FILE, 20, 20), _load_font(FONT_FILE, 20, 20))
_OUTLINE = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

_LABEL_DURATION = 2.0
_LABEL_FADE = 0.3

_label_cache: dict = {}


def _get_label_surf(label: str, color) -> pygame.Surface:
    key = (label, color)
    surf = _label_cache.get(key)
    if surf is None:
        fg = _label_font.render(label, True, color)
        bk = _label_font.render(label, True, (0, 0, 0))
        surf = pygame.Surface((fg.get_width() + 2, fg.get_height() + 2), pygame.SRCALPHA)
        for dx, dy in _OUTLINE:
            surf.blit(bk, (dx + 1, dy + 1))
        surf.blit(fg, (1, 1))
        if len(_label_cache) > 64:
            _label_cache.pop(next(iter(_label_cache)))
        _label_cache[key] = surf
    return surf


def _draw_strength_label(surface, label: str, color, x: int, y_top: int,
                         elapsed: float) -> None:
    """登陆图标下方的强度标注：显示 2 秒，淡入淡出。"""
    if not label or elapsed < 0 or elapsed >= _LABEL_DURATION:
        return
    a = min(1.0, elapsed / _LABEL_FADE, (_LABEL_DURATION - elapsed) / _LABEL_FADE)
    alpha = int(255 * max(0.0, a))
    if alpha <= 0:
        return
    surf = _get_label_surf(label, color)
    if alpha < 255:
        surf = surf.copy()
        surf.set_alpha(alpha)
    r = surf.get_rect(midtop=(x, y_top))
    surface.blit(surf, r)


class LandfallEffect:
    def __init__(self, strength: str, lon: float, lat: float,
                 img1: pygame.Surface, img2: pygame.Surface,
                 start_time: float,
                 latlon_to_screen_func: Callable[[float, float], tuple],
                 label: str = "",
                 label_color: Tuple[int, int, int] = (255, 255, 255)) -> None:
        self.strength = strength
        self.lon = lon
        self.lat = lat
        self.img1 = img1
        self.img2 = img2
        self.start_time = start_time
        self.latlon_to_screen = latlon_to_screen_func
        self.label = label
        self.label_color = label_color
        self._flash_alpha: int = 255
        self._ring_alpha: int = 255

    def update(self, current_time: float) -> bool:
        elapsed = (current_time - self.start_time) / 1000.0
        if elapsed > max(2.0, _LABEL_DURATION):
            return False
        self._flash_alpha = max(0, int(255 * (1.0 - elapsed / 1.0)))
        self._ring_alpha = max(0, int(255 * (1.0 - elapsed / 2.0)))
        return True

    def draw(self, surface: pygame.Surface, current_time: float) -> None:
        x, y = self.latlon_to_screen(self.lat, self.lon)
        if self._flash_alpha > 0 and self.img2:
            flash = self.img2.copy()
            flash.set_alpha(self._flash_alpha)
            r = flash.get_rect(center=(x, y))
            surface.blit(flash, r)
        if self._ring_alpha > 0 and self.img1:
            ring = self.img1.copy()
            ring.set_alpha(self._ring_alpha)
            elapsed = (current_time - self.start_time) / 1000.0
            angle = elapsed * 360 % 360
            rotated = pygame.transform.rotate(ring, angle)
            r = rotated.get_rect(center=(x, y))
            surface.blit(rotated, r)
        elapsed = (current_time - self.start_time) / 1000.0
        y_top = y + (self.img1.get_height() // 2 + 4 if self.img1 else 20)
        _draw_strength_label(surface, self.label, self.label_color, x, y_top, elapsed)


class LandfallEffectSMCY:
    """SMCY 视频登陆特效：播放 60 帧 1 秒动画。"""

    def __init__(self, strength: str, lon: float, lat: float,
                 frames: List[pygame.Surface],
                 start_time: float,
                 latlon_to_screen_func: Callable[[float, float], tuple],
                 label: str = "",
                 label_color: Tuple[int, int, int] = (255, 255, 255)) -> None:
        self.strength = strength
        self.lon = lon
        self.lat = lat
        self.frames = frames
        self.start_time = start_time
        self.latlon_to_screen = latlon_to_screen_func
        self.label = label
        self.label_color = label_color
        self._frame_count = len(frames)
        self._half_h = frames[0].get_height() // 2 if frames else 20

    def update(self, current_time: float) -> bool:
        elapsed = (current_time - self.start_time) / 1000.0
        return elapsed < max(self._frame_count / 60.0, _LABEL_DURATION)

    def draw(self, surface: pygame.Surface, current_time: float) -> None:
        elapsed = (current_time - self.start_time) / 1000.0
        x, y = self.latlon_to_screen(self.lat, self.lon)
        idx = int(elapsed * 60)
        if 0 <= idx < self._frame_count:
            frame = self.frames[idx]
            r = frame.get_rect(center=(x, y))
            surface.blit(frame, r)
        _draw_strength_label(surface, self.label, self.label_color,
                             x, y + self._half_h + 4, elapsed)
