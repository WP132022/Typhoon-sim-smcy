from __future__ import annotations

import os
import math
import logging
from typing import Optional

import pygame

from .constants import DEFAULT_MAP, LAND_MASK

logger = logging.getLogger(__name__)


class MapView:
    def __init__(self, img_path, lon_min, lon_max, lat_min, lat_max, screen_width, screen_height):
        self.original_img = pygame.image.load(img_path).convert()
        self.img_w, self.img_h = self.original_img.get_size()
        self.lon_min, self.lon_max = lon_min, lon_max
        self.lat_min, self.lat_max = lat_min, lat_max
        self.width_deg = lon_max - lon_min
        self.height_deg = lat_max - lat_min
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.view_x = self.view_y = 0.0
        self.scale = 1.0
        self.min_scale = min(screen_width / self.img_w, screen_height / self.img_h)
        self._cached_scale = -1.0
        self._cached_sw = -1
        self._cached_offset = (0, 0)

    @property
    def _max_view_y(self):
        return max(0.0, self.img_h - self.screen_height / self.scale)

    def _clamp_view_y(self):
        self.view_y = max(0.0, min(self.view_y, self._max_view_y))

    def _src_y(self, view_h):
        return max(0.0, min(self.view_y, self.img_h - view_h))

    def geo_to_screen(self, lon, lat):
        px = (lon - self.lon_min) / self.width_deg * self.img_w
        py = (self.lat_max - lat) / self.height_deg * self.img_h
        cx = self.view_x + self.screen_width / (2.0 * self.scale)
        dx = px - cx
        if dx > self.img_w / 2.0: dx -= self.img_w
        elif dx < -self.img_w / 2.0: dx += self.img_w
        ox, oy = self._draw_offset()
        return int(dx * self.scale + self.screen_width / 2.0) + ox, \
               int((py - self.view_y) * self.scale) + oy

    def screen_to_geo(self, sx, sy):
        ox, oy = self._draw_offset()
        sx, sy = sx - ox, sy - oy
        cx = self.view_x + self.screen_width / (2.0 * self.scale)
        px = cx + (sx - self.screen_width / 2.0) / self.scale
        py = self.view_y + sy / self.scale
        lon = self.lon_min + (px / self.img_w) * self.width_deg
        lon = ((lon - self.lon_min) % self.width_deg) + self.lon_min
        lat = max(self.lat_min, min(self.lat_max,
                                    self.lat_max - (py / self.img_h) * self.height_deg))
        return lon, lat

    def move_view(self, dx, dy):
        old_vx, old_vy = self.view_x, self.view_y
        self.view_x -= dx / self.scale
        self.view_y -= dy / self.scale
        self.view_x %= self.img_w
        self._clamp_view_y()
        return (self.view_x - old_vx) * self.scale, (self.view_y - old_vy) * self.scale

    def zoom_at(self, factor, mx, my):
        ox, oy = self._draw_offset()
        mx, my = mx - ox, my - oy
        old = self.scale
        self.scale = max(self.min_scale, min(self.scale * factor, 8.0))
        self.view_x = (self.view_x + mx / old) - mx / self.scale
        self.view_y = (self.view_y + my / old) - my / self.scale
        self.view_x %= self.img_w
        self._clamp_view_y()

    def set_view_region(self, lon_min, lon_max, lat_min, lat_max):
        if lon_max < lon_min: lon_max += 360
        clon = (lon_min + lon_max) / 2.0
        clat = (lat_min + lat_max) / 2.0
        lon_span = lon_max - lon_min
        lat_span = lat_max - lat_min
        self.scale = max(self.min_scale, min(
            self.screen_width / (lon_span / self.width_deg * self.img_w),
            self.screen_height / (lat_span / self.height_deg * self.img_h), 8.0))
        self.view_x = ((clon - self.lon_min) / self.width_deg * self.img_w
                       - self.screen_width / (2.0 * self.scale)) % self.img_w
        self.view_y = (self.lat_max - clat) / self.height_deg * self.img_h \
                      - self.screen_height / (2.0 * self.scale)
        self._clamp_view_y()

    def _draw_offset(self):
        if self._cached_scale != self.scale or self._cached_sw != self.screen_width:
            vw = min(self.screen_width / self.scale, self.img_w)
            vh = min(self.screen_height / self.scale, self.img_h)
            self._cached_offset = (
                int((self.screen_width - vw * self.scale) / 2),
                int((self.screen_height - vh * self.scale) / 2),
            )
            self._cached_scale = self.scale
            self._cached_sw = self.screen_width
        return self._cached_offset

    def draw(self, screen, dest_rect=None):
        if dest_rect is None:
            dest_rect = pygame.Rect(0, 0, self.screen_width, self.screen_height)
        screen.fill((120, 120, 120), dest_rect)

        vw = min(dest_rect.width / self.scale, self.img_w)
        vh = min(dest_rect.height / self.scale, self.img_h)
        sx, sy = self.view_x % self.img_w, self._src_y(vh)
        ox, oy = self._draw_offset()
        rw = self.img_w - sx

        x_off = 0
        for seg_x, seg_w in ([(sx, min(rw, vw))] if rw >= vw
                             else [(sx, rw), (0, vw - rw)]):
            rect = pygame.Rect(int(seg_x), int(sy),
                                int(math.ceil(seg_w)), int(math.ceil(vh)))
            try:
                part = self.original_img.subsurface(rect)
                scaled = pygame.transform.scale(part,
                    (max(1, int(seg_w * self.scale)), max(1, int(vh * self.scale))))
                screen.blit(scaled, (dest_rect.left + ox + x_off, dest_rect.top + oy))
                x_off += scaled.get_width()
            except ValueError:
                pass


