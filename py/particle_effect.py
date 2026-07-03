"""粒子特效：RI（快速增强）。"""
from __future__ import annotations

import os
import logging
from typing import List, Optional, Tuple

import pygame
from PIL import Image as PILImage

from .constants import SUCAI_DIR, ICON_SET_SMCY

logger = logging.getLogger(__name__)

_PARTICLE_DIR = os.path.join(SUCAI_DIR, ICON_SET_SMCY, 'particle')

# ── 缓存 ──
_eri_frames: Optional[List[pygame.Surface]] = None
_eri_sound: Optional[pygame.mixer.Sound] = None


def preload_particles() -> None:
    _load_eri_gif()


def _load_eri_gif() -> List[pygame.Surface]:
    global _eri_frames
    if _eri_frames is not None:
        return _eri_frames
    _eri_frames = []
    path = os.path.join(_PARTICLE_DIR, 'ERI.gif')
    if not os.path.exists(path):
        logger.warning(f"粒子特效: {path} 不存在")
        return _eri_frames
    gif = PILImage.open(path)
    for i in range(gif.n_frames):
        gif.seek(i)
        frame = gif.convert('RGBA')
        data = frame.tobytes()
        surf = pygame.image.fromstring(data, frame.size, 'RGBA')
        _eri_frames.append(surf)
    gif.close()
    logger.info(f"粒子特效: 加载 ERI.gif ({len(_eri_frames)} 帧)")
    return _eri_frames


def play_eri_sound(volume: float = 0.6) -> None:
    global _eri_sound
    if _eri_sound is None:
        path = os.path.join('./sound/', 'ERI.ogg')
        if os.path.exists(path):
            try:
                _eri_sound = pygame.mixer.Sound(path)
            except Exception as e:
                logger.debug(f"加载 ERI.ogg 失败: {e}")
    if _eri_sound:
        _eri_sound.set_volume(volume)
        _eri_sound.play()


class RIEffect:
    """快速增强（RI）粒子特效，跟随台风移动。"""

    def __init__(self, typhoon, start_time: float,
                 latlon_to_screen_func, icon_factor: float = 1.0) -> None:
        self.typhoon = typhoon
        self.start_time = start_time
        self.latlon_to_screen = latlon_to_screen_func
        self.icon_factor = icon_factor
        self.frames = _load_eri_gif()
        self._frame_count = len(self.frames)

    def update(self, current_time: float) -> bool:
        elapsed = (current_time - self.start_time) / 1000.0
        idx = int(elapsed * 30)
        return idx < self._frame_count and self._frame_count > 0

    def draw(self, surface: pygame.Surface, current_time: float) -> None:
        if self._frame_count == 0:
            return
        pos = self.typhoon.cpos()
        if not pos:
            return
        elapsed = (current_time - self.start_time) / 1000.0
        idx = int(elapsed * 90) % self._frame_count
        if 0 <= idx < self._frame_count:
            x, y = self.latlon_to_screen(pos['la'], pos['lo'])
            frame = self.frames[idx]
            size = max(40, int(100 * self.icon_factor))
            sw = max(1, int(frame.get_width() * size / 640))
            sh = max(1, int(frame.get_height() * size / 640))
            scaled = pygame.transform.smoothscale(frame, (sw, sh))
            r = scaled.get_rect(center=(x, y))
            surface.blit(scaled, r)
