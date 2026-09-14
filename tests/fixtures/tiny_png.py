"""matplotlib 없이 차트 자리를 채우기 위한 최소 PNG.

3단계 차트 캐시(session_state["charts"])를 시드해 AppTest 가
실제 렌더(수 초)를 건너뛰게 하거나, report_builder 에 유효한
이미지를 넣을 때 사용한다.
"""

from __future__ import annotations

import base64
from io import BytesIO

# 1x1 투명 PNG
TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)

# report_builder 가 Word 에 넣을 때 세로/가로 크기가 0 이면 곤란하므로
# 10x10 회색 PNG 도 준비한다.
SMALL_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAFUlEQVR4nGNsaGhgwA2Y8MgxjFxpANthAZRjoXkSAAAAAElFTkSuQmCC"
)

CHART_KEYS = ("trend", "bar", "avg", "rank", "compare")


def tiny_png_buf() -> BytesIO:
    """새 BytesIO 로 감싼 1x1 PNG (seek 위치 0)."""
    buf = BytesIO(TINY_PNG_BYTES)
    buf.seek(0)
    return buf


def small_png_buf() -> BytesIO:
    """새 BytesIO 로 감싼 10x10 PNG (seek 위치 0)."""
    buf = BytesIO(SMALL_PNG_BYTES)
    buf.seek(0)
    return buf


def fake_charts() -> dict:
    """build_report / session_state 용 charts 5종 (모두 유효 PNG)."""
    return {key: small_png_buf() for key in CHART_KEYS}
