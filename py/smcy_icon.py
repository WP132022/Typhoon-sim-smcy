"""SMCY 视频台风图标系统（流式按需加载 + 小窗口帧缓存）。"""
from __future__ import annotations

import os
import logging
from collections import OrderedDict
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import pygame

from .constants import (
    SUCAI_DIR, ICON_SET_SMCY,
    HEMISPHERE_NORTH, HEMISPHERE_SOUTH,
)

logger = logging.getLogger(__name__)

_TC_CATEGORIES = {
    'C1': 'TC-C1', 'C2': 'TC-C2', 'C2-': 'TC-C2-', 'C3': 'TC-C3',
    'C3-': 'TC-C3-', 'C4': 'TC-C4', 'C4-ST': 'TC-C4+', 'C5': 'TC-C5',
    'TS': 'TC-TS', 'STS': 'TC-TS+', 'TD': 'TD-D',
}

_EX_CATEGORIES = {
    'EX': 'EX-EX', 'SD': 'EX-SD', 'SS': 'EX-SS',
}

_DB_CATEGORIES = {
    'DB': 'DB-DB', 'LO': 'DB-LO', 'MD': 'DB-MD', 'WV': 'DB-WV',
}

_FPS = 60.0
_TOTAL_FRAMES = 1800
_FRAME_INTERVAL_MS = int(1000.0 / _FPS)

_VIDEO_EXT = '.mp4'
_CACHE_MAX = 120
_SMCY_SPEED = 1.0
_MAX_STREAMS = 8


def _is_ex_category(cat: str) -> bool:
    return cat == 'EX'


def _frame_to_surface(frame_bgr: np.ndarray) -> pygame.Surface:
    """BGR 帧转 BGRA Surface，alpha = max(R,G,B)。numpy 加速版。"""
    alpha = frame_bgr.max(axis=2).astype(np.uint8)
    frame_bgra = np.dstack([frame_bgr, alpha])
    return pygame.image.frombuffer(frame_bgra.tobytes(), frame_bgra.shape[1::-1], 'BGRA')


class _VideoStream:
    """单个视频的流式读取 + OrderedDict 帧缓存（O(1) 驱逐）。"""

    def __init__(self, path: str) -> None:
        self._cap = cv2.VideoCapture(path)
        self._cache: OrderedDict[int, pygame.Surface] = OrderedDict()
        self._orig_w: int = 0
        self._orig_h: int = 0
        self._frame_count: int = _TOTAL_FRAMES
        self._scale_size: Optional[Tuple[int, int]] = None
        self._last_pos: Optional[int] = None
        if self._cap.isOpened():
            self._orig_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._orig_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fc = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if fc > 0:
                self._frame_count = fc

    @property
    def is_open(self) -> bool:
        return self._cap.isOpened()

    @property
    def orig_size(self) -> Tuple[int, int]:
        return (self._orig_w, self._orig_h)

    def set_scale_size(self, size: Tuple[int, int]) -> None:
        if self._scale_size != size:
            self._scale_size = size
            self._cache.clear()
            self._last_pos = None

    def get_frame(self, idx: int, target_size: Optional[Tuple[int, int]] = None) -> Optional[pygame.Surface]:
        idx = idx % self._frame_count
        if target_size and target_size != self._scale_size:
            self._scale_size = target_size
            self._cache.clear()
            self._last_pos = None
        if idx in self._cache:
            self._cache.move_to_end(idx)
            return self._cache[idx]

        if self._last_pos is not None and self._last_pos < idx and idx - self._last_pos <= 30:
            skip = idx - self._last_pos - 1
            for _ in range(skip):
                self._cap.grab()
            ret, frame_bgr = self._cap.read()
        else:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame_bgr = self._cap.read()

        self._last_pos = idx

        if not ret:
            return None
        if self._scale_size:
            frame_bgr = cv2.resize(frame_bgr, self._scale_size, interpolation=cv2.INTER_LINEAR)
        surf = _frame_to_surface(frame_bgr)
        self._cache[idx] = surf
        if len(self._cache) > _CACHE_MAX:
            self._cache.popitem(last=False)
        return surf

    def preload_window(self, start_idx: int, count: int = 30) -> None:
        """预加载 [start_idx, start_idx+count) 帧到缓存，避免后续 seek 卡顿。"""
        for i in range(start_idx, min(start_idx + count, self._frame_count)):
            self.get_frame(i)

    def release(self) -> None:
        self._cap.release()
        self._cache.clear()
        self._last_pos = None


