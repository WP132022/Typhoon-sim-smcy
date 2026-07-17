# py/utils.py
"""工具函数。"""
from __future__ import annotations

import os
import json
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)
_DEFAULT_W, _DEFAULT_H = 1360, 885


def load_window_size() -> Tuple[int, int]:
    try:
        with open("config.json", 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        w = max(800, min(cfg.get("screen_width", _DEFAULT_W), 3840))
        h = max(600, min(cfg.get("screen_height", _DEFAULT_H), 2160))
        return int(w), int(h)
    except Exception as e:
        logger.warning(f"无法加载窗口尺寸配置，使用默认值 {_DEFAULT_W}x{_DEFAULT_H}: {e}")
        return _DEFAULT_W, _DEFAULT_H


def find_insensitive_path(base_path: str) -> Optional[str]:
    if os.path.exists(base_path):
        return base_path
    for variant in (base_path.lower(), base_path.upper()):
        if os.path.exists(variant):
            return variant
    directory, filename = os.path.dirname(base_path), os.path.basename(base_path).lower()
    if os.path.isdir(directory):
        for f in os.listdir(directory):
            if f.lower() == filename:
                return os.path.join(directory, f)
    return None


fip = find_insensitive_path

_NON_TROPICAL_TYPES = frozenset({'MD', 'SS', 'SD', 'EX', 'LO'})
_EXCLUDED_TYPES = frozenset({'MD', 'SS', 'SD', 'EX', 'LO', 'DB'})

# Saffir-Simpson 风力等级阈值 (kt)
_WIND_TD_MAX = 28
_WIND_TS_MIN = 34
_WIND_STS_MIN = 49
_WIND_C1_MIN = 64
_WIND_C2_MINUS_MIN = 83
_WIND_C2_MIN = 86
_WIND_C3_MINUS_MIN = 96
_WIND_C3_MIN = 105
_WIND_C4_MIN = 113
_WIND_C4_ST_MIN = 130
_WIND_C5_MIN = 137


def get_valid_winds(pts, exclude_extra: bool = False) -> list:
    excluded = _EXCLUDED_TYPES if exclude_extra else _NON_TROPICAL_TYPES
    return [p['w'] for p in pts if p['st'].upper() not in excluded]


def get_tropical_points(pts) -> list:
    return [p for p in pts if p['st'].upper() not in _NON_TROPICAL_TYPES]


def max_wind_from_points(pts, exclude_extra: bool = False) -> int:
    winds = get_valid_winds(pts, exclude_extra)
    return max(winds) if winds else 0


def infer_strength_category(wind: int, stype: str) -> str:
    st = stype.upper()
    if st in ('MD', 'SD', 'SS', 'LO', 'TD', 'DB', 'WV'):
        return st
    if st == 'EX':
        return "EX"
    if wind <= _WIND_TD_MAX:
        return "DB"
    if wind < _WIND_TS_MIN:
        return "TD"
    if wind < _WIND_STS_MIN:
        return "TS"
    if wind < _WIND_C1_MIN:
        return "STS"
    if wind < _WIND_C2_MINUS_MIN:
        return "C1"
    if wind < _WIND_C2_MIN:
        return "C2-"
    if wind < _WIND_C3_MINUS_MIN:
        return "C2"
    if wind < _WIND_C3_MIN:
        return "C3-"
    if wind < _WIND_C4_MIN:
        return "C3"
    if wind < _WIND_C4_ST_MIN:
        return "C4"
    if wind < _WIND_C5_MIN:
        return "C4-ST"
    return "C5"


def darken_color(c: Tuple[int, ...], factor: float = 0.6) -> Tuple[int, ...]:
    r, g, b = c[:3]
    a = c[3] if len(c) == 4 else 255
    return (int(r * factor), int(g * factor), int(b * factor), a) if len(c) == 4 else \
           (int(r * factor), int(g * factor), int(b * factor))


def lighten_color(c: Tuple[int, ...], factor: float = 1.2) -> Tuple[int, ...]:
    r, g, b = c[:3]
    a = c[3] if len(c) == 4 else 255
    return (min(255, int(r * factor)), min(255, int(g * factor)),
            min(255, int(b * factor)), a) if len(c) == 4 else \
           (min(255, int(r * factor)), min(255, int(g * factor)), min(255, int(b * factor)))


# ── 经纬度工具：NSEW 格式显示 / 解析 ──

def lon_to_display(val: float) -> str:
    if abs(val - 180.0) < 0.001:
        return "180.0"
    if abs(val) < 0.001:
        return "0.0"
    if val > 180.0:
        return f"{360.0 - val:.1f}W"
    return f"{val:.1f}E"


def lat_to_display(val: float) -> str:
    if abs(val) < 0.001:
        return "0.0"
    if val > 0:
        return f"{val:.1f}N"
    return f"{-val:.1f}S"


def parse_lon(text: str) -> float:
    text = text.strip().upper()
    if not text:
        return 0.0
    if text.endswith('W'):
        return 360.0 - float(text[:-1])
    if text.endswith('E'):
        return float(text[:-1])
    return float(text)


def parse_lat(text: str) -> float:
    text = text.strip().upper()
    if not text:
        return 0.0
    if text.endswith('S'):
        return -float(text[:-1])
    if text.endswith('N'):
        return float(text[:-1])
    return float(text)
