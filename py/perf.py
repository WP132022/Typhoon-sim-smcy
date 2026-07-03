"""帧性能分析：对关键路径计时，每 60 帧输出一次汇总。"""
from __future__ import annotations

import time
from collections import defaultdict

_FRAME = 0
_ACC: defaultdict = defaultdict(float)
_COUNT: defaultdict = defaultdict(int)
_FRAME_START = time.perf_counter()


def reset_frame():
    global _FRAME_START
    _FRAME_START = time.perf_counter()


def tick(name: str):
    global _FRAME_START
    now = time.perf_counter()
    _ACC[name] += (now - _FRAME_START) * 1000.0
    _COUNT[name] += 1
    _FRAME_START = now


def end_frame():
    global _FRAME
    _FRAME += 1
    if _FRAME % 60 == 0:
        _print_report()
        _ACC.clear()
        _COUNT.clear()
    reset_frame()


def _print_report():
    items = sorted(_ACC.items(), key=lambda x: -x[1])
    total_ms = sum(v for _, v in items)
    print(f"\n[perf] frame {_FRAME} ({total_ms:.1f}ms total):")
    for name, ms in items:
        cnt = _COUNT[name]
        pct = ms / total_ms * 100 if total_ms > 0 else 0
        avg = ms / cnt if cnt > 0 else 0
        print(f"  {name:30s} {ms:8.1f}ms ({pct:5.1f}%)  calls={cnt:4d}  avg={avg:.2f}ms")
