# py/statistics/chart_presets.py
from __future__ import annotations
import math
import pygame
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict

from ..constants import TXT, f_s, rt
from .chart_helpers import DASH_COLOR, _get_dashed_h_surface


# ════════════════════ 每日 ACE 柱状图 ════════════════════

DAILY_BAR_COLOR = (0, 200, 180)
DAILY_BAR_MAX_COLOR = (220, 40, 40)

_daily_ace_cache: Dict[Tuple, dict] = {}
_MAX_CACHE = 16


def draw_daily_ace_chart(
    surface: pygame.Surface,
    rect: pygame.Rect,
    daily_ace_list: List[Tuple[int, float]],
    year_range: Tuple,
    draw_dashed_h,
) -> Optional[Tuple[str, Tuple[int, int]]]:
    if not daily_ace_list:
        return None

    n_days = len(daily_ace_list)
    if n_days == 0:
        return None

    key = (id(daily_ace_list), rect.width, rect.height)

    if key not in _daily_ace_cache:
        cached = {}
        w, h = rect.width, rect.height

        max_daily = max(ace for _, ace in daily_ace_list)
        if max_daily <= 0:
            max_daily = 1.0
        y_max = max_daily * 1.2

        bar_w = w / n_days
        max_i = max(range(n_days), key=lambda i: daily_ace_list[i][1])

        chart_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        chart_surf.fill((0, 0, 0, 0))

        start_dt, _, _ = year_range
        max_labels = []

        for i, (_, ace) in enumerate(daily_ace_list):
            x_px = i * bar_w
            rel_h = ace / y_max if y_max > 0 else 0
            bar_h_val = max(1, rel_h * h)
            bar_y = h - bar_h_val
            color = DAILY_BAR_MAX_COLOR if (i == max_i and ace > 0) else DAILY_BAR_COLOR
            br = pygame.Rect(int(x_px), int(bar_y), max(1, int(math.ceil(bar_w))), int(bar_h_val))
            pygame.draw.rect(chart_surf, color, br)

            if i == max_i and ace > 0:
                al = rt(f_s, f"{ace:.4f}", DAILY_BAR_MAX_COLOR)
                lx = br.centerx - al.get_width() // 2
                ly = br.top - al.get_height() - 2
                if ly < 0:
                    ly = br.bottom + 2
                max_labels.append((al, lx, ly))

        bw_line = 2
        pygame.draw.line(chart_surf, TXT, (0, 0), (0, h), bw_line)
        pygame.draw.line(chart_surf, TXT, (w - 1, 0), (w - 1, h), bw_line)
        pygame.draw.line(chart_surf, TXT, (0, h - 1), (w, h - 1), bw_line)

        tick_labels = []
        y_tick_step = 5.0 if y_max >= 30 else 2.0
        val = 0.0
        while val <= y_max:
            rel = val / y_max
            y_px = h - rel * h
            lbl = rt(f_s, f"{val:.0f}", TXT)
            tick_labels.append((lbl, int(y_px)))
            if val > 0.001:
                dash_surf = _get_dashed_h_surface(w, DASH_COLOR)
                chart_surf.blit(dash_surf, (0, int(y_px)))
            val += y_tick_step

        cached['chart_surf'] = chart_surf
        cached['tick_labels'] = tick_labels
        cached['max_labels'] = max_labels
        cached['n_days'] = n_days
        cached['bar_w'] = bar_w
        cached['start_dt'] = start_dt
        cached['daily_ace_list'] = daily_ace_list

        if len(_daily_ace_cache) >= _MAX_CACHE:
            _daily_ace_cache.pop(next(iter(_daily_ace_cache)))
        _daily_ace_cache[key] = cached
    else:
        cached = _daily_ace_cache[key]

    surface.blit(cached['chart_surf'], rect.topleft)
    for lbl, y_px in cached['tick_labels']:
        surface.blit(lbl, (rect.x - lbl.get_width() - 10, rect.y + y_px - lbl.get_height() // 2))
    for al, lx, ly in cached.get('max_labels', []):
        surface.blit(al, (rect.x + lx, rect.y + ly))

    mx, my = pygame.mouse.get_pos()
    if rect.collidepoint(mx, my):
        day_i = int((mx - rect.x) / cached['bar_w'])
        if 0 <= day_i < cached['n_days']:
            _, ace = cached['daily_ace_list'][day_i]
            dt = cached['start_dt'] + timedelta(days=day_i)
            return f"{dt.month}/{dt.day}: {ace:.4f}", (mx + 15, my - 25)
    return None


# ════════════════════ 活跃台风数柱状图 ════════════════════

ACTIVITY_BAR_COLOR = (0, 200, 180)
ACTIVITY_BAR_MAX_COLOR = (220, 40, 40)

_activity_cache: Dict[Tuple, dict] = {}


def draw_activity_count_chart(
    surface: pygame.Surface,
    rect: pygame.Rect,
    activity_count_list: List[Tuple[int, int]],
    year_range: Tuple,
    draw_dashed_h,
) -> Optional[Tuple[str, Tuple[int, int]]]:
    if not activity_count_list:
        return None

    n_days = len(activity_count_list)
    if n_days == 0:
        return None

    key = (id(activity_count_list), rect.width, rect.height)

    if key not in _activity_cache:
        cached = {}
        w, h = rect.width, rect.height

        max_count = max(c for _, c in activity_count_list)
        if max_count <= 0:
            max_count = 1
        y_max = float(max_count + 1)

        bar_w = w / n_days
        max_i = max(range(n_days), key=lambda i: activity_count_list[i][1])

        chart_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        chart_surf.fill((0, 0, 0, 0))

        start_dt, _, _ = year_range

        for i, (_, cnt) in enumerate(activity_count_list):
            x_px = i * bar_w
            rel_h = cnt / y_max if y_max > 0 else 0
            bar_h_val = max(1, rel_h * h)
            bar_y = h - bar_h_val
            color = ACTIVITY_BAR_MAX_COLOR if (i == max_i and cnt > 0) else ACTIVITY_BAR_COLOR
            br = pygame.Rect(int(x_px), int(bar_y), max(1, int(math.ceil(bar_w))), int(bar_h_val))
            pygame.draw.rect(chart_surf, color, br)

        tick_labels = []
        y_tick_step = 3.0 if y_max >= 9 else 2.0
        val = 0.0
        while val <= y_max:
            rel = val / y_max
            y_px = h - rel * h
            lbl = rt(f_s, f"{val:.0f}", TXT)
            tick_labels.append((lbl, int(y_px)))
            if val > 0.001:
                dash_surf = _get_dashed_h_surface(w, DASH_COLOR)
                chart_surf.blit(dash_surf, (0, int(y_px)))
            val += y_tick_step

        cached['chart_surf'] = chart_surf
        cached['tick_labels'] = tick_labels
        cached['n_days'] = n_days
        cached['bar_w'] = bar_w
        cached['start_dt'] = start_dt
        cached['activity_count_list'] = activity_count_list

        if len(_activity_cache) >= _MAX_CACHE:
            _activity_cache.pop(next(iter(_activity_cache)))
        _activity_cache[key] = cached
    else:
        cached = _activity_cache[key]

    surface.blit(cached['chart_surf'], rect.topleft)
    for lbl, y_px in cached['tick_labels']:
        surface.blit(lbl, (rect.x - lbl.get_width() - 10, rect.y + y_px - lbl.get_height() // 2))

    mx, my = pygame.mouse.get_pos()
    if rect.collidepoint(mx, my):
        day_i = int((mx - rect.x) / cached['bar_w'])
        n_days = cached['n_days']
        if 0 <= day_i < n_days:
            _, cnt = cached['activity_count_list'][day_i]
            dt = cached['start_dt'] + timedelta(days=day_i)
            return f"{dt.month}/{dt.day}: {cnt}个活跃台风", (mx + 15, my - 25)
    return None


# ════════════════════ 活跃周期图 ════════════════════

_active_periods_cache: Dict[Tuple, dict] = {}


def draw_active_periods_chart(
    surface: pygame.Surface,
    rect: pygame.Rect,
    active_periods: List[dict],
    year_range: Tuple,
    typhoon_bar_width: float,
    area_map: Dict[str, str] = None,
) -> Tuple[Optional[Tuple[str, Tuple[int, int]]], list]:
    if not active_periods:
        return None, []

    bw = typhoon_bar_width
    key = (id(active_periods), rect.width, rect.height, round(bw, 2))

    cached = _active_periods_cache.get(key)
    if cached is None or cached.get('src') is not active_periods:
        cached = {'src': active_periods}
        w, h = rect.width, rect.height
        n_mid = 25
        zone_h = 18
        pad_edge = 15
        bar_h = 14
        bar_pad = 2

        start_dt, _, total_hours = year_range

        chart_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        chart_surf.fill((0, 0, 0, 0))

        bar_info = []
        name_entries = []

        for i, period in enumerate(active_periods):
            zone_idx = i % n_mid
            zone_top = pad_edge + zone_idx * zone_h
            bar_top = zone_top + bar_pad

            t1_hours = max(0, (period['start_dt'] - start_dt).total_seconds() / 3600)
            t2_hours = min(total_hours, (period['end_dt'] - start_dt).total_seconds() / 3600)
            x1 = (t1_hours / total_hours) * w
            x2 = (t2_hours / total_hours) * w
            bar_w_px = max(1, x2 - x1)

            bar_rect = pygame.Rect(int(x1), int(bar_top), int(bar_w_px), max(1, int(bar_h)))
            color = period['color']
            pygame.draw.rect(chart_surf, color, bar_rect)

            type2_times = period.get('type2_times', [])
            for k in range(0, len(type2_times) - 1, 2):
                ta, tb = type2_times[k], type2_times[k + 1]
                if ta is None or tb is None:
                    continue
                ha = max(0, (ta - start_dt).total_seconds() / 3600)
                hb = min(total_hours, (tb - start_dt).total_seconds() / 3600)
                if hb <= ha:
                    continue
                sx1 = (ha / total_hours) * w
                sx2 = (hb / total_hours) * w
                sr = pygame.Rect(int(sx1), int(bar_top), max(1, int(sx2 - sx1)), max(1, int(bar_h)))
                alpha_color = (color[0], color[1], color[2], 128)
                pygame.draw.rect(chart_surf, (255, 255, 255), sr)
                overlay = pygame.Surface((sr.width, sr.height), pygame.SRCALPHA)
                overlay.fill(alpha_color)
                chart_surf.blit(overlay, sr)

            pygame.draw.rect(chart_surf, (0, 0, 0), bar_rect, 1)

            name_surf = period.get('name_surf')
            if name_surf is None:
                name_surf = rt(f_s, period['name_str'], (0, 0, 0))
                period['name_surf'] = name_surf
            name_entries.append((name_surf, bar_rect.left, bar_rect.centery))

            basin_name = (area_map.get(period.get('basin', ''), period.get('basin', ''))
                          if area_map else '')
            hover_str = (
                f"{period['name_str']}: "
                f"{period['start_dt'].strftime('%m/%d %HZ')} - "
                f"{period['end_dt'].strftime('%m/%d %HZ')}"
                f"{'  ' + basin_name if basin_name else ''}"
            )
            bar_info.append((bar_rect, hover_str, period))

        cached['chart_surf'] = chart_surf
        cached['bar_info'] = bar_info
        cached['name_entries'] = name_entries

        if len(_active_periods_cache) >= _MAX_CACHE:
            _active_periods_cache.pop(next(iter(_active_periods_cache)))
        _active_periods_cache[key] = cached

    surface.blit(cached['chart_surf'], rect.topleft)

    for name_surf, bar_left, bar_cy in cached['name_entries']:
        nx = rect.x + bar_left - name_surf.get_width() - 3
        ny = rect.y + bar_cy - name_surf.get_height() // 2
        surface.blit(name_surf, (nx, ny))

    mx, my = pygame.mouse.get_pos()
    hover_result = None
    click_targets = []
    for br_local, hover_str, period in cached['bar_info']:
        br_screen = br_local.move(rect.x, rect.y)
        click_targets.append((br_screen, period))
        if br_screen.collidepoint(mx, my):
            hover_result = (hover_str, (mx + 15, my - 25))
    return hover_result, click_targets


# ════════════════════ ACE 累计曲线图 ════════════════════

CURVE_BLUE = (30, 100, 220)

_curve_cache: Dict[Tuple, dict] = {}


def _make_curve_cache_key(
    ace_curve_points: List[Tuple[datetime, float]],
    rect_size: Tuple[int, int],
    year_total_ace: float,
) -> Tuple:
    return (id(ace_curve_points), rect_size[0], rect_size[1], round(year_total_ace, 1))


def draw_curve_chart(
    surface: pygame.Surface,
    rect: pygame.Rect,
    ace_curve_points: List[Tuple[datetime, float]],
    year_range: Tuple[datetime, datetime, int],
    year_total_ace: float,
    draw_dashed_h,
) -> Optional[Tuple[str, Tuple[int, int]]]:
    if not ace_curve_points:
        return None

    start_dt, end_dt, total_hours = year_range
    key = _make_curve_cache_key(ace_curve_points, (rect.width, rect.height), year_total_ace)

    cached = _curve_cache.get(key)
    if cached is None or cached.get('src') is not ace_curve_points:
        cached = {'src': ace_curve_points}
        x_min, x_max = 0, total_hours
        max_cum = max(p[1] for p in ace_curve_points)
        yt = float(year_total_ace or max_cum)
        y_min_val = -0.05 * yt
        y_max_val = max_cum * 1.1
        if y_max_val - y_min_val < 1:
            y_max_val = y_min_val + 10.0

        w, h = rect.width, rect.height
        chart_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        chart_surf.fill((0, 0, 0, 0))

        pygame.draw.rect(chart_surf, TXT, (0, 0, w, h), 2)

        y_step = 200.0 if y_max_val >= 1000 else 50.0
        y_range = y_max_val - y_min_val
        tick_labels = []
        if y_range > 0:
            val = 0.0
            while val <= y_max_val:
                if val >= y_min_val:
                    rel = (val - y_min_val) / y_range
                    y_px = h - rel * h
                    pygame.draw.line(chart_surf, TXT, (0, int(y_px)), (5, int(y_px)), 1)
                    lbl = rt(f_s, f"{val:.0f}", TXT)
                    tick_labels.append((lbl, int(y_px)))
                    if abs(val) > 0.001:
                        dash_surf = _get_dashed_h_surface(w, DASH_COLOR)
                        chart_surf.blit(dash_surf, (0, int(y_px)))
                val += y_step

        cached['tick_labels'] = tick_labels
        cached['chart_surf'] = chart_surf

        def mapper(xv, yv):
            rx = (xv - x_min) / (x_max - x_min) if x_max != x_min else 0
            ry = (yv - y_min_val) / y_range if y_range != 0 else 0
            return rect.x + rx * w, rect.y + (h - ry * h)

        pts = []
        for dt, ace in ace_curve_points:
            hours = max(0, min((dt - start_dt).total_seconds() / 3600, total_hours))
            x, y = mapper(hours, ace)
            pts.append((int(x), int(y)))

        cached['pts'] = pts

        curve_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        curve_overlay.fill((0, 0, 0, 0))
        if len(pts) > 1:
            local_pts = [(px - rect.x, py - rect.y) for px, py in pts]
            pygame.draw.lines(curve_overlay, CURVE_BLUE, False, local_pts, 2)
        cached['curve_overlay'] = curve_overlay

        if len(_curve_cache) >= _MAX_CACHE:
            _curve_cache.pop(next(iter(_curve_cache)))
        _curve_cache[key] = cached

    surface.blit(cached['chart_surf'], rect.topleft)

    for lbl, y_px in cached['tick_labels']:
        surface.blit(lbl, (rect.x - lbl.get_width() - 10, rect.y + y_px - lbl.get_height() // 2))

    surface.blit(cached['curve_overlay'], rect.topleft)

    mx, my = pygame.mouse.get_pos()
    for i, (px, py) in enumerate(cached['pts']):
        if abs(mx - px) + abs(my - py) < 10:
            dt, ace = ace_curve_points[i]
            return f"{dt.month}/{dt.day} {dt.hour:02d}Z: {ace:.4f}", (mx + 15, my - 25)
    return None
