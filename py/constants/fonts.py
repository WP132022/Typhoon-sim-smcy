"""字体系统：SmartFont、字体实例、rt()渲染"""
from __future__ import annotations

import pygame
import os
from typing import Tuple, Dict
from functools import lru_cache
from collections import OrderedDict

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'font')

FONT_FILE = 'MapleMono-NF-CN-Medium.ttf'


def _load_font(filename: str, size: int, fallback_size: int):
    path = os.path.join(_FONT_DIR, filename)
    try:
        return pygame.font.Font(path, size)
    except Exception:
        return pygame.font.Font(None, fallback_size)


font_en_l = _load_font(FONT_FILE, 22, 22)
font_en_m = _load_font(FONT_FILE, 18, 18)
font_en_s = _load_font(FONT_FILE, 14, 14)
font_en_name = _load_font(FONT_FILE, 21, 21)

font_zh_l = _load_font(FONT_FILE, 22, 22)
font_zh_m = _load_font(FONT_FILE, 18, 18)
font_zh_s = _load_font(FONT_FILE, 14, 14)
font_zh_name = _load_font(FONT_FILE, 21, 21)


def _is_cjk_char(cp: int) -> bool:
    return ((0x2E80 <= cp <= 0x2FDF) or    # CJK Radicals
            (0x3000 <= cp <= 0x303F) or    # CJK Symbols
            (0x3040 <= cp <= 0x309F) or    # Hiragana
            (0x30A0 <= cp <= 0x30FF) or    # Katakana
            (0x3400 <= cp <= 0x4DBF) or    # CJK Extension A
            (0x4E00 <= cp <= 0x9FFF) or    # CJK Unified
            (0xF900 <= cp <= 0xFAFF) or    # CJK Compatibility
            (0xFF01 <= cp <= 0xFF60) or    # Fullwidth forms
            (0xAC00 <= cp <= 0xD7AF))      # Hangul


@lru_cache(maxsize=1024)
def _split_runs(text: str) -> tuple:
    """把文本切成 (is_cjk, 片段) 的连续段：汉字用中文字体，其余用英文字体。"""
    runs = []
    start = 0
    cur = None
    for i, ch in enumerate(text):
        is_cjk = _is_cjk_char(ord(ch))
        if cur is None:
            cur = is_cjk
        elif is_cjk != cur:
            runs.append((cur, text[start:i]))
            start = i
            cur = is_cjk
    if text:
        runs.append((cur, text[start:]))
    return tuple(runs)


class SmartFont:
    def __init__(self, en_font, zh_font, maxsize=128):
        self.en_font = en_font
        self.zh_font = zh_font
        self._cache: Dict[Tuple[str, Tuple[int, int, int]], pygame.Surface] = {}
        self.maxsize = maxsize

    def _font_for(self, is_cjk: bool):
        return self.zh_font if is_cjk else self.en_font

    def _render_mixed(self, runs, antialias, color) -> pygame.Surface:
        """分段渲染后按基线对齐拼接。"""
        parts = []
        max_ascent = 0
        for is_cjk, seg in runs:
            font = self._font_for(is_cjk)
            parts.append((font, font.render(seg, antialias, color)))
            max_ascent = max(max_ascent, font.get_ascent())
        width = sum(s.get_width() for _, s in parts)
        height = max(max_ascent - f.get_ascent() + s.get_height() for f, s in parts)
        canvas = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
        x = 0
        for f, s in parts:
            canvas.blit(s, (x, max_ascent - f.get_ascent()))
            x += s.get_width()
        return canvas

    def render(self, text, antialias, color):
        key = (text, color, antialias)
        if key in self._cache:
            return self._cache[key]
        if len(self._cache) >= self.maxsize:
            self._cache.pop(next(iter(self._cache)))
        runs = _split_runs(text)
        if len(runs) <= 1:
            font = self._font_for(runs[0][0]) if runs else self.en_font
            surf = font.render(text, antialias, color)
        else:
            surf = self._render_mixed(runs, antialias, color)
        self._cache[key] = surf
        return surf

    def size(self, text):
        runs = _split_runs(text)
        if len(runs) <= 1:
            font = self._font_for(runs[0][0]) if runs else self.en_font
            return font.size(text)
        w, h = 0, 0
        for is_cjk, seg in runs:
            sw, sh = self._font_for(is_cjk).size(seg)
            w += sw
            h = max(h, sh)
        return (w, h)

    def get_height(self):
        return max(self.en_font.get_height(), self.zh_font.get_height())


font_en_15 = _load_font(FONT_FILE, 15, 15)
font_en_19 = _load_font(FONT_FILE, 19, 19)
font_zh_15 = _load_font(FONT_FILE, 15, 15)
font_zh_19 = _load_font(FONT_FILE, 19, 19)

f_l = SmartFont(font_en_l, font_zh_l)
f_m = SmartFont(font_en_m, font_zh_m)
f_s = SmartFont(font_en_s, font_zh_s)
f_name = SmartFont(font_en_name, font_zh_name)
f_15 = SmartFont(font_en_15, font_zh_15)
f_19 = SmartFont(font_en_19, font_zh_19)


def rt(f, text, color, max_width=None):
    if max_width is None:
        return f.render(text, True, color)
    if not hasattr(rt, "_cache"):
        rt._cache = OrderedDict()
    cache = rt._cache
    max_cache_size = 1024
    key = (id(f), text, color, max_width)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    if len(cache) >= max_cache_size:
        cache.popitem(last=False)
    words = text.split(' ')
    lines, cur = [], ""
    for wd in words:
        test = cur + wd + " "
        if f.size(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = wd + " "
    if cur:
        lines.append(cur)
    surfaces = [f.render(ln, True, color) for ln in lines]
    h = sum(sf.get_height() for sf in surfaces)
    w = max(sf.get_width() for sf in surfaces)
    canvas = pygame.Surface((w, h), pygame.SRCALPHA)
    y = 0
    for sf in surfaces:
        canvas.blit(sf, (0, y))
        y += sf.get_height()
    cache[key] = canvas
    return canvas
