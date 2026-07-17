# py/typhoon_render.py
"""台风渲染 Mixin：坐标变换、旋转、屏幕点。"""
from __future__ import annotations

import pygame
from typing import Tuple, TYPE_CHECKING
from .spline import build_spline, compute_arc_lengths

if TYPE_CHECKING:
    from .ty_sim import TySim


class TyphoonRenderMixin:
    """渲染方法：update_screen_points, 旋转, 坐标。"""

    def update_screen_points(self, latlon_to_screen_func, view_rect=None):
        v = self.v
        v.screen_points.clear()
        v.smooth_screen_points.clear()
        v._smooth_arc_lengths.clear()
        if not self.pts:
            v.bbox = None
            return
        xs, ys = [], []
        for pt in self.pts:
            x, y = latlon_to_screen_func(pt['la'], pt['lo'])
            v.screen_points.append((x, y))
            xs.append(x)
            ys.append(y)
        v.bbox = pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if view_rect and not v.bbox.colliderect(view_rect):
            return
        if self.sim and self.sim.cfg.smooth_path:
            segs = self.sim.cfg.smooth_path_segments
            geo_pts = [(p['lo'], p['la']) for p in self.pts]
            smooth_geo = build_spline(geo_pts, segs)
            f = latlon_to_screen_func
            smooth_sc = [f(lat, lon) for lon, lat in smooth_geo]
            v.smooth_screen_points = smooth_sc
            v._smooth_arc_lengths = compute_arc_lengths(smooth_sc)

    def _get_rotated(self, key_prefix: str, img: pygame.Surface, angle: float,
                     mirror: bool) -> pygame.Surface:
        key = (key_prefix, int(angle) % 360, mirror)
        cache = self.v._img_cache
        if key in cache:
            return cache[key]
        rotated = pygame.transform.rotate(img, angle)
        if mirror:
            rotated = pygame.transform.flip(rotated, True, False)
        cache[key] = rotated
        return rotated

    def get_rotated_ring(self, cat: str, base_ring: pygame.Surface, angle: float,
                          mirror: bool) -> pygame.Surface:
        return self._get_rotated(cat, base_ring, angle, mirror)

    def get_rotated_level3_ring(self, cat: str, base_ring: pygame.Surface, angle: float,
                                 mirror: bool) -> pygame.Surface:
        return self._get_rotated(cat, base_ring, angle, mirror)

    def update_rotation(self, dt: float) -> None:
        mf = self.sim.main_rotation_speed if self.sim else 1.0
        lf = self.sim.level3_rotation_speed if self.sim else 1.5
        v = self.v
        v.sa = (v.sa + 180 * dt * mf) % 360
        v.sa3 = (v.sa3 + 180 * dt * lf) % 360
        v.sa4 = (v.sa4 + 180 * dt * lf) % 360
        v.sa5 = (v.sa5 + 180 * dt * lf) % 360
