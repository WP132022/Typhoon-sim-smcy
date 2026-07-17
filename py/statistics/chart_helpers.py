# py/statistics/chart_helpers.py
from __future__ import annotations
import math
import pygame
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional

from ..constants import (
    f_s, rt, TXT,
    HEMISPHERE_NORTH,
    ACE_CHART_DEFAULT_WIDTH, ACE_CHART_DEFAULT_HEIGHT,
    ACE_CHART_PADDING_LEFT, ACE_CHART_PADDING_RIGHT, ACE_CHART_PADDING_TOP,
)

DASH_COLOR = (180, 180, 200, 80)
WINDOW_WIDTH_SCALE = 1.2

# ════════════════════ 绘图辅助 ════════════════════


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2.0 * math.asin(math.sqrt(a))


_dashed_h_cache: Dict[Tuple[int, int], pygame.Surface] = {}


def _get_dashed_h_surface(width: int, color: Tuple, dash: int = 6, gap: int = 4) -> pygame.Surface:
    key = (width, dash, gap, color)
    if key in _dashed_h_cache:
        return _dashed_h_cache[key]
    surf = pygame.Surface((width, 1), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    step = dash + gap
    for i in range(max(1, width // step + 1)):
        sx = i * step
        ex = min(sx + dash, width)
        if sx < width:
            surf.fill(color, (int(sx), 0, int(ex - sx), 1))
    _dashed_h_cache[key] = surf
    if len(_dashed_h_cache) > 64:
        _dashed_h_cache.pop(next(iter(_dashed_h_cache)))
    return surf


def draw_dashed_v(surface: pygame.Surface, x: float, y1: float, y2: float,
                  color: Tuple, dash: int = 6, gap: int = 4):
    total = y2 - y1
    if total <= 0:
        return
    step = dash + gap
    for i in range(max(1, int(total / step))):
        sy = y1 + i * step
        ey = min(sy + dash, y2)
        pygame.draw.line(surface, color, (int(x), int(sy)), (int(x), int(ey)), 1)


def draw_dashed_h(surface: pygame.Surface, x1: float, x2: float, y: float,
                  color: Tuple, dash: int = 6, gap: int = 4):
    width = int(x2 - x1)
    if width <= 0 or y < 0:
        return
    dash_surf = _get_dashed_h_surface(width, color, dash, gap)
    surface.blit(dash_surf, (int(x1), int(y)))


_month_lines_cache: Dict[Tuple, Tuple[pygame.Surface, List[float], List[str]]] = {}


def build_month_lines_surface(
    width: int, height: int,
    start_dt: datetime, total_hours: int, hemisphere: str,
) -> Tuple[pygame.Surface, List[float], List[str]]:
    cache_key = (width, height, start_dt.year, total_hours, hemisphere)
    if cache_key in _month_lines_cache:
        return _month_lines_cache[cache_key]

    xs: List[float] = []
    labels: List[str] = []
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    if width <= 0 or height <= 0:
        _month_lines_cache[cache_key] = (surf, xs, labels)
        return surf, xs, labels

    for m in range(1, 13):
        if hemisphere == HEMISPHERE_NORTH:
            ms = datetime(start_dt.year, m, 1, 0)
        else:
            yr = start_dt.year
            ms = datetime(yr, m, 1, 0) if m >= 7 else datetime(yr + 1, m, 1, 0)
        if ms < start_dt:
            continue
        if ms > (start_dt + timedelta(hours=total_hours)):
            continue
        ho = (ms - start_dt).total_seconds() / 3600
        x_px = (ho / total_hours) * width
        draw_dashed_v(surf, x_px, 0, height, DASH_COLOR)
        xs.append(x_px)
        labels.append(f"{m:02d}/01")

    if len(_month_lines_cache) > 32:
        _month_lines_cache.pop(next(iter(_month_lines_cache)))
    _month_lines_cache[cache_key] = (surf, xs, labels)
    return surf, xs, labels


# ════════════════════ 图表布局 Mixin ════════════════════


def _offset_rect(r: pygame.Rect, dy: int) -> pygame.Rect:
    return pygame.Rect(r.x, r.y + dy, r.w, r.h)


class ChartGridMixin:
    """图表布局、栅格计算、滚动条、月份缓存管理。"""

    padding_left: int
    padding_right: int
    padding_top: int
    window_width: int
    window_height: int
    graph_width: int

    curve_rect: pygame.Rect
    daily_bar_rect: pygame.Rect
    chart2_rect: pygame.Rect
    chart3_rect: pygame.Rect
    bar_rect: pygame.Rect

    curve_height: int
    daily_height: int
    chart2_height: int
    chart3_height: int
    typhoon_height: int
    _typhoon_bar_width: float

    _scroll_y: int
    _content_height: int
    _layout_valid: bool
    _chart_data: object
    _month_lines_surface: Optional[pygame.Surface]
    _month_line_xs: List[float]
    _month_line_labels: List[str]
    _month_line_top: int
    _month_line_bottom: int
    _month_label_y: int
    _month_label_surfs: Optional[List[pygame.Surface]]
    _month_label_surf_xs: Optional[List[float]]

    def _init_grid_attributes(self) -> None:
        max_w = max(800, min(int(ACE_CHART_DEFAULT_WIDTH * WINDOW_WIDTH_SCALE),
                             self.sim.screen_width - 20))
        max_h = max(600, min(ACE_CHART_DEFAULT_HEIGHT,
                             self.sim.screen_height - 80))
        self.window_width = max_w
        self.window_height = max_h
        self._max_window_height = max_h
        self._layout_valid = False

        self.padding_left = ACE_CHART_PADDING_LEFT
        self.padding_right = ACE_CHART_PADDING_RIGHT
        self.padding_top = ACE_CHART_PADDING_TOP
        self.graph_width = self.window_width - self.padding_left - self.padding_right

        self.curve_rect = pygame.Rect(0, 0, 0, 0)
        self.daily_bar_rect = pygame.Rect(0, 0, 0, 0)
        self.chart2_rect = pygame.Rect(0, 0, 0, 0)
        self.chart3_rect = pygame.Rect(0, 0, 0, 0)
        self.bar_rect = pygame.Rect(0, 0, 0, 0)

        self.curve_height = 250
        self.daily_height = 180
        self.chart2_height = 360
        self.chart3_height = 120
        self.typhoon_height = 250
        self._typhoon_bar_width = 30

        self._scroll_y = 0
        self._content_height = 0

        self._month_lines_surface = None
        self._month_line_xs = []
        self._month_line_labels = []
        self._month_line_top = 0
        self._month_line_bottom = 0
        self._month_label_y = 0
        self._month_label_surfs = None
        self._month_label_surf_xs = None

    def _center_in_map(self):
        map_cx = self.sim.screen_width // 2
        map_cy = self.sim.map_height // 2
        self.bg_rect.x = max(0, map_cx - self.window_width // 2)
        self.bg_rect.y = max(0, map_cy - self.window_height // 2)
        if self.bg_rect.right > self.sim.screen_width:
            self.bg_rect.x = self.sim.screen_width - self.window_width
        if self.bg_rect.bottom > self.sim.screen_height:
            self.bg_rect.y = self.sim.screen_height - self.window_height
        self._layout_valid = False

    def _compute_layout(self):
        if self._layout_valid:
            return

        graph_width = self.window_width - self.padding_left - self.padding_right
        chart_data = self._chart_data

        n_ty = max(1, len(chart_data.typhoon_ace_list))
        tbw = min(40, graph_width / n_ty * 0.7)
        self._typhoon_bar_width = tbw

        chart2_h = 480
        chart3_h = max(40, int(2 * tbw))
        curve_h, daily_h, typhoon_h = 250, 180, 250

        top_area = self.padding_top + 40 + 30
        bottom_area = 70
        label_row = 18
        gap = 10

        needed = top_area + curve_h + daily_h + chart2_h + chart3_h + label_row + gap + typhoon_h + bottom_area
        max_h = min(1440, self.sim.screen_height - 100)
        if needed > max_h:
            self.window_height = max_h
            self._content_height = needed
        else:
            self.window_height = needed
            self._content_height = needed
            self._scroll_y = 0

        self.curve_height = curve_h
        self.daily_height = daily_h
        self.chart2_height = chart2_h
        self.chart3_height = chart3_h
        self.typhoon_height = typhoon_h
        self.graph_width = graph_width

        bx = self.bg_rect.x + self.padding_left
        top = self.bg_rect.y + self.padding_top + 32
        self.curve_rect = pygame.Rect(bx, top, graph_width, curve_h)
        self.daily_bar_rect = pygame.Rect(bx, self.curve_rect.bottom, graph_width, daily_h)
        self.chart2_rect = pygame.Rect(bx, self.daily_bar_rect.bottom, graph_width, chart2_h)
        self.chart3_rect = pygame.Rect(bx, self.chart2_rect.bottom, graph_width, chart3_h)
        self._month_label_y = self.chart3_rect.bottom + 7
        bt = self.chart3_rect.bottom + label_row + gap + 5
        self.bar_rect = pygame.Rect(bx, bt, graph_width, typhoon_h)
        self._month_line_top = self.curve_rect.top
        self._month_line_bottom = self.chart3_rect.bottom + 5
        total_h = self.bar_rect.bottom - self.bg_rect.y + 55
        self._content_height = max(self._content_height, total_h)
        max_h = min(1440, self.sim.screen_height - 100)
        self.bg_rect.height = min(max_h, max(self.window_height, total_h))
        self.window_height = self.bg_rect.height
        max_scroll = max(0, self._content_height - self.window_height)
        self._scroll_y = max(0, min(self._scroll_y, max_scroll))

        self._layout_valid = True

    def _build_month_cache(self):
        cd = self._chart_data
        sd, _, th = cd.year_range
        w = self.graph_width
        h = self._month_line_bottom - self._month_line_top
        surf, xs, labels = build_month_lines_surface(w, h, sd, th, self.sim.hemisphere)
        self._month_lines_surface = surf
        self._month_line_xs = xs
        self._month_line_labels = labels
        self._month_label_surfs = [rt(f_s, lbl, TXT) for lbl in labels]
        self._month_label_surf_xs = xs

    def _invalidate_grid_caches(self):
        self._month_label_surfs = None
        self._month_label_surf_xs = None

    def _draw_scrollbar(self, surface, bx, by, bw):
        if self._content_height > self.window_height:
            bar_h = max(20, int(self.window_height * self.window_height / self._content_height))
            bar_y = by + int(self._scroll_y * self.window_height / self._content_height)
            pygame.draw.rect(surface, (160, 160, 160),
                             pygame.Rect(bx + bw - 8, bar_y, 6, bar_h), border_radius=3)
