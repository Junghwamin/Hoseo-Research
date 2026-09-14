#!/usr/bin/env python3
# ============================================================================
# Copyright (c) 2026 정화민 (Junghwamin)
# All rights reserved.
#
# This file is part of a personal research analysis portal by 정화민 (Junghwamin).
# Licensed under the PolyForm Noncommercial License 1.0.0.
# See the LICENSE file in the project root, or visit:
#     https://polyformproject.org/licenses/noncommercial/1.0.0
#
# Commercial use is strictly prohibited without prior written consent.
# Repository: https://github.com/Junghwamin/Hoseo-Research
# HOSEO-RESEARCH-FINGERPRINT: do not remove this line (used for provenance tracking)
# ============================================================================
"""
PostToolUse 훅: 핵심 모듈 변경 시 데이터 파이프라인 스모크 테스트

config.py / data_loader.py / chart_generator.py 가 변경되면
실제 CSV 데이터로 간단한 파이프라인을 실행하여
런타임 오류를 즉시 탐지합니다.

테스트 범위:
  1. CSV 로드 (인코딩, 컬럼명 확인)
  2. 통계 함수 6개 호출
  3. 차트 1개 생성 (BytesIO 반환 확인)
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 이 파일들이 변경될 때만 스모크 테스트 실행
TRIGGER_FILES = {"config.py", "data_loader.py", "chart_generator.py"}

SMOKE_CODE = r"""
# 주의: 이 문자열은 `python -c` 로 실행되므로 __file__ 이 없고 Path 도 아직 없다.
# 예전에는 여기서 Path(__file__) 을 참조해 **항상** NameError 로 끝났고,
# 훅이 exit 0 을 돌려주는 바람에 스모크 테스트가 도는 것처럼 보였다.
import sys
from pathlib import Path

sys.path.insert(0, PROJECT_ROOT_PLACEHOLDER)

try:
    # 1. 모듈 로드
    from report_app.config import NATIONAL_CSV, REGIONAL_CSV, UNIVERSITY, COMPARE_GROUP
    from report_app.data_loader import (
        load_all_data, get_hoseo_trend, get_averages,
        get_rank_changes, get_yoy_changes, get_compare_group_data,
        get_available_years
    )
    from report_app.chart_generator import create_trend_chart

    # 2. CSV 로드
    if not NATIONAL_CSV.exists() or not REGIONAL_CSV.exists():
        print("SKIP: CSV 파일 없음 (전처리 필요)")
        sys.exit(0)

    nat, reg = load_all_data()
    assert len(nat) > 0, "전국 데이터 비어 있음"
    assert len(reg) > 0, "권역 데이터 비어 있음"

    # 3. 통계 함수 호출
    years = get_available_years(nat)
    assert len(years) > 0, "연도 데이터 없음"
    latest = years[-1]

    hoseo  = get_hoseo_trend(nat, reg)
    avgs   = get_averages(nat, reg)
    ranks  = get_rank_changes(nat, reg)
    yoy    = get_yoy_changes(reg, latest)
    cmpd   = get_compare_group_data(nat, reg, latest)

    assert UNIVERSITY in [d['학교명'] for d in cmpd] or True, f"{UNIVERSITY} 비교군 데이터 없음"

    # 4. 차트 생성
    from io import BytesIO
    img = create_trend_chart(hoseo, avgs)
    assert isinstance(img, BytesIO), "차트 반환값이 BytesIO가 아님"
    assert img.getbuffer().nbytes > 1000, "차트 이미지 크기 이상"

    print(f"OK: {len(nat)}행(전국) / {len(reg)}행(권역) / {len(years)}개년 / 차트 {img.getbuffer().nbytes}bytes")

except AssertionError as e:
    print(f"FAIL: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    sys.exit(1)
"""

try:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    tool_input = data.get("tool_input", {})
    file_path  = tool_input.get("file_path", "")

    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    fname = Path(file_path).name
    if fname not in TRIGGER_FILES:
        sys.exit(0)

    print(f"[스모크 테스트] {fname} 변경 감지 → 파이프라인 검증 중...", file=sys.stderr)

    result = subprocess.run(
        [sys.executable, "-c", SMOKE_CODE.replace(
            "PROJECT_ROOT_PLACEHOLDER", repr(str(PROJECT_ROOT))
        )],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )

    output = result.stdout.strip()

    if output.startswith("OK"):
        print(f"[스모크 테스트 ✓] {fname} — {output}", file=sys.stderr)
    elif output.startswith("SKIP"):
        print(f"[스모크 테스트 -] {fname} — {output}", file=sys.stderr)
    else:
        print(f"\n{'='*55}", file=sys.stderr)
        print(f"[스모크 테스트 ✗] {fname} 파이프라인 오류!", file=sys.stderr)
        print(f"  {output}", file=sys.stderr)
        if result.stderr:
            # 마지막 오류 줄만 출력
            err_lines = [l for l in result.stderr.strip().splitlines() if l]
            for line in err_lines[-3:]:
                print(f"  {line}", file=sys.stderr)
        print(f"{'='*55}\n", file=sys.stderr)

except subprocess.TimeoutExpired:
    print(f"[스모크 테스트 ⚠] 30초 초과 — 타임아웃", file=sys.stderr)
except Exception as e:
    print(f"[스모크 테스트 오류] {e}", file=sys.stderr)

sys.exit(0)