class SMCYIconManager:
    """管理 SMCY 视频台风图标的流式加载与帧播放。"""

    def __init__(self) -> None:
        self._base_dir = os.path.join(SUCAI_DIR, ICON_SET_SMCY, 'mainicon')
        self._streams: Dict[str, _VideoStream] = {}
        self._sizes: Dict[str, Tuple[int, int]] = {}
        self._icon_size_cache: int = 0
        self._ex_icon_size_cache: int = 0
        self._access_order: list = []

    # ── 公开接口 ──

    def get_frame(self, category: str, hemisphere: str, frame_idx: int,
                  target_size: Optional[Tuple[int, int]] = None) -> Optional[pygame.Surface]:
        key = self._make_key(category, hemisphere)
        stream = self._streams.get(key)
        if stream is None:
            stream = self._open(category, hemisphere)
        if stream is None:
            return None
        self._touch(key)
        return stream.get_frame(frame_idx, target_size)

    def get_size(self, category: str, hemisphere: str) -> Optional[Tuple[int, int]]:
        key = self._make_key(category, hemisphere)
        if key in self._sizes:
            return self._sizes[key]
        stream = self._streams.get(key)
        if stream is None:
            stream = self._open(category, hemisphere)
        if stream is None:
            return None
        return self._sizes.get(key)

    def preload_frame_window(self, category: str, hemisphere: str,
                              frame_idx: int, count: int = 30) -> None:
        key = self._make_key(category, hemisphere)
        stream = self._streams.get(key)
        if stream is None:
            stream = self._open(category, hemisphere)
        if stream is not None:
            self._touch(key)
            stream.preload_window(frame_idx, count)

    def unload_unused(self, active_keys: set) -> None:
        for key in list(self._streams.keys()):
            if key not in active_keys:
                self._streams[key].release()
                del self._streams[key]
                if key in self._access_order:
                    self._access_order.remove(key)

    def set_icon_size(self, size: int, ex_size: int = 0) -> None:
        if self._icon_size_cache == size and self._ex_icon_size_cache == ex_size:
            return
        self._icon_size_cache = size
        self._ex_icon_size_cache = ex_size
        for key, stream in self._streams.items():
            cat = key.split(':', 1)[1] if ':' in key else ''
            if _is_ex_category(cat) and ex_size:
                ow, oh = stream.orig_size
                if ow <= 0 or oh <= 0:
                    stream.set_scale_size((size, size))
                    continue
                scale = min(ex_size / ow, ex_size / oh)
                stream.set_scale_size((max(1, int(ow * scale)), max(1, int(oh * scale))))
            else:
                stream.set_scale_size((size, size))

    # ── 内部方法 ──

    @staticmethod
    def _make_key(category: str, hemisphere: str) -> str:
        hemi = 'N' if hemisphere == HEMISPHERE_NORTH else 'S'
        return f"{hemi}:{category}"

    def _touch(self, key: str) -> None:
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def _evict_lru(self) -> None:
        while len(self._streams) > _MAX_STREAMS and self._access_order:
            oldest = self._access_order.pop(0)
            if oldest in self._streams:
                self._streams[oldest].release()
                del self._streams[oldest]
                logger.debug(f"SMCY: LRU 回收 {oldest}")

    def _get_file_name(self, category: str) -> Optional[str]:
        if category in _TC_CATEGORIES:
            return 'tc/' + _TC_CATEGORIES[category] + _VIDEO_EXT
        if category in _EX_CATEGORIES:
            return 'ex/' + _EX_CATEGORIES[category] + _VIDEO_EXT
        if category in _DB_CATEGORIES:
            return 'db/' + _DB_CATEGORIES[category] + _VIDEO_EXT
        return None

    def _open(self, category: str, hemisphere: str) -> Optional[_VideoStream]:
        file_name = self._get_file_name(category)
        if file_name is None:
            logger.warning(f"SMCY: 未找到类别映射 {category}")
            return None

        hemi_prefix = 'N' if hemisphere == HEMISPHERE_NORTH else 'S'
        parts = file_name.split('/')
        if len(parts) != 2:
            return None
        subdir, base = parts
        video_name = f"{hemi_prefix}-{base.replace(_VIDEO_EXT, '')}{_VIDEO_EXT}"
        video_path = os.path.join(self._base_dir, subdir, video_name)

        if not os.path.exists(video_path):
            logger.warning(f"SMCY: 视频文件不存在 {video_path}")
            return None

        stream = _VideoStream(video_path)
        if not stream.is_open:
            logger.warning(f"SMCY: 无法打开视频 {video_path}")
            return None

        if self._icon_size_cache > 0:
            if _is_ex_category(category) and self._ex_icon_size_cache > 0:
                ow, oh = stream.orig_size
                if ow <= 0 or oh <= 0:
                    stream.set_scale_size((self._icon_size_cache, self._icon_size_cache))
                else:
                    scale = min(self._ex_icon_size_cache / ow, self._ex_icon_size_cache / oh)
                    stream.set_scale_size((max(1, int(ow * scale)), max(1, int(oh * scale))))
            else:
                stream.set_scale_size((self._icon_size_cache, self._icon_size_cache))

        key = self._make_key(category, hemisphere)
        self._streams[key] = stream
        self._sizes[key] = stream.orig_size
        self._evict_lru()

        logger.info(f"SMCY: 打开 {video_name} ({stream.orig_size[0]}x{stream.orig_size[1]})")
        return stream


