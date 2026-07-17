# py/statistics/dialog_chart.py
"""ACE 统计图表对话框 + 统计面板 + 洋区框 + 辅助按钮。"""
from __future__ import annotations
import pygame
import os
from typing import List, Tuple, Optional, Dict

from ..constants import (
    f_s, f_m, f_l, rt, TXT, BUTTON_BORDER,
    HEMISPHERE_NORTH, HEMISPHERE_SOUTH,
    DIALOG_TITLE_BAR_HEIGHT,
)
from ..constants.fonts import SmartFont, _load_font, FONT_FILE
from ..input_field import InputField
from ..dialog_base import DraggableDialog

from .data_builder_chart import build_chart_data, ChartData
from .chart_helpers import draw_dashed_h, ChartGridMixin, _offset_rect
from .chart_presets import draw_curve_chart, draw_daily_ace_chart, draw_active_periods_chart, draw_activity_count_chart
from .typhoon_ace_chart import draw_typhoon_ace_chart
from .season_stats import calculate_season_stats

_font_ace_title = None

_PICTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'picture')

def _get_ace_title_font():
    global _font_ace_title
    if _font_ace_title is None:
        _font_ace_title = SmartFont(_load_font(FONT_FILE, 30, 30), _load_font(FONT_FILE, 30, 30))
    return _font_ace_title


