# py/ty_sim_mixins/_draw_path_mixin.py
"""台风路径渲染 Mixin：安全连线、路径缓存、增量绘制。"""
from __future__ import annotations
import math
import pygame
from collections import OrderedDict
from ..constants import (
    PATH, CUR_POS,
    FUTURE_LINE_ALPHA, FADE_DURATION,
)


class TySimDrawPathMixin:
    """台风路径绘制：点标记、缓存、增量更新。"""

    @staticmethod
    def _draw_dashed(surface, color, start, end, width):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        pos = 0.0
        dash, gap = 6, 4
        while pos < length:
            seg_end = min(pos + dash, length)
            x1 = int(start[0] + ux * pos)
            y1 = int(start[1] + uy * pos)
            x2 = int(start[0] + ux * seg_end)
            y2 = int(start[1] + uy * seg_end)
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), width)
            pos = seg_end + gap

    @staticmethod
    def _draw_lines_safe(surface, color, points, width, max_seg_len):
        """Draw connected lines, breaking at segments that exceed max_seg_len.
        防止两连续屏幕点落在地图投影折返两侧时产生横跨全屏的伪线。
        """
        if len(points) < 2:
            return
        seg_start = 0
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            dx, dy = x2 - x1, y2 - y1
            if dx * dx + dy * dy > max_seg_len * max_seg_len:
                if i - seg_start >= 2:
                    pygame.draw.lines(surface, color, False, points[seg_start:i], width)
                seg_start = i
        if len(points) - seg_start >= 2:
            pygame.draw.lines(surface, color, False, points[seg_start:], width)

    @staticmethod
    def _draw_lines_colored(surface, points, point_colors, width, max_seg_len, point_types=None):
        """Draw colored line segments. point_types: list of storm type strings,
        EX/SS/SD segments are drawn dashed."""
        if len(points) < 2:
            return
        for i in range(1, len(points)):
            x1, y1 = points[i - 1]
            x2, y2 = points[i]
            dx, dy = x2 - x1, y2 - y1
            if dx * dx + dy * dy <= max_seg_len * max_seg_len:
                c = point_colors[i - 1]
                if point_types and point_types[i - 1] in ('EX', 'SS', 'SD'):
                    TySimDrawPathMixin._draw_dashed(surface, c, (x1, y1), (x2, y2), width)
                else:
                    pygame.draw.line(surface, c, (x1, y1), (x2, y2), width)

    _circle_cache: OrderedDict = OrderedDict()
    _MAX_CIRCLE_CACHE = 512

    _path_render_view_version = 0       # 视图版本号，视图变化时递增

    def _get_circle_marker(self, radius, color):
        key = (radius, color)
        cache = self._circle_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, color, (radius, radius), radius)
        cache[key] = surf
        if len(cache) > self._MAX_CIRCLE_CACHE:
            cache.popitem(last=False)
        return surf

    # ── 非圆形标记缓存（矩形/三角形） ──
    _rect_marker_cache: OrderedDict = OrderedDict()
    _tri_marker_cache: OrderedDict = OrderedDict()
    _MAX_SHAPE_CACHE = 128

    def _get_rect_marker(self, size, color):
        key = (size, color)
        cache = self._rect_marker_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill(color)
        cache[key] = surf
        if len(cache) > self._MAX_SHAPE_CACHE:
            cache.popitem(last=False)
        return surf

    def _get_tri_marker(self, tri_w, tri_h, color):
        key = (tri_w, tri_h, color)
        cache = self._tri_marker_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        surf = pygame.Surface((tri_w * 2, tri_h * 2), pygame.SRCALPHA)
        tri = [(tri_w, 0), (0, tri_h * 2), (tri_w * 2, tri_h * 2)]
        pygame.draw.polygon(surf, color, tri)
        cache[key] = surf
        if len(cache) > self._MAX_SHAPE_CACHE:
            cache.popitem(last=False)
        return surf

    # ── 台风筛选 ──
    def should_draw_typhoon(self, ty) -> bool:
        if self.md == self.MODE_NORMAL:
            if ty == self.current_typhoon():
                return True
            if self.fade_path and ty.finish_time > 0:
                ct = pygame.time.get_ticks()
                if (ct - ty.finish_time) / 1000.0 < FADE_DURATION:
                    return True
            return False
        elif self.md == self.MODE_SEASON:
            if ty.act and ty.ss and not ty.sf:
                return True
            if self.fade_path and ty.sf and ty.finish_time > 0:
                ct = pygame.time.get_ticks()
                if (ct - ty.finish_time) / 1000.0 < FADE_DURATION:
                    return True
            return False
        elif self.md == self.MODE_EDIT:
            if ty == self.edit_typhoon:
                if self.fade_path and ty.finish_time > 0:
                    ct = pygame.time.get_ticks()
                    if (ct - ty.finish_time) / 1000.0 < FADE_DURATION:
                        return True
                return True
            return False
        return False

    def _is_typhoon_visible(self, ty) -> bool:
        """使用 bbox 快速判断台风路径是否与可视区域有交集。
        拖拽期间，将可见区域向反方向偏移以补偿路径的整体平移。"""
        bbox = getattr(ty, 'bbox', None)
        if bbox is None:
            return True  # 无 bbox 时保守绘制
        margin = 20
        map_rect = pygame.Rect(-margin, -margin,
                               self.screen_width + margin * 2,
                               self.map_height + margin * 2)
        # 拖拽时路径 blit 会加上 drag_offset，
        # 把可见矩形向反方向偏移，等效于 bbox 加偏移
        if self._drag_offset_x or self._drag_offset_y:
            map_rect.x -= self._drag_offset_x
            map_rect.y -= self._drag_offset_y
        if map_rect.colliderect(bbox):
            return True
        # bbox 可能因视图平移变得过时，用当前位置的地理坐标做二次确认
        pos = ty.cpos()
        if pos:
            x, y = self.latlon_to_screen(pos['la'], pos['lo'])
            if -margin <= x <= self.screen_width + margin and -margin <= y <= self.map_height + margin:
                # 使路径缓存失效，确保 draw_typhoon 用当前视图坐标重绘
                self._invalidate_path_cache_for_ty(ty)
                return True
        return False

    def _draw_typhoons(self, surface):
        current_ty = self.current_typhoon()
        if self.md == self.MODE_EDIT and self.edit_typhoon:
            self.draw_typhoon(surface, self.edit_typhoon, highlight=True)
        else:
            for ty in self.tys:
                if self.should_draw_typhoon(ty):
                    if not self._is_typhoon_visible(ty):
                        continue
                    self.draw_typhoon(surface, ty, highlight=(ty == current_ty))

    # ── 增量路径渲染缓存（per-typhoon）──

    def _make_path_cache_key(self, ty, screen_points, highlight):
        """生成路径缓存的键。首尾屏幕坐标作为视图指纹。"""
        sp_first = screen_points[0] if screen_points else (0, 0)
        sp_last = screen_points[-1] if screen_points else (0, 0)
        return (highlight, self.point_size,
                self._path_render_view_version,
                sp_first, sp_last, len(screen_points),
                len(ty.pts), id(ty.pts),
                self.md == self.MODE_EDIT and highlight)

    def _make_point_marker(self, point_color, cat, p, radius, point_radius_factor,
                           highlight, is_future):
        """创建一个点标记 Surface（圆/三角/矩形），返回 (surf, offset_x, offset_y)。"""
        if not p.get('official', True):
            size = max(2, int(2 * point_radius_factor))
            return self._get_rect_marker(size, point_color), size // 2, size // 2
        elif cat == "EX":
            tri_h = int(3 * point_radius_factor)
            tri_w = int(3 * point_radius_factor)
            return self._get_tri_marker(tri_w, tri_h, point_color), tri_w, tri_h
        else:
            if is_future and not (highlight and self.md == self.MODE_EDIT):
                if len(point_color) == 3:
                    alpha_pc = (*point_color, FUTURE_LINE_ALPHA)
                else:
                    alpha_pc = (*point_color[:3], min(point_color[3], FUTURE_LINE_ALPHA))
                return self._get_circle_marker(radius, alpha_pc), radius, radius
            else:
                return self._get_circle_marker(radius, point_color), radius, radius

    @staticmethod
    def _build_line_colors(pts, draw_points, dim, segs):
        """为 draw_points 构建逐段颜色列表（每段用终点原始点颜色）。返回 (colors, types)."""
        n_orig = len(pts)
        colors, types = [], []
        for idx in range(1, len(draw_points)):
            orig_idx = min(idx // (segs or 1), n_orig - 1)
            colors.append(pts[orig_idx]['color_dim' if dim else 'color'])
            types.append(pts[orig_idx].get('st', ''))
        return colors, types

    def _render_path_to_surface(self, ty, screen_points, highlight):
        """增量渲染：cached_full（半透明全路径）+ cached_traversed（不透明已走段）。
        使用 bbox 尺寸 Surface，避免全屏分配。"""
        point_radius_factor = self.point_size / 100.0
        if self.fix_icon_point_size and self.map_mgr.map_view.min_scale > 0:
            point_radius_factor *= self.map_mgr.map_view.scale / (self.map_mgr.map_view.min_scale * 2.5)
        base_radius = 3
        radius = int(base_radius * point_radius_factor)
        if radius < 1:
            radius = 1
        max_seg = min(self.screen_width, self.map_height) // 2
        n_pts = len(ty.pts)
        cur_idx = ty.ci
        if not screen_points:
            return pygame.Surface((1, 1), pygame.SRCALPHA), (0, 0)
        key = self._make_path_cache_key(ty, screen_points, highlight)

        # 计算 bbox（含点标记边距）
        margin = radius + 4
        xs = [p[0] for p in screen_points]
        ys = [p[1] for p in screen_points]
        bbox_x = max(0, min(xs) - margin)
        bbox_y = max(0, min(ys) - margin)
        bbox_w = min(self.screen_width - bbox_x, max(xs) - bbox_x + margin * 2)
        bbox_h = min(self.map_height - bbox_y, max(ys) - bbox_y + margin * 2)
        if bbox_w <= 0 or bbox_h <= 0:
            return pygame.Surface((1, 1), pygame.SRCALPHA), (0, 0)

        # ── 缓存失效：重建 full + traversed ──
        if ty._path_cache_key != key:
            line_mode = getattr(self, 'path_mode', 'markers') == 'line'
            line_width = 4 if line_mode else 2
            segs = max(1, self.smooth_path_segments)
            # full: 完整路径（半透明）
            ty._path_cache_full = pygame.Surface((bbox_w, bbox_h), pygame.SRCALPHA)
            full = ty._path_cache_full

            smooth_pts = (ty.v.smooth_screen_points
                          if self.smooth_path else None)
            draw_points = smooth_pts if smooth_pts else screen_points
            rel_points = [(px - bbox_x, py - bbox_y) for px, py in draw_points]

            if line_mode:
                colors, types = self._build_line_colors(ty.pts, draw_points, dim=True, segs=segs if smooth_pts else 1)
                self._draw_lines_colored(full, rel_points, colors, line_width, max_seg, point_types=types)
            else:
                line_color = (*PATH, FUTURE_LINE_ALPHA)
                if highlight and self.md == self.MODE_EDIT:
                    line_color = (*PATH, 255)
                self._draw_lines_safe(full, line_color, rel_points, 2, max_seg)

            if not line_mode:
                for i, (p, (x, y)) in enumerate(zip(ty.pts, screen_points)):
                    point_color = p['color'] if highlight else p['color_dim']
                    cat = p.get('cat', self.get_strength_category(p['w'], p['st']))
                    marker, offset_x, offset_y = self._make_point_marker(
                        point_color, cat, p, radius, point_radius_factor,
                        highlight, is_future=True)
                    full.blit(marker, (x - bbox_x - offset_x, y - bbox_y - offset_y))

            # traversed: 从头构建已走段（不透明）
            ty._path_cache_traversed = pygame.Surface((bbox_w, bbox_h), pygame.SRCALPHA)
            traversed = ty._path_cache_traversed

            smooth_sp = (ty.v.smooth_screen_points
                         if self.smooth_path else None)
            if cur_idx > 0:
                if smooth_sp:
                    end_idx = min(cur_idx * segs, len(smooth_sp) - 1)
                    passed_line = smooth_sp[:end_idx + 1]
                else:
                    passed_line = screen_points[:cur_idx + 1] if len(screen_points) > 1 else screen_points
                rel_line = [(px - bbox_x, py - bbox_y) for px, py in passed_line]
                if line_mode:
                    colors, types = self._build_line_colors(ty.pts[:cur_idx + 1], passed_line, dim=False, segs=segs if smooth_sp else 1)
                    self._draw_lines_colored(traversed, rel_line, colors, line_width, max_seg, point_types=types)
                else:
                    self._draw_lines_safe(traversed, PATH, rel_line, 2, max_seg)

            if not line_mode:
                for i in range(cur_idx):
                    p = ty.pts[i]
                    x, y = screen_points[i]
                    point_color = p['color'] if highlight else p['color_dim']
                    cat = p.get('cat', self.get_strength_category(p['w'], p['st']))
                    marker, offset_x, offset_y = self._make_point_marker(
                        point_color, cat, p, radius, point_radius_factor,
                        highlight, is_future=False)
                    traversed.blit(marker, (x - bbox_x - offset_x, y - bbox_y - offset_y))

            ty._last_rendered_ci = cur_idx
            ty._path_cache_key = key
            ty._path_cache_blit = (bbox_x, bbox_y)


        # ── 增量追加：ci 前进时在 traversed 上追加新线段 ──
        elif cur_idx > ty._last_rendered_ci:
            line_mode = getattr(self, 'path_mode', 'markers') == 'line'
            line_width = 4 if line_mode else 2
            segs = max(1, self.smooth_path_segments)
            traversed = ty._path_cache_traversed
            smooth_sp = (ty.v.smooth_screen_points
                          if self.smooth_path else None)
            if ty._last_rendered_ci >= 0:
                if smooth_sp:
                    i0 = ty._last_rendered_ci * segs
                    i1 = min(cur_idx * segs, len(smooth_sp) - 1)
                    seg = smooth_sp[i0:i1 + 1]
                else:
                    seg = screen_points[ty._last_rendered_ci:cur_idx + 1]
                rel_seg = [(px - bbox_x, py - bbox_y) for px, py in seg]
                if len(rel_seg) > 1:
                    if line_mode:
                        colors, types = self._build_line_colors(ty.pts[ty._last_rendered_ci:cur_idx + 1], seg, dim=False, segs=segs if smooth_sp else 1)
                        self._draw_lines_colored(traversed, rel_seg, colors, line_width, max_seg, point_types=types)
                    else:
                        self._draw_lines_safe(traversed, PATH, rel_seg, 2, max_seg)
            elif cur_idx > 0:
                if smooth_sp:
                    i1 = min(cur_idx * segs, len(smooth_sp) - 1)
                    passed = smooth_sp[:i1 + 1]
                else:
                    passed = screen_points[:cur_idx + 1]
                rel_pass = [(px - bbox_x, py - bbox_y) for px, py in passed]
                if len(rel_pass) > 1:
                    if line_mode:
                        colors, types = self._build_line_colors(ty.pts[:cur_idx + 1], passed, dim=False, segs=segs if smooth_sp else 1)
                        self._draw_lines_colored(traversed, rel_pass, colors, line_width, max_seg, point_types=types)
                    else:
                        self._draw_lines_safe(traversed, PATH, rel_pass, 2, max_seg)

            if not line_mode:
                for i in range(max(0, ty._last_rendered_ci), cur_idx):
                    p = ty.pts[i]
                    x, y = screen_points[i]
                    point_color = p['color'] if highlight else p['color_dim']
                    cat = p.get('cat', self.get_strength_category(p['w'], p['st']))
                    marker, offset_x, offset_y = self._make_point_marker(
                        point_color, cat, p, radius, point_radius_factor,
                        highlight, is_future=False)
                    traversed.blit(marker, (x - bbox_x - offset_x, y - bbox_y - offset_y))

            ty._last_rendered_ci = cur_idx


        # ── ci 回退：重建 traversed ──
        elif cur_idx < ty._last_rendered_ci:
            line_mode = getattr(self, 'path_mode', 'markers') == 'line'
            line_width = 4 if line_mode else 2
            segs = max(1, self.smooth_path_segments)
            traversed = ty._path_cache_traversed
            traversed.fill((0, 0, 0, 0))
            smooth_sp = (ty.v.smooth_screen_points
                          if self.smooth_path else None)
            if cur_idx > 0:
                if smooth_sp:
                    end_idx = min(cur_idx * segs, len(smooth_sp) - 1)
                    passed = smooth_sp[:end_idx + 1]
                else:
                    passed = screen_points[:cur_idx + 1] if len(screen_points) > 1 else screen_points
                rel_pass = [(px - bbox_x, py - bbox_y) for px, py in passed]
                if line_mode:
                    colors, types = self._build_line_colors(ty.pts[:cur_idx + 1], passed, dim=False, segs=segs if smooth_sp else 1)
                    self._draw_lines_colored(traversed, rel_pass, colors, line_width, max_seg, point_types=types)
                else:
                    self._draw_lines_safe(traversed, PATH, rel_pass, 2, max_seg)
            if not line_mode:
                for i in range(cur_idx):
                    p = ty.pts[i]
                    x, y = screen_points[i]
                    point_color = p['color'] if highlight else p['color_dim']
                    cat = p.get('cat', self.get_strength_category(p['w'], p['st']))
                    marker, offset_x, offset_y = self._make_point_marker(
                        point_color, cat, p, radius, point_radius_factor,
                        highlight, is_future=False)
                    traversed.blit(marker, (x - bbox_x - offset_x, y - bbox_y - offset_y))
            ty._last_rendered_ci = cur_idx


        # ── 拖拽中：渲染到 bbox 尺寸 Surface，避免屏幕外路径被裁剪 ──
        dragging = self._drag_offset_x != 0 or self._drag_offset_y != 0
        if dragging:
            drag_key = (cur_idx, highlight)
            if ty._path_cache_drag_key != drag_key:
                line_mode = getattr(self, 'path_mode', 'markers') == 'line'
                line_width = 4 if line_mode else 2
                if not screen_points:
                    min_x = min_y = max_x = max_y = 0
                else:
                    min_x = min(x for x, y in screen_points)
                    min_y = min(y for x, y in screen_points)
                    max_x = max(x for x, y in screen_points)
                    max_y = max(y for x, y in screen_points)
                pad = 30
                box_w = max_x - min_x + pad * 2
                box_h = max_y - min_y + pad * 2
                if box_w < 4:
                    box_w = 4
                if box_h < 4:
                    box_h = 4
                bbox_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)

                def _local(pt):
                    return (pt[0] - min_x + pad, pt[1] - min_y + pad)

                local_pts = [_local(sp) for sp in screen_points]
                f_alpha_for_full = FUTURE_LINE_ALPHA
                if highlight and self.md == self.MODE_EDIT:
                    f_alpha_for_full = 255
                if line_mode:
                    colors, types = self._build_line_colors(ty.pts, screen_points, dim=True, segs=1)
                    self._draw_lines_colored(bbox_surf, local_pts, colors, line_width, max_seg, point_types=types)
                else:
                    self._draw_lines_safe(bbox_surf, (*PATH, f_alpha_for_full), local_pts, 2, max_seg)

                if cur_idx > 0 and len(local_pts) > 1:
                    if line_mode:
                        colors, types = self._build_line_colors(ty.pts[:cur_idx + 1], screen_points[:cur_idx + 1], dim=False, segs=1)
                        self._draw_lines_colored(bbox_surf, local_pts[:cur_idx + 1], colors, line_width, max_seg, point_types=types)
                    else:
                        self._draw_lines_safe(bbox_surf, PATH, local_pts[:cur_idx + 1], 2, max_seg)

                if not line_mode:
                    for i, (p, lpt) in enumerate(zip(ty.pts, local_pts)):
                        lx, ly = lpt
                        point_color = p['color'] if highlight else p['color_dim']
                        cat = p.get('cat', self.get_strength_category(p['w'], p['st']))
                        is_future = i > cur_idx
                        marker, offset_x, offset_y = self._make_point_marker(
                            point_color, cat, p, radius, point_radius_factor,
                            highlight, is_future=is_future)
                        bbox_surf.blit(marker, (lx - offset_x, ly - offset_y))

                if 0 <= cur_idx < n_pts and highlight and not line_mode:
                    lx, ly = local_pts[cur_idx]
                    highlight_r = radius + int(2 * point_radius_factor)
                    outer_surf = self._get_circle_marker(highlight_r, CUR_POS)
                    pc_ci = ty.pts[cur_idx]['color'] if highlight else ty.pts[cur_idx]['color_dim']
                    inner_surf = self._get_circle_marker(radius, pc_ci)
                    bbox_surf.blit(outer_surf, (lx - highlight_r, ly - highlight_r))
                    bbox_surf.blit(inner_surf, (lx - radius, ly - radius))

                ty._path_cache_drag_surf = bbox_surf
                ty._path_cache_drag_key = drag_key
                ty._path_cache_drag_pos = (min_x - pad, min_y - pad)

            return ty._path_cache_drag_surf, ty._path_cache_drag_pos

        blit_pos = getattr(ty, '_path_cache_blit', (0, 0))
        return ty._path_cache_full, ty._path_cache_traversed, blit_pos

    def _blit_highlight(self, surface, x, y, radius, highlight_r, point_color, off_x, off_y):
        outer = self._get_circle_marker(highlight_r, CUR_POS)
        inner = self._get_circle_marker(radius, point_color)
        surface.blit(outer, (x - highlight_r + off_x, y - highlight_r + off_y))
        surface.blit(inner, (x - radius + off_x, y - radius + off_y))

    def _invalidate_path_cache_for_ty(self, ty):
        """使指定台风的增量路径缓存失效。"""
        ty._path_cache_full = None
        ty._path_cache_traversed = None
        ty._last_rendered_ci = -1
        ty._path_cache_key = ()
        ty._path_cache_drag_surf = None
        ty._path_cache_drag_key = ()

    def _invalidate_all_path_caches(self):
        """使所有台风路径缓存失效（视图变化时调用）。"""
        self._path_render_view_version += 1
        for ty in self.tys:
            ty._path_cache_full = None
            ty._path_cache_traversed = None
            ty._last_rendered_ci = -1
            ty._path_cache_key = ()
            ty._path_cache_blit = (0, 0)
            ty._path_cache_drag_surf = None
            ty._path_cache_drag_key = ()

    # ── 路径绘制（使用缓存） ──
    def draw_typhoon(self, surface, ty, highlight):
        if not ty.pts:
            return

        screen_points = getattr(ty, 'screen_points', None)
        if not screen_points or len(screen_points) != len(ty.pts):
            if self.right_button_dragging:
                return
            screen_points = [self.latlon_to_screen(p['la'], p['lo']) for p in ty.pts]
            if hasattr(ty, 'update_screen_points'):
                ty.update_screen_points(self.latlon_to_screen)

        path_alpha = 255
        if self.fade_path and ty.finish_time > 0:
            ct = pygame.time.get_ticks()
            elapsed = (ct - ty.finish_time) / 1000.0
            if elapsed >= FADE_DURATION:
                path_alpha = 0
            else:
                path_alpha = max(0, int(255 * (1.0 - elapsed / FADE_DURATION)))

        if path_alpha <= 0 and self.fade_path:
            return

        # ── 从缓存获取或创建路径 Surface ──
        result = self._render_path_to_surface(
            ty, screen_points, highlight)
        if isinstance(result, tuple) and len(result) == 3:
            full_surf, trav_surf, (blit_x, blit_y) = result
            full_surf.set_alpha(path_alpha)
            trav_surf.set_alpha(path_alpha)
            surface.blit(full_surf, (blit_x + self._drag_offset_x, blit_y + self._drag_offset_y))
            surface.blit(trav_surf, (blit_x + self._drag_offset_x, blit_y + self._drag_offset_y))
        else:
            path_surf, path_blit = result
            path_surf.set_alpha(path_alpha)
            surface.blit(path_surf, (path_blit[0] + self._drag_offset_x, path_blit[1] + self._drag_offset_y))

        # 当前位置高亮（直接绘制，不分配复合 Surface）
        if highlight and not ty.sf:
            if getattr(self, 'path_mode', 'markers') == 'line':
                # 渐变线模式：在台风实时插值位置画红点
                pos = ty.cpos()
                if pos:
                    x, y = self.latlon_to_screen(pos['la'], pos['lo'])
                    pygame.draw.circle(surface, CUR_POS, (x + self._drag_offset_x, y + self._drag_offset_y), 2)
            else:
                n_pts = len(ty.pts)
                cur_idx = ty.ci
                if 0 <= cur_idx < n_pts:
                    p = ty.pts[cur_idx]
                    x, y = screen_points[cur_idx]
                    point_color = p['color'] if highlight else p['color_dim']
                    if path_alpha < 255 and len(point_color) == 3:
                        point_color = (*point_color, path_alpha)
                    point_radius_factor = self.point_size / 100.0
                    if self.fix_icon_point_size and self.map_mgr.map_view.min_scale > 0:
                        point_radius_factor *= self.map_mgr.map_view.scale / (self.map_mgr.map_view.min_scale * 2.5)
                    radius = max(1, int(3 * point_radius_factor))
                    highlight_r = radius + int(2 * point_radius_factor)
                    self._blit_highlight(surface, x, y, radius, highlight_r, point_color, self._drag_offset_x, self._drag_offset_y)