# ── 登陆特效 ──

_LANDFALL_MAP = {
    'C1': '[Landing]C1', 'C2': '[Landing]C2', 'C2-': '[Landing]C2',
    'C3': '[Landing]C3', 'C3-': '[Landing]C3',
    'C4': '[Landing]C4', 'C4-ST': '[Landing]C4',
    'C5': '[Landing]C5',
    'TS': '[Landing]S', 'STS': '[Landing]S', 'SS': '[Landing]S',
    'TD': '[Landing]D', 'SD': '[Landing]D',
    'MD': '[Landing]MD',
}

_landfall_cache: Dict[Tuple[str, int, int], list] = {}


def get_landfall_frames(category: str, target_w: int = 0, target_h: int = 0) -> Optional[list]:
    """获取登陆特效的全部帧，加载时预缩放到目标尺寸，按尺寸缓存。"""
    name = _LANDFALL_MAP.get(category)
    if name is None:
        return None
    cache_key = (name, target_w, target_h)
    if cache_key in _landfall_cache:
        return _landfall_cache[cache_key]
    path = os.path.join(SUCAI_DIR, ICON_SET_SMCY, 'landfall', f'{name}.mp4')
    if not os.path.exists(path):
        return None
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    frames = []
    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break
        if target_w > 0 and target_h > 0:
            frame_bgr = cv2.resize(frame_bgr, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        frames.append(_frame_to_surface(frame_bgr))
    cap.release()
    _landfall_cache[cache_key] = frames
    logger.info(f"SMCY 登陆特效: 加载 {name}.mp4 ({len(frames)} 帧, {target_w}x{target_h})")
    return frames


# ── 摘要视频 ──

_SUMMARY_DIR = os.path.join(SUCAI_DIR, ICON_SET_SMCY, 'summary')

_SUMMARY_CATS = {
    'TD': 'TD', 'TS': 'TS', 'STS': 'TS+', 'C1': 'C1', 'C2': 'C2',
    'C2-': 'C2-', 'C3': 'C3', 'C3-': 'C3-', 'C4': 'C4', 'C4-ST': 'C4+',
    'C5': 'C5', 'SS': 'SS',
}

_summary_streams: Dict[str, _VideoStream] = {}
_summary_access: list = []
_MAX_SUMMARY_STREAMS = 10


def _summary_video_path(cat: str, hemi: str) -> Optional[str]:
    name = _SUMMARY_CATS.get(cat)
    if name is None:
        return None
    path = os.path.join(_SUMMARY_DIR, f"Summary-{hemi}-TC-{name}.mp4")
    if os.path.exists(path):
        return path
    if cat == 'SS':
        path = os.path.join(_SUMMARY_DIR, f"Summary-{hemi}-EX-{name}.mp4")
        if os.path.exists(path):
            return path
    return None


def has_summary_video(cat: str, hemi: str) -> bool:
    """该等级/半球是否存在对应的摘要视频。"""
    return _summary_video_path(cat, hemi) is not None


def get_summary_frame(cat: str, hemi: str, idx: int,
                      target_size: Optional[Tuple[int, int]] = None) -> Optional[pygame.Surface]:
    """获取摘要视频的指定帧（流式读取 + 缓存，按宽高比缩放）。"""
    global _summary_streams, _summary_access
    path = _summary_video_path(cat, hemi)
    if path is None:
        return None
    key = f"{hemi}:{cat}"
    if key not in _summary_streams:
        stream = _VideoStream(path)
        if not stream.is_open:
            return None
        _summary_streams[key] = stream
        while len(_summary_streams) > _MAX_SUMMARY_STREAMS and _summary_access:
            oldest = _summary_access.pop(0)
            if oldest in _summary_streams:
                _summary_streams[oldest].release()
                del _summary_streams[oldest]
    if key in _summary_access:
        _summary_access.remove(key)
    _summary_access.append(key)
    return _summary_streams[key].get_frame(idx, target_size)


def set_summary_scale(w: int, h: int) -> None:
    """设置摘要视频的预缩放尺寸（2/5 原大小）。"""
    size = (w, h)
    for stream in _summary_streams.values():
        stream.set_scale_size(size)


_smcy_manager: Optional[SMCYIconManager] = None


def get_smcy_manager() -> SMCYIconManager:
    global _smcy_manager
    if _smcy_manager is None:
        _smcy_manager = SMCYIconManager()
    return _smcy_manager


def clear_smcy_cache() -> None:
    global _smcy_manager
    if _smcy_manager is not None:
        for stream in _smcy_manager._streams.values():
            stream.release()
    _smcy_manager = None