class ACEChartDialog(ChartGridMixin, DraggableDialog):
    def __init__(self, sim):
        super().__init__(sim)
        self.close_text = rt(f_s, "关闭", (255, 255, 255))
        self.save_text = rt(f_s, "保存图片", (255, 255, 255))
        self._stats_toggle_text = rt(f_s, "统计数据", (255, 255, 255))
        self._path_cmp_text = rt(f_s, "路径对比", (255, 255, 255))
        self._heatmap_text = rt(f_s, "热力图", (255, 255, 255))
        self._path_len_text = rt(f_s, "路径长度", (255, 255, 255))
        self._jump_btn_text = rt(f_s, "指定年份", (255, 255, 255))
        self._jump_prompt_text = rt(f_s, "输入年份:", TXT)
        self._no_data_text = rt(f_m, "无可用年份数据", TXT)

        self.cumulative_to_current = False
        self.bg_rect = pygame.Rect(0, 0, 1, 1)
        self.title_bar_height = DIALOG_TITLE_BAR_HEIGHT

        self._init_grid_attributes()
        self.bg_rect = pygame.Rect(0, 0, self.window_width, self.window_height)

        # 数据
        self._chart_data = ChartData()
        self.needs_update = True
        self._layout_valid = False
        self._show_stats = False
        self._stats_data: Optional[Dict] = None

        # 缓存
        self._cached_title_surf: Optional[pygame.Surface] = None
        self._cached_title_hash: Optional[int] = None
        self._cached_mode_text: Optional[pygame.Surface] = None
        self._cached_mode_hash: Optional[int] = None

        self._available_years: List[int] = []
        self._selected_year_index = -1

        self._hover_info: Optional[str] = None
        self._hover_pos: Optional[Tuple[int, int]] = None
        self._active_period_click_targets: list = []

        self._close_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._mode_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._save_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._jump_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._arrow_left: Optional[pygame.Rect] = None
        self._arrow_right: Optional[pygame.Rect] = None

        self._bar_page = 0
        self._bar_arrow_left: Optional[pygame.Rect] = None
        self._bar_arrow_right: Optional[pygame.Rect] = None

        self._jump_active = False
        self._jump_field: Optional[InputField] = None

        # 底部按钮区域
        self._stats_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._path_cmp_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._heatmap_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._path_len_btn_rect = pygame.Rect(0, 0, 0, 0)

        # 洋区框绘制
        self._basin_box_rect = pygame.Rect(0, 0, 0, 0)

    # ═══════════════════════════════════════════════
    def activate(self):
        super().activate()
        self.dragging = False
        self._bar_page = 0
        self._jump_active = False
        self._jump_field = None
        self.cumulative_to_current = False
        self._layout_valid = False
        self._show_stats = False
        self._stats_data = None
        self._invalidate_caches()

        self._available_years = sorted([y for y, v in self.sim.yad.items() if v > 0])
        if not self._available_years:
            self._available_years = []
        target = self.sim.current_ace_year
        if target in self._available_years:
            idx = self._available_years.index(target)
        elif self._available_years:
            idx = next((i for i, y in enumerate(self._available_years) if y >= target), 0)
        else:
            idx = -1
        self._selected_year_index = idx
        self.needs_update = True

        if idx >= 0:
            self._rebuild()
            self.needs_update = False
            self._compute_layout()
            self._build_month_cache()
            self._layout_valid = True

        self._center_in_map()

    def deactivate(self):
        super().deactivate()
        self.dragging = False
        self._invalidate_caches()
        self._stats_data = None

    def _invalidate_caches(self):
        self._cached_title_surf = None
        self._cached_title_hash = None
        self._cached_mode_text = None
        self._cached_mode_hash = None
        self._invalidate_grid_caches()

    def _rebuild(self):
        if self._selected_year_index < 0:
            self._chart_data = ChartData()
            return
        year = self._available_years[self._selected_year_index]
        self._chart_data = build_chart_data(
            self.sim, year, self.cumulative_to_current, self._available_years
        )
        # 计算统计数据（洋区限定）
        lm = getattr(self.sim, 'ace_limit_mode', 'none')
        bc = getattr(self.sim, 'ace_limit_basin', '')
        basin = bc if lm == 'basin' else None
        self._stats_data = calculate_season_stats(self.sim, year, basin)
        self._invalidate_caches()
        self._layout_valid = False

    # ═══════════════════════════════════════════════
    #  绘制
    # ═══════════════════════════════════════════════
    def draw(self, surface: pygame.Surface):
        if not self.active:
            return
        if self._selected_year_index < 0 or not self._available_years:
            self.draw_background(surface, self.bg_rect)
            surface.blit(self._no_data_text, (
                self.bg_rect.centerx - self._no_data_text.get_width() // 2,
                self.bg_rect.centery - self._no_data_text.get_height() // 2))
            cb = pygame.Rect(self.bg_rect.x + self.window_width - 90, self.bg_rect.y + 8, 55, 25)
            self._close_btn_rect = cb
            self.draw_button(surface, cb, self.close_text)
            return

        if self.needs_update:
            self._rebuild()
            self.needs_update = False
        self._compute_layout()
        self.draw_background(surface, self.bg_rect)

        box_x, box_y = self.bg_rect.x, self.bg_rect.y
        box_w = self.bg_rect.width
        dialog_y = -self._scroll_y

        # 裁剪到可见窗口
        old_clip = surface.get_clip()
        surface.set_clip(self.bg_rect)

        # 标题
        title_hash = self._title_hash()
        if self._cached_title_surf is None or self._cached_title_hash != title_hash:
            self._cached_title_surf = rt(_get_ace_title_font(), self._build_title(), TXT)
            self._cached_title_hash = title_hash
        surface.blit(self._cached_title_surf, (box_x + 12, box_y + 8))

        self._draw_top_buttons(surface, box_x, box_y, box_w)
        self._hover_info = None
        self._hover_pos = None

        cd = self._chart_data

        # 月份线
        if self._month_lines_surface is None:
            self._build_month_cache()
        if self._month_lines_surface is not None:
            surface.blit(self._month_lines_surface, (box_x + self.padding_left, self._month_line_top + dialog_y))

        # 图表（所有 rect Y 偏移 dy）
        hint = draw_curve_chart(surface, _offset_rect(self.curve_rect, dialog_y),
                                cd.ace_curve_points,
                                cd.year_range, cd.year_total_ace, draw_dashed_h)
        self._apply_hint(hint)
        hint = draw_daily_ace_chart(surface, _offset_rect(self.daily_bar_rect, dialog_y),
                                    cd.daily_ace_list,
                                    cd.year_range, draw_dashed_h)
        self._apply_hint(hint)
        area_map = {}
        areas = getattr(getattr(self.sim, 'res_mgr', None), 'ocean_areas', None)
        if areas and areas.areas:
            area_map = {a.code: a.name_cn for a in areas.areas}
        hint, click_targets = draw_active_periods_chart(surface, _offset_rect(self.chart2_rect, dialog_y),
                                         cd.active_periods,
                                         cd.year_range, self._typhoon_bar_width, area_map)
        self._apply_hint(hint)
        self._active_period_click_targets = click_targets
        hint = draw_activity_count_chart(surface, _offset_rect(self.chart3_rect, dialog_y),
                                         cd.activity_count_list,
                                         cd.year_range, draw_dashed_h)
        self._apply_hint(hint)

        # 月份标签
        if self._month_label_surfs and self._month_label_surf_xs:
            for x_px, ls in zip(self._month_label_surf_xs, self._month_label_surfs):
                surface.blit(ls, (box_x + self.padding_left + x_px - ls.get_width() // 2, self._month_label_y + dialog_y))

        hint, total_pages, multi = draw_typhoon_ace_chart(
            surface, _offset_rect(self.bar_rect, dialog_y), cd.typhoon_ace_list, self._bar_page
        )
        self._apply_hint(hint)

        if multi:
            by2 = self.bar_rect.bottom + dialog_y + 28
            bl = pygame.Rect(self.bar_rect.x + 5, by2, 16, 16)
            br2 = pygame.Rect(self.bar_rect.right - 21, by2, 16, 16)
            pygame.draw.polygon(surface, TXT,
                                [(bl.right, bl.top), (bl.right, bl.bottom), (bl.left + 4, bl.centery)])
            pygame.draw.polygon(surface, TXT,
                                [(br2.left, br2.top), (br2.left, br2.bottom), (br2.right - 4, br2.centery)])
            self._bar_arrow_left = bl
            self._bar_arrow_right = br2
        else:
            self._bar_arrow_left = None
            self._bar_arrow_right = None

        self._draw_bottom_buttons(surface, box_x)
        self._draw_hover(surface)

        # 滚动条（委托给 ChartGridMixin）
        self._draw_scrollbar(surface, box_x, box_y, box_w)

        surface.set_clip(old_clip)

    def _draw_bottom_buttons(self, surface, box_x):
        y_bottom = self.bg_rect.y + self.bg_rect.height - 45
        btn_w, btn_h, gap = 90, 28, 8
        # 保存图片
        sb = pygame.Rect(box_x + 15, y_bottom, 100, btn_h)
        self._save_btn_rect = sb
        self.draw_button(surface, sb, self.save_text)
        # 指定年份
        jb = pygame.Rect(sb.right + gap, y_bottom, 100, btn_h)
        self._jump_btn_rect = jb
        self.draw_button(surface, jb, self._jump_btn_text)
        # 统计数据切换
        stb = pygame.Rect(jb.right + gap, y_bottom, 100, btn_h)
        self._stats_btn_rect = stb
        self.draw_button(surface, stb, self._stats_toggle_text)
        # 路径对比
        pcb = pygame.Rect(stb.right + gap, y_bottom, 100, btn_h)
        self._path_cmp_btn_rect = pcb
        self.draw_button(surface, pcb, self._path_cmp_text)
        # 热力图
        hb = pygame.Rect(pcb.right + gap, y_bottom, 100, btn_h)
        self._heatmap_btn_rect = hb
        self.draw_button(surface, hb, self._heatmap_text)
        # 路径长度
        plb = pygame.Rect(hb.right + gap, y_bottom, 100, btn_h)
        self._path_len_btn_rect = plb
        self.draw_button(surface, plb, self._path_len_text)

        if self._jump_active and self._jump_field:
            self._jump_field.draw(surface)
            surface.blit(self._jump_prompt_text,
                         (self._jump_field.rect.x, self._jump_field.rect.y - 22))

    def _draw_hover(self, surface):
        if self._hover_info and self._hover_pos:
            tip = rt(f_s, self._hover_info, TXT)
            tw, th = tip.get_width() + 8, tip.get_height() + 8
            text_x, text_y = self._hover_pos
            if text_y - th < 0:
                text_y = self._hover_pos[1] + 15
            if text_x + tw > self.sim.screen_width:
                text_x = self.sim.screen_width - tw - 5
            tb = pygame.Surface((tw, th), pygame.SRCALPHA)
            tb.fill((255, 255, 255, 200))
            pygame.draw.rect(tb, BUTTON_BORDER, (0, 0, tw, th), 1)
            tb.blit(tip, (4, 4))
            surface.blit(tb, (text_x, text_y - th))

    # ═══════════════════════════════════════════════
    #  事件
    # ═══════════════════════════════════════════════
    def handle_event(self, e: pygame.event.Event) -> bool:
        if not self.active:
            return False
        if self._jump_active:
            return self._handle_jump_event(e)
        if e.type == pygame.MOUSEWHEEL:
            if self._content_height > self.window_height and self.bg_rect.collidepoint(pygame.mouse.get_pos()):
                max_scroll = self._content_height - self.window_height
                self._scroll_y = max(0, min(max_scroll, self._scroll_y - e.y * 30))
                return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self._handle_click(e):
                return True
        if self.handle_drag_event(e):
            self._layout_valid = False
            return True
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.deactivate()
            return True
        return False

    def _handle_click(self, e):
        x, y = e.pos
        # 优先检测关闭按钮（禁止事件穿透）
        if self._close_btn_rect.collidepoint(x, y):
            self.deactivate()
            return True
        # 活跃时间图点击 → 跳转到台风生成时间
        for br_screen, period in self._active_period_click_targets:
            if br_screen.collidepoint(x, y):
                dt = period['start_dt']
                self._jump_sim_to(dt)
                return True
        # 统计数据切换 → 打开独立统计对话框
        if self._stats_btn_rect.collidepoint(x, y):
            dlg = self.sim.dialog_mgr.season_stats
            year = self._available_years[self._selected_year_index]
            self.sim.current_ace_year = year
            dlg.activate()
            return True
        # 路径对比
        if self._path_cmp_btn_rect.collidepoint(x, y):
            dlg = self.sim.dialog_mgr.path_comparison
            year = self._available_years[self._selected_year_index]
            self.sim.current_ace_year = year
            dlg.activate()
            return True
        # 热力图
        if self._heatmap_btn_rect.collidepoint(x, y):
            dlg = self.sim.dialog_mgr.heatmap
            year = self._available_years[self._selected_year_index]
            self.sim.current_ace_year = year
            dlg.activate()
            return True
        # 路径长度
        if self._path_len_btn_rect.collidepoint(x, y):
            dlg = self.sim.dialog_mgr.path_length_viewer
            year = self._available_years[self._selected_year_index]
            self.sim.current_ace_year = year
            dlg.activate()
            return True
        # 模式切换
        if self._mode_btn_rect.collidepoint(x, y):
            self.cumulative_to_current = not self.cumulative_to_current
            self._invalidate_caches()
            self.needs_update = True
            return True
        # 保存图片
        if self._save_btn_rect.collidepoint(x, y):
            self._save_chart_image()
            return True
        # 跳页
        if self._jump_btn_rect.collidepoint(x, y):
            self._start_jump()
            return True
        # 年份箭头
        if self._arrow_left and self._arrow_left.collidepoint(x, y):
            if self._selected_year_index > 0:
                self._selected_year_index -= 1
                self._invalidate_caches()
                self.needs_update = True
            return True
        if self._arrow_right and self._arrow_right.collidepoint(x, y):
            if self._selected_year_index < len(self._available_years) - 1:
                self._selected_year_index += 1
                self._invalidate_caches()
                self.needs_update = True
            return True
        # 柱状图翻页
        if self._bar_arrow_left and self._bar_arrow_left.collidepoint(x, y):
            if self._bar_page > 0:
                self._bar_page -= 1
            return True
        if self._bar_arrow_right and self._bar_arrow_right.collidepoint(x, y):
            tp = (len(self._chart_data.typhoon_ace_list) + 19) // 20
            if self._bar_page < tp - 1:
                self._bar_page += 1
            return True
        return False

    # ── 跳页 ──
    def _handle_jump_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self._jump_active = False
                self._jump_field = None
                return True
            if e.key == pygame.K_RETURN:
                self._do_jump()
                return True
        if self._jump_field and self._jump_field.handle_event(e):
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self._jump_field and not self._jump_field.rect.collidepoint(e.pos):
                self._do_jump()
                return True
        return True

    def _start_jump(self):
        self._jump_active = True
        r = pygame.Rect(self.bg_rect.x + self.bg_rect.width // 2 - 50, self.bg_rect.y + 35, 100, 24)
        self._jump_field = InputField(r, max_length=4, validator=lambda c: c.isdigit())
        self._jump_field.activate()

    def _do_jump(self):
        if self._jump_field:
            try:
                y = int(self._jump_field.get_text())
                if y in self._available_years:
                    self._selected_year_index = self._available_years.index(y)
                    self._invalidate_caches()
                    self.needs_update = True
            except ValueError:
                pass
        self._jump_active = False
        self._jump_field = None

    def _save_chart_image(self):
        out = _PICTURE_DIR
        os.makedirs(out, exist_ok=True)
        yv = self._available_years[self._selected_year_index]
        yd = self._year_display(yv).replace(' ', '_')
        lm = getattr(self.sim, 'ace_limit_mode', 'none')
        bc = getattr(self.sim, 'ace_limit_basin', '')
        if lm in ('none', '') and not bc:
            filename = f"{yd}_GLOBAL_ACE"
        elif lm == 'basin' and bc:
            a = self._get_basin_area(bc)
            filename = f"{yd}_{a.name_full if a else bc}_ACE"
        else:
            filename = f"{yd}_ACE"

        ox, oy = self.bg_rect.x, self.bg_rect.y
        self.bg_rect.x = 0
        self.bg_rect.y = 0
        self._layout_valid = False
        self._compute_layout()
        tmp = pygame.Surface((self.window_width, self.window_height))
        self.draw(tmp)
        self.bg_rect.x, self.bg_rect.y = ox, oy
        self._layout_valid = False
        self._compute_layout()

        filepath = os.path.join(out, f"{filename}.png")
        try:
            pygame.image.save(tmp, filepath)
            self.sim.show_error(f"图表已保存为 {filepath}")
        except Exception as e:
            self.sim.show_error(f"保存失败: {e}")

    def _get_basin_area(self, code):
        res_mgr = getattr(self.sim, 'res_mgr', None)
        areas = getattr(res_mgr, 'ocean_areas', None)
        return areas.get_by_code(code) if areas else None

    # ── 标题 ──
    def _build_title(self) -> str:
        if self._selected_year_index < 0 or not self._available_years:
            return "No Data"
        yv = self._available_years[self._selected_year_index]
        yd = self._year_display(yv)
        tace = self.sim.yad.get(yv, 0.0)
        lm = getattr(self.sim, 'ace_limit_mode', 'none')
        bc = getattr(self.sim, 'ace_limit_basin', '')
        if lm in ('none', '') and not bc:
            return f"{yd} GLOBAL ACE: {tace:.4f}"
        if lm == 'basin' and bc:
            a = self._get_basin_area(bc)
            bd = a.name_full if a else bc
            avg = a.avg_ace if a else 0.0
        else:
            bd = ""
            avg = getattr(getattr(getattr(self.sim, 'res_mgr', None), 'ocean_areas', None),
                          'total_avg_ace', 0) or 0
        anom = tace - avg
        sign = '+' if anom >= 0 else ''
        if bd:
            return f"{yd} {bd} ACE: {tace:.4f} ({sign}{anom:.4f})"
        return f"{yd} ACE: {tace:.4f} ({sign}{anom:.4f})"

    def _year_display(self, year: int) -> str:
        if self.sim.hemisphere == HEMISPHERE_SOUTH:
            return f"{year} - {year + 1}"
        return str(year)

    def _title_hash(self) -> int:
        yv = self._available_years[self._selected_year_index]
        return hash((yv, self.cumulative_to_current, self.sim.current_ace_year))

    def _apply_hint(self, hint):
        if hint is not None:
            self._hover_info, self._hover_pos = hint

    def _jump_sim_to(self, dt):
        """跳转模拟时间到指定日期（委托给 SeasonController）。"""

        sim = self.sim
        if hasattr(sim, 'season_ctrl'):
            sim.season_ctrl.jump_to(dt)
            sim._sync_season_state()
        sim._view_dirty = True
        self.needs_update = True

    def _draw_top_buttons(self, surface, box_x, box_y, box_w):
        BAR_Y = box_y + 6
        BAR_H = 26
        GAP = 8
        a_sz = 16
        cbtn = pygame.Rect(box_x + box_w - 55 - 10, BAR_Y, 55, BAR_H)
        self.draw_button(surface, cbtn, self.close_text)
        self._close_btn_rect = cbtn
        acy = BAR_Y + BAR_H // 2
        rr = pygame.Rect(cbtn.left - GAP - a_sz, acy - a_sz // 2, a_sz, a_sz)
        pygame.draw.polygon(surface, TXT,
                            [(rr.left, rr.top), (rr.left, rr.bottom), (rr.right - 4, rr.centery)])
        self._arrow_right = rr
        lr = pygame.Rect(rr.left - GAP - a_sz, acy - a_sz // 2, a_sz, a_sz)
        pygame.draw.polygon(surface, TXT,
                            [(lr.right, lr.top), (lr.right, lr.bottom), (lr.left + 4, lr.centery)])
        self._arrow_left = lr
        mb = pygame.Rect(lr.left - GAP - 165, BAR_Y, 165, BAR_H)

        sy = self._available_years[self._selected_year_index]
        mode_hash = (self.cumulative_to_current, sy, self.sim.current_ace_year, self.sim.hemisphere)
        if self._cached_mode_text is None or self._cached_mode_hash != mode_hash:
            if self.cumulative_to_current and sy == self.sim.current_ace_year:
                ms = "当前：运行时间"
            elif self.cumulative_to_current:
                ms = "当前：非当前年份"
            else:
                ms = "当前：截止到12/31" if self.sim.hemisphere == HEMISPHERE_NORTH else "当前：截止到次年6/30"
            self._cached_mode_text = rt(f_s, ms, TXT)
            self._cached_mode_hash = mode_hash
        self.draw_button(surface, mb, self._cached_mode_text)
        self._mode_btn_rect = mb