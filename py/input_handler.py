# py/input_handler.py
"""长按检测和输入事件处理。"""
from __future__ import annotations
import math
import pygame
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ty_sim import TySim


_LONG_PRESS_DELAY_MS = 200
_LONG_PRESS_DEAD_ZONE = 10


class InputHandler:
    def __init__(self, sim: TySim) -> None:
        self.sim = sim
        self._down = False
        self._down_time = 0
        self._down_pos = (0, 0)
        self._triggered = False

    def handle_event(self, e: pygame.event.Event) -> None:
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self._down = True
            self._down_time = pygame.time.get_ticks()
            self._down_pos = e.pos
            self._triggered = False
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._down = False

    def update(self, ct: int) -> None:
        if self.sim.dialog_mgr.any_active():
            return
        if self._down and not self._triggered and ct - self._down_time >= _LONG_PRESS_DELAY_MS:
            mx, my = pygame.mouse.get_pos()
            if math.hypot(mx - self._down_pos[0], my - self._down_pos[1]) < _LONG_PRESS_DEAD_ZONE:
                self.sim.on_long_press(mx, my)
            self._triggered = True
