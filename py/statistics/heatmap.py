# py/statistics/path_heatmap.py
"""台风 ACE 热力图对话框 — 径向累积 + ace-heat.png 色彩映射。"""
from __future__ import annotations
import math
import os
import pygame
from PIL import Image as PILImage
from typing import Optional

from ..constants import f_s, f_m, rt, TXT, DIALOG_TITLE_BAR_HEIGHT, SUCAI_DIR, SETTINGS_TEXT_DIM
from ..dialog_base import DraggableDialog


# ── ace-heat.png 色表加载 ──
_heat_img = None
_HEAT_H = 0


def _load_heat():
    global _heat_img, _HEAT_H
    if _heat_img is not None:
        return
    path = os.path.join(SUCAI_DIR, 'SMCY', 'resource', 'ace-heat.png')
    if os.path.exists(path):
        img = PILImage.open(path)
        _heat_img = img.convert('RGBA')
        _HEAT_H = _heat_img.height - 1


def _ace_heat_color(value: float) -> tuple:
    """从 ace-heat.png 采样颜色，value ∈ [0, 8]."""
    _load_heat()
    if _heat_img is None or _HEAT_H <= 0:
        if value <= 0:
            return (0, 0, 0, 0)
        if value >= 8:
            return (0, 0, 0, 255)
        t = value / 8.0
        return (int(t * 255), int((1 - t) * 255), 0, 255)
    v = max(0.0, min(value, 8.0))
    y = int((1.0 - v / 8.0) * _HEAT_H)
    pixel = _heat_img.getpixel((0, y))
    return pixel[:4]