class MapManager:
    def __init__(self, sim):
        self.sim = sim
        self.map_view: Optional[MapView] = None
        self.land_img: Optional[pygame.Surface] = None
        self._land_alpha_bytes: Optional[bytes] = None
        self._land_w: int = 0
        self.ocean_overlay: Optional[pygame.Surface] = None
        self.cmp: Optional[str] = None
        self._land_orig: Optional[pygame.Surface] = None
        self._cached_map_render: Optional[pygame.Surface] = None
        self._cached_render_hash = None

    def _view_hash(self):
        v = self.map_view
        if v is None:
            return None
        return (int(v.view_x * 100), int(v.view_y * 100),
                v.scale, self.sim.screen_width, self.sim.map_height)

    def _init_map_view(self):
        path = self.cmp if self.cmp and os.path.exists(self.cmp) else DEFAULT_MAP
        self.map_view = MapView(path, 0.0, 360.0, -90.0, 90.0,
                                self.sim.screen_width, self.sim.map_height)
        self.map_view.set_view_region(self.sim.mlo, self.sim.Mlo, self.sim.mla, self.sim.Mla)

    def _load_land_orig(self):
        if self._land_orig is None and os.path.exists(LAND_MASK):
            try:
                self._land_orig = pygame.image.load(LAND_MASK).convert_alpha()
            except Exception as e:
                logger.error(f"加载陆地掩码失败: {e}")
        return self._land_orig

    def _rebuild_land_and_overlay(self):
        land = self._load_land_orig()
        if land is None or self.map_view is None:
            self.land_img = None
        else:
            view = self.map_view
            vw = min(self.sim.screen_width / view.scale, view.img_w)
            vh = min(self.sim.map_height / view.scale, view.img_h)
            sx, sy = view.view_x % view.img_w, max(0.0, min(view.view_y, view.img_h - vh))
            ox, oy = view._draw_offset()
            lw, lh = land.get_size()
            scx, scy = lw / view.img_w, lh / view.img_h

            self.land_img = pygame.Surface(
                (self.sim.screen_width, self.sim.map_height), pygame.SRCALPHA)

            for lsx, lw_seg in ([(sx, min(view.img_w - sx, vw))]
                                if view.img_w - sx >= vw
                                else [(sx, view.img_w - sx), (0, vw - (view.img_w - sx))]):
                if lw_seg <= 0: continue
                rect = pygame.Rect(int(lsx * scx), int(sy * scy),
                                   int(math.ceil(lw_seg * scx)), int(math.ceil(vh * scy)))
                rect = rect.clip(land.get_rect())
                if rect.width <= 0 or rect.height <= 0: continue
                scaled = pygame.transform.scale(
                    land.subsurface(rect),
                    (max(1, int(lw_seg * view.scale)), max(1, int(vh * view.scale))))
                dst_x = 0 if lsx == sx else int((view.img_w - sx) * view.scale)
                self.land_img.blit(scaled, (ox + dst_x, oy))

        self.ocean_overlay = None

        if self.land_img is not None:
            raw = pygame.image.tobytes(self.land_img, 'RGBA')
            self._land_alpha_bytes = raw[3::4]
            self._land_w = self.land_img.get_width()
        else:
            self._land_alpha_bytes = None
            self._land_w = 0

    def update_land_mask(self):
        if self.map_view is None:
            return
        vh = self._view_hash()
        if vh == self._cached_render_hash:
            return
        self._rebuild_land_and_overlay()
        w, h = self.sim.screen_width, self.sim.map_height
        self._cached_map_render = pygame.Surface((w, h))
        self.map_view.draw(self._cached_map_render, pygame.Rect(0, 0, w, h))
        self._cached_render_hash = vh

    def is_land_at_screen(self, sx, sy):
        ab = self._land_alpha_bytes
        if ab is None:
            return False
        w = self._land_w
        if 0 <= sx < w and 0 <= sy < len(ab) // w:
            return ab[sy * w + sx] > 0
        return False

    def update_view(self):
        if self.map_view is None:
            self._init_map_view()
        else:
            self.map_view.set_view_region(self.sim.mlo, self.sim.Mlo, self.sim.mla, self.sim.Mla)
        self.update_land_mask()

    update_map_image = update_view

    def draw_map(self, surface, dest_rect=None):
        if self.map_view is None:
            self._init_map_view()
        if self._cached_map_render is None:
            self.update_land_mask()
        if dest_rect is None:
            dest_rect = pygame.Rect(0, 0, self.sim.screen_width, self.sim.map_height)
        surface.blit(self._cached_map_render, dest_rect)

    def get_draw_rect(self):
        return pygame.Rect(0, 0, self.sim.screen_width, self.sim.map_height)

    def load_custom_map(self, path):
        if os.path.exists(path):
            self.cmp = path
            self._init_map_view()
            self.sim._config_needs_save = True

    def reset_map(self):
        self.cmp = None
        self._init_map_view()
        self.sim._config_needs_save = True
