"""SMCY 视频台风图标系统（流式按需加载 + 小窗口帧缓存）。"""
from __future__ import annotations

import os
import logging
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
_FRAME_INTERVAL_MS = int(500.0 / _FPS)

_VIDEO_EXT = '.mp4'
_CACHE_MAX = 120
_SMCY_SPEED = 2.0


def _frame_to_surface(frame_bgr: np.ndarray) -> pygame.Surface:
    """BGR 帧转 BGRA Surface，alpha = max(R,G,B)。"""
    b, g, r = cv2.split(frame_bgr)
    alpha = cv2.max(cv2.max(r, g), b)
    frame_bgra = cv2.merge([b, g, r, alpha])
    return pygame.image.frombuffer(frame_bgra.tobytes(), frame_bgra.shape[1::-1], 'BGRA')


class _VideoStream:
    """单个视频的流式读取 + 小窗口帧缓存。"""

    def __init__(self, path: str) -> None:
        self._cap = cv2.VideoCapture(path)
        self._cache: Dict[int, pygame.Surface] = {}

    @property
    def is_open(self) -> bool:
        return self._cap.isOpened()

    def get_frame(self, idx: int) -> Optional[pygame.Surface]:
        idx = idx % _TOTAL_FRAMES
        if idx in self._cache:
            return self._cache[idx]
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame_bgr = self._cap.read()
        if not ret:
            return None
        surf = _frame_to_surface(frame_bgr)
        self._cache[idx] = surf
        if len(self._cache) > _CACHE_MAX:
            oldest = min(self._cache.keys())
            del self._cache[oldest]
        return surf

    def release(self) -> None:
        self._cap.release()
        self._cache.clear()


class SMCYIconManager:
    """管理 SMCY 视频台风图标的流式加载与帧播放。"""

    def __init__(self) -> None:
        self._base_dir = os.path.join(SUCAI_DIR, ICON_SET_SMCY, 'mainicon')
        self._streams: Dict[str, _VideoStream] = {}
        self._sizes: Dict[str, Tuple[int, int]] = {}

    # ── 公开接口 ──

    def get_frame(self, category: str, hemisphere: str, frame_idx: int) -> Optional[pygame.Surface]:
        key = self._make_key(category, hemisphere)
        stream = self._streams.get(key)
        if stream is None:
            stream = self._open(category, hemisphere)
        if stream is None:
            return None
        return stream.get_frame(frame_idx)

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

    def unload_unused(self, active_keys: set) -> None:
        """释放不在 active_keys 中的视频流。"""
        for key in list(self._streams.keys()):
            if key not in active_keys:
                self._streams[key].release()
                del self._streams[key]

    # ── 内部方法 ──

    @staticmethod
    def _make_key(category: str, hemisphere: str) -> str:
        hemi = 'N' if hemisphere == HEMISPHERE_NORTH else 'S'
        return f"{hemi}:{category}"

    @staticmethod
    def _hemi_prefix(hemisphere: str) -> str:
        return 'N' if hemisphere == HEMISPHERE_NORTH else 'S'

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

        hemi_prefix = self._hemi_prefix(hemisphere)
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

        key = self._make_key(category, hemisphere)
        self._streams[key] = stream

        cap = stream._cap
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._sizes[key] = (w, h)

        logger.info(f"SMCY: 打开 {video_name} ({w}x{h})")
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

_landfall_cache: Dict[str, list] = {}


def get_landfall_frames(category: str) -> Optional[list]:
    """获取登陆特效的全部帧（60帧，~60MB），缓存后复用。"""
    name = _LANDFALL_MAP.get(category)
    if name is None:
        return None
    if name in _landfall_cache:
        return _landfall_cache[name]
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
        frames.append(_frame_to_surface(frame_bgr))
    cap.release()
    _landfall_cache[name] = frames
    logger.info(f"SMCY 登陆特效: 加载 {name}.mp4 ({len(frames)} 帧)")
    return frames


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