class PathHeatmapDialog(DraggableDialog):
    RANGE_AUTO = 0
    RANGE_SETTINGS = 1
    RANGE_CUSTOM = 2

    def __init__(self, sim):
        super().__init__(sim)
        self.title_bar_height = DIALOG_TITLE_BAR_HEIGHT
        self._year: int = 0
        self._cached_surf: Optional[pygame.Surface] = None
        self._close_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._range_mode = self.RANGE_AUTO
        self._custom_mlon = 0.0
        self._custom_Mlon = 360.0
        self._custom_mlat = -90.0
        self._custom_Mlat = 90.0
        self._custom_active = False
        self._custom_fields = []
        self._custom_field_active = -1

    def activate(self):
        super().activate()
        year = self.sim.current_ace_year
        self._year = year
        w, h = min(1800, self.sim.screen_width - 40), min(1100, self.sim.screen_height - 80)
        self.bg_rect = pygame.Rect(
            (self.sim.screen_width - w) // 2,
            (self.sim.screen_height - h) // 2, w, h)
        self._cached_surf = None

    def _render(self):
        if self._cached_surf is not None:
            return

        # ── Phase 1: 收集 ACE 报点 (lon, lat, pace) ──
        engine = self.sim.ace_engine
        ace_pts = []          # [(lon, lat, pace), ...]
        all_lons, all_lats = [], []
        for ty in self.sim.tys:
            for p in ty.pts:
                if p.get('ace_year', 0) != self._year:
                    continue
                if not engine.point_in_limit(p['la'], p['lo']):
                    continue
                pace = p.get('pace', 0.0)
                if pace <= 0:
                    continue
                ace_pts.append((p['lo'], p['la'], pace))
                all_lons.append(p['lo'])
                all_lats.append(p['la'])

        if not all_lons:
            w, h = self.bg_rect.width, self.bg_rect.height
            self._cached_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            return

        # ── 地理边界 ──
        if self._range_mode == self.RANGE_AUTO:
            margin = 5.0
            mlon, Mlon = min(all_lons) - margin, max(all_lons) + margin
            mlat, Mlat = min(all_lats) - margin, max(all_lats) + margin
        elif self._range_mode == self.RANGE_SETTINGS:
            mlon, Mlon = self.sim.mlo, self.sim.Mlo
            mlat, Mlat = self.sim.mla, self.sim.Mla
        else:
            mlon, Mlon = self._custom_mlon, self._custom_Mlon
            mlat, Mlat = self._custom_mlat, self._custom_Mlat
        if Mlon - mlon < 2:
            Mlon = mlon + 2
        if Mlat - mlat < 2:
            Mlat = mlat + 2

        # ── Phase 2: 按地理宽高比动态调整高度 ──
        bx, by = 80, 50
        bw = self.bg_rect.width - 160
        geo_ratio = (Mlon - mlon) / max(0.1, Mlat - mlat)
        bh = int(bw / geo_ratio)
        bh = max(100, min(2000, bh))

        new_h = bh + by + 80
        if new_h != self.bg_rect.height:
            self.bg_rect.height = new_h
            self.bg_rect.centery = self.sim.screen_height // 2

        w = self.bg_rect.width
        surf = pygame.Surface((w, new_h), pygame.SRCALPHA)

        # ── 底图 ──
        try:
            orig = self.sim.map_mgr.map_view.original_img
            iw, ih = orig.get_size()
            ix1 = int((mlon - 0) / 360 * iw)
            ix2 = int((Mlon - 0) / 360 * iw)
            iy1 = int((90 - Mlat) / 180 * ih)
            iy2 = int((90 - mlat) / 180 * ih)
            ix1, ix2 = max(0, min(ix1, iw)), max(0, min(ix2, iw))
            iy1, iy2 = max(0, min(iy1, ih)), max(0, min(iy2, ih))
            if ix2 > ix1 and iy2 > iy1:
                sub = orig.subsurface(pygame.Rect(ix1, iy1, ix2 - ix1, iy2 - iy1))
                scaled = pygame.transform.smoothscale(sub, (bw, bh))
                scaled.set_alpha(200)
                surf.blit(scaled, (bx, by))
        except Exception:
            pass

        # ── Phase 3: 径向累积 ACE 热力 ──
        radius_px = 2.0 / (Mlat - mlat) * bh   # 2° 纬距 → 像素
        heat = [0.0] * (bw * bh)

        for lon, lat, pace in ace_pts:
            px = (lon - mlon) / (Mlon - mlon) * bw
            py = (Mlat - lat) / (Mlat - mlat) * bh
            r_int = int(radius_px) + 1
            x0 = max(0, int(px - r_int))
            y0 = max(0, int(py - r_int))
            x1 = min(bw, int(px + r_int) + 1)
            y1 = min(bh, int(py + r_int) + 1)
            for y in range(y0, y1):
                dy = y - py
                row_off = y * bw
                for x in range(x0, x1):
                    dx = x - px
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist <= radius_px:
                        heat[row_off + x] += pace * (1.0 - dist / radius_px)

        # ── Phase 4: 色彩映射到 Surface ──
        heat_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
        px_array = pygame.PixelArray(heat_surf)
        for y in range(bh):
            row = y * bw
            for x in range(bw):
                v = heat[row + x]
                if v > 0:
                    c = pygame.Color(*_ace_heat_color(v))
                    px_array[x, y] = heat_surf.map_rgb(c)
        px_array.close()
        surf.blit(heat_surf, (bx, by))

        # ── 洋区矩形边框 ──
        rect_color = (100, 180, 255)
        pygame.draw.rect(surf, rect_color, (bx, by, bw, bh), 2)

        self._cached_surf = surf

    def _draw_legend(self, surface):
        """在左侧空白区域绘制颜色渐变图例"""
        bx, by = self.bg_rect.x, self.bg_rect.y
        # 图例放在左侧边距区
        legend_x = bx + 20
        legend_y = by + 60
        legend_w = 24
        legend_h = 200

        # 渐变条
        for py in range(legend_h):
            t = 1.0 - py / legend_h
            value = t * 8.0
            rgba = _ace_heat_color(value)
            color = pygame.Color(*rgba)
            pygame.draw.line(surface, color,
                           (legend_x, legend_y + py),
                           (legend_x + legend_w, legend_y + py))

        pygame.draw.rect(surface, TXT,
                        (legend_x, legend_y, legend_w, legend_h), 1)
        # 标签
        for val_pct in [0, 0.25, 0.5, 0.75, 1.0]:
            y = legend_y + int((1.0 - val_pct) * legend_h)
            value = val_pct * 8.0
            lbl = rt(f_s, f"{value:.0f}", TXT)
            surface.blit(lbl, (legend_x + legend_w + 6, y - lbl.get_height() // 2))
        # 标题
        title_lbl = rt(f_s, "ACE", TXT)
        surface.blit(title_lbl, (legend_x, legend_y - 20))

    def draw(self, surface: pygame.Surface):
        if not self.active:
            return
        self.draw_background(surface, self.bg_rect)
        self._render()
        if self._cached_surf:
            surface.blit(self._cached_surf, self.bg_rect.topleft)

        self._draw_legend(surface)

        bx, by = self.bg_rect.x, self.bg_rect.y
        bw = self.bg_rect.width
        title = rt(f_m, f"路径密度热力图 - {self._year}", TXT)
        surface.blit(title, (bx + 12, by + 8))

        # 右上角范围模式切换（记录按钮位置供 handle_event 检测）
        self._mode_btns = []
        mode_names = ["自动", "设置", "自定义"]
        for i, name in enumerate(mode_names):
            r = pygame.Rect(bx + bw - 280 + i * 85, by + 6, 75, 22)
            self._mode_btns.append(r)
            is_on = self._range_mode == i
            if not self.dark_mode:
                bg = (100, 150, 200) if is_on else (180, 190, 210)
                tc = (255, 255, 255)
            elif is_on:
                bg = (70, 130, 180)
                tc = (20, 25, 35)
            else:
                bg = (50, 55, 70)
                tc = SETTINGS_TEXT_DIM
            pygame.draw.rect(surface, bg, r, border_radius=6)
            ts = rt(f_s, name, tc)
            surface.blit(ts, (r.x + (r.w - ts.get_width()) // 2, r.y + (r.h - ts.get_height()) // 2))

        # 关闭按钮
        cb = pygame.Rect(bx + bw - 90, by + 8, 55, 25)
        self._close_btn_rect = cb
        self.draw_button(surface, cb, rt(f_s, "关闭", (255, 255, 255)))

        # 自定义范围输入
        if self._range_mode == self.RANGE_CUSTOM:
            cy = by + 34
            labels = ["西", "东", "南", "北"]
            vals = [f"{self._custom_mlon:.0f}", f"{self._custom_Mlon:.0f}",
                    f"{self._custom_mlat:.0f}", f"{self._custom_Mlat:.0f}"]
            for i, (lbl, val) in enumerate(zip(labels, vals)):
                lx = bx + bw - 280 + i * 68
                surface.blit(rt(f_s, lbl, TXT), (lx, cy))
                fr = pygame.Rect(lx + 16, cy, 46, 22)
                pygame.draw.rect(surface, (255, 255, 255), fr, 0, 3)
                pygame.draw.rect(surface, (100, 150, 200), fr, 1, 3)
                vs = rt(f_s, val, TXT)
                surface.blit(vs, (fr.x + 3, fr.y + 3))

    def handle_event(self, e: pygame.event.Event) -> bool:
        if not self.active:
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self._close_btn_rect.collidepoint(e.pos):
                self.deactivate()
                return True
            for i, r in enumerate(getattr(self, '_mode_btns', [])):
                if r.collidepoint(e.pos):
                    self._range_mode = i
                    self._cached_surf = None
                    return True
        if self.handle_drag_event(e):
            return True
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.deactivate()
            return True
        return False

    def deactivate(self):
        super().deactivate()
        self._cached_surf = None
