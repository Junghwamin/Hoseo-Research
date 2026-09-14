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
데이터 로드 및 통계 계산 모듈

권역별_순위.csv (또는 레거시 충청권_순위.csv) 및 전체_대학_데이터.csv를 읽어
보고서에 필요한 각종 통계를 산출한다.

새 포맷(권역별_순위.csv)은 모든 권역 데이터를 포함하며,
레거시 포맷(충청권_순위.csv)은 자동 변환하여 하위 호환을 유지한다.
"""

from __future__ import annotations

import math

import pandas as pd

from report_app.config import (
    COMPARE_GROUP,
    NATIONAL_CSV,
    REGIONAL_CSV,
    REGIONAL_CSV_LEGACY,
    UNIVERSITY,
)


# ---------------------------------------------------------------------------
# 1. 기본 로드
# ---------------------------------------------------------------------------

def load_all_data(
    national_df: pd.DataFrame | None = None,
    regional_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    CSV를 읽어 (national_df, regional_df)를 반환한다.

    우선순위: 권역별_순위.csv (새 포맷) > 충청권_순위.csv (레거시)
    레거시 CSV를 읽으면 자동으로 컬럼명을 변환한다:
        충청권순위 → 권역순위, 권역명='충청권' 추가

    Args:
        national_df: 직접 전달 시 파일 읽기 생략
        regional_df: 직접 전달 시 파일 읽기 생략

    Returns:
        (national_df, regional_df) 튜플
    """
    if national_df is None:
        national_df = pd.read_csv(NATIONAL_CSV, encoding="utf-8-sig")
    if regional_df is None:
        if REGIONAL_CSV.exists():
            regional_df = pd.read_csv(REGIONAL_CSV, encoding="utf-8-sig")
        elif REGIONAL_CSV_LEGACY.exists():
            regional_df = pd.read_csv(REGIONAL_CSV_LEGACY, encoding="utf-8-sig")
        else:
            raise FileNotFoundError(
                f"권역 데이터 파일을 찾을 수 없습니다: "
                f"{REGIONAL_CSV} 또는 {REGIONAL_CSV_LEGACY}"
            )

    # 레거시 포맷 자동 변환
    regional_df = _ensure_new_format(regional_df)

    return national_df, regional_df


def _ensure_new_format(regional_df: pd.DataFrame) -> pd.DataFrame:
    """레거시 CSV 포맷(충청권순위)을 새 포맷(권역순위+권역명)으로 변환한다."""
    if "충청권순위" in regional_df.columns and "권역순위" not in regional_df.columns:
        regional_df = regional_df.rename(columns={"충청권순위": "권역순위"})
        regional_df["권역명"] = "충청권"
    return regional_df


# ---------------------------------------------------------------------------
# 2. 권역 감지 유틸리티
# ---------------------------------------------------------------------------

def detect_region(university: str, regional_df: pd.DataFrame) -> list[str]:
    """대학이 속한 권역명 목록을 반환한다.

    다중 캠퍼스 대학은 여러 권역에 속할 수 있다.

    Args:
        university: 대학명
        regional_df: 권역별 데이터 (권역명 컬럼 필요)

    Returns:
        권역명 리스트 (예: ["수도권", "충청권"]) 또는 빈 리스트
    """
    if "권역명" not in regional_df.columns:
        return []
    matches = regional_df[regional_df["학교명"] == university]["권역명"].unique().tolist()
    return sorted(matches)


def get_region_universities(
    regional_df: pd.DataFrame,
    region_name: str,
    year: int | None = None,
) -> list[str]:
    """특정 권역의 대학 목록을 반환한다."""
    mask = regional_df["권역명"] == region_name
    if year is not None:
        mask = mask & (regional_df["연도"] == year)
    return sorted(regional_df[mask]["학교명"].unique().tolist())


# ---------------------------------------------------------------------------
# 3. 대상 대학 연도별 추이
# ---------------------------------------------------------------------------

def get_hoseo_trend(
    national_df: pd.DataFrame,
    regional_df: pd.DataFrame,
    university: str | None = None,
    region_name: str | None = None,
) -> dict[int, dict]:
    """
    대상 대학의 연도별 핵심 수치를 반환한다.

    Args:
        national_df: 전국 대학 데이터
        regional_df: 권역별 대학 데이터
        university: 분석 대상 대학명
        region_name: 특정 권역으로 필터링. None이면 대학이 속한 첫 번째 권역 사용.

    Returns:
        {연도: {"논문수", "전임교원수", "1인당논문수", "권역순위", "전국순위"}, ...}
    """
    univ = university or UNIVERSITY
    result: dict[int, dict] = {}

    national_hoseo = national_df[national_df["학교명"] == univ].copy()

    # 권역 필터링
    reg_filtered = regional_df[regional_df["학교명"] == univ].copy()
    if region_name and "권역명" in reg_filtered.columns:
        reg_filtered = reg_filtered[reg_filtered["권역명"] == region_name]

    for _, row in national_hoseo.iterrows():
        year = int(row["연도"])
        result[year] = {
            "논문수": round(float(row["SCI/SCOPUS논문수"]), 2),
            "전임교원수": int(row["전임교원수"]),
            "1인당논문수": round(float(row["1인당논문수"]), 4),
            "권역순위": None,
            "전국순위": int(row["전국순위"]),
        }

    for _, row in reg_filtered.iterrows():
        year = int(row["연도"])
        if year in result:
            result[year]["권역순위"] = int(row["권역순위"])

    return dict(sorted(result.items()))


# ---------------------------------------------------------------------------
# 4. 전국 / 권역 / 비교군 평균
# ---------------------------------------------------------------------------

def get_averages(
    national_df: pd.DataFrame,
    regional_df: pd.DataFrame,
    compare_group: list[str] | None = None,
    region_name: str | None = None,
) -> dict[int, dict]:
    """
    연도별 전국/권역/비교군 1인당논문수 평균을 반환한다.

    Args:
        national_df: 전국 대학 데이터
        regional_df: 권역별 대학 데이터
        compare_group: 비교 대학 목록
        region_name: 권역 필터 (None이면 전체 regional_df 사용)

    Returns:
        {연도: {"전국평균", "권역평균", "비교군평균"}, ...}
    """
    cmp = compare_group if compare_group is not None else COMPARE_GROUP
    result: dict[int, dict] = {}
    years = sorted(national_df["연도"].unique())

    # 권역 필터링
    reg_data = regional_df
    if region_name and "권역명" in regional_df.columns:
        reg_data = regional_df[regional_df["권역명"] == region_name]

    for year in years:
        nat_year = national_df[national_df["연도"] == year]
        reg_year = reg_data[reg_data["연도"] == year]
        cmp_year = national_df[
            (national_df["연도"] == year) & (national_df["학교명"].isin(cmp))
        ]

        result[int(year)] = {
            "전국평균": round(float(nat_year["1인당논문수"].mean()), 4),
            "권역평균": round(float(reg_year["1인당논문수"].mean()), 4) if len(reg_year) > 0 else 0.0,
            "비교군평균": round(float(cmp_year["1인당논문수"].mean()), 4) if len(cmp_year) > 0 else 0.0,
        }

    return result


# ---------------------------------------------------------------------------
# 5. 권역·전국 순위 변화
# ---------------------------------------------------------------------------

def get_rank_changes(
    national_df: pd.DataFrame,
    regional_df: pd.DataFrame,
    university: str | None = None,
    region_name: str | None = None,
) -> dict[int, dict]:
    """
    대상 대학의 연도별 권역·전국 순위 및 전년대비 변화를 반환한다.

    부호 규약(중요):
        변화량 = 이전순위 - 현재순위
        → **양수 = 순위 개선**(예: 7위에서 5위로 오르면 +2)
        → **음수 = 순위 하락**, 0 = 동일, None = 비교할 이전 연도가 없음
        화면·보고서에서 이 값을 다시 뒤집지 말 것.

    Returns:
        {연도: {"권역순위", "전국순위", "권역순위_변화", "전국순위_변화"}, ...}
    """
    univ = university or UNIVERSITY
    hoseo_nat = national_df[national_df["학교명"] == univ].sort_values("연도")

    reg_filtered = regional_df[regional_df["학교명"] == univ]
    if region_name and "권역명" in regional_df.columns:
        reg_filtered = reg_filtered[reg_filtered["권역명"] == region_name]
    hoseo_reg = reg_filtered.sort_values("연도")

    result: dict[int, dict] = {}
    prev_nat_rank: int | None = None
    prev_reg_rank: int | None = None

    nat_by_year = {int(r["연도"]): int(r["전국순위"]) for _, r in hoseo_nat.iterrows()}
    reg_by_year = {int(r["연도"]): int(r["권역순위"]) for _, r in hoseo_reg.iterrows()}

    for year in sorted(nat_by_year.keys()):
        nat_rank = nat_by_year.get(year)
        reg_rank = reg_by_year.get(year)

        nat_change = (prev_nat_rank - nat_rank) if (prev_nat_rank is not None and nat_rank is not None) else None
        reg_change = (prev_reg_rank - reg_rank) if (prev_reg_rank is not None and reg_rank is not None) else None

        result[year] = {
            "권역순위": reg_rank,
            "전국순위": nat_rank,
            "권역순위_변화": reg_change,
            "전국순위_변화": nat_change,
        }

        prev_nat_rank = nat_rank
        prev_reg_rank = reg_rank

    return result


# ---------------------------------------------------------------------------
# 6. 전년대비 증감률 상위·하위 대학 (권역 기준)
# ---------------------------------------------------------------------------

def _yoy_rate(current: float, previous: float) -> float | None:
    """전년대비 증감률(%)을 계산한다.

    이전값이 0 이면 증감률을 정의할 수 없으므로 두 경우를 구분한다:
        - 이전 0 · 현재 > 0  → None ('신규' 실적. 무변화와 혼동되면 안 된다)
        - 이전 0 · 현재 = 0  → 0.0 (무실적 유지)

    **NaN 은 절대 반환하지 않는다.** 소비처의 가드가 `is None` 으로만 걸러지므로
    NaN 이 새어 나가면 f"{v:+.1f}%" 가 예외 없이 '+nan%' 로 조용히 렌더된다.
    결측·비정상 입력(업로드 CSV 에 NaN/inf 가 섞인 경우)도 None 으로 모은다.
    """
    if not (math.isfinite(current) and math.isfinite(previous)):
        return None
    if previous > 0:
        rate = round((current - previous) / previous * 100, 1)
        return rate if math.isfinite(rate) else None
    return None if current > 0 else 0.0


def _yoy_sort_key(rate: float | None) -> float:
    """정렬용 키. 신규 실적(None)은 최대 증가로 보아 맨 앞에 둔다."""
    return float("inf") if rate is None else rate


def get_yoy_changes(
    regional_df: pd.DataFrame,
    year: int,
    university: str | None = None,
    region_name: str | None = None,
) -> dict:
    """
    권역 내 대학의 전년대비 1인당논문수 증감률을 계산하여
    증가 상위 / 감소 하위 대학을 반환한다.

    상위·하위는 **서로 겹치지 않는다**. 대상 대학 수가 적으면 개수를 줄여
    나눠 갖는다(상위 최대 3 = min(3, (n+1)//2), 하위 = min(3, n - 상위 수)).
    따라서 1개교뿐인 권역은 상위 1 / 하위 0 이 된다.

    다중 캠퍼스로 2개 권역에 등재된 대학은 (학교명, 권역명) 기준으로 합친 뒤
    학교명 기준으로 한 번만 남긴다(region_name=None 이어도 중복 등장하지 않는다).

    증감률 타입 계약 (float | None 뿐이며 **NaN 은 반환하지 않는다**):
        float  — 이전값 > 0 인 일반적인 경우 (소수 첫째 자리 반올림)
        0.0    — 이전 0 · 현재 0 (무실적 유지)
        None   — 이전 0 · 현재 > 0 (**신규 실적**) 또는 값이 결측이라
                 증감률을 정의할 수 없는 경우. 소비처는 '신규' 등으로
                 표기해야 하며 그대로 숫자 포맷(f"{v:+.1f}%")에 넣으면 안 된다.
                 NaN 을 내보내면 소비처의 `is None` 가드를 통과해
                 '+nan%' 로 조용히 렌더되므로 None 으로만 신호한다.

    Returns:
        {"상위": [...], "하위": [...], "호서": {...} | None}
        각 원소 키: {"학교명", "증감률", "기준연도"(현재값), "비교연도"(이전값)}
    """
    univ = university or UNIVERSITY
    prev_year = year - 1

    # 권역 필터링
    reg_data = regional_df
    if region_name and "권역명" in regional_df.columns:
        reg_data = regional_df[regional_df["권역명"] == region_name]

    # 다중권역 대학이 cross-product 로 불어나지 않도록 권역명까지 병합 키로 쓴다.
    merge_keys = ["학교명"]
    if "권역명" in reg_data.columns:
        merge_keys.append("권역명")
    cols = merge_keys + ["1인당논문수"]

    cur = reg_data[reg_data["연도"] == year][cols].copy()
    prv = reg_data[reg_data["연도"] == prev_year][cols].copy()

    if cur.empty or prv.empty:
        return {"상위": [], "하위": [], "호서": None}

    merged = cur.merge(prv, on=merge_keys, suffixes=("_현재", "_이전"))
    # 권역마다 한 행씩 남은 다중권역 대학을 학교명 기준 1행으로 줄인다.
    merged = merged.drop_duplicates(subset=["학교명"], keep="first")

    rows: list[dict] = []
    for _, r in merged.iterrows():
        current = float(r["1인당논문수_현재"])
        previous = float(r["1인당논문수_이전"])
        rows.append({
            "학교명": r["학교명"],
            "증감률": _yoy_rate(current, previous),
            "기준연도": round(current, 4),
            "비교연도": round(previous, 4),
        })

    rows.sort(key=lambda row: _yoy_sort_key(row["증감률"]), reverse=True)

    # 상위·하위가 같은 대학을 공유하지 않도록 겹치지 않게 잘라 쓴다.
    top_n = min(3, (len(rows) + 1) // 2)
    bottom_n = min(3, len(rows) - top_n)
    top = [dict(row) for row in rows[:top_n]]
    bottom = [dict(row) for row in rows[len(rows) - bottom_n:]] if bottom_n else []

    hoseo = next((dict(row) for row in rows if row["학교명"] == univ), None)

    return {"상위": top, "하위": bottom, "호서": hoseo}


# ---------------------------------------------------------------------------
# 7. 비교군 최신 연도 데이터
# ---------------------------------------------------------------------------

def get_compare_group_data(
    national_df: pd.DataFrame,
    regional_df: pd.DataFrame,
    year: int,
    compare_group: list[str] | None = None,
    region_name: str | None = None,
) -> list[dict]:
    """
    비교 대학의 특정 연도 데이터를 반환한다.

    Returns:
        [{"학교명", "전임교원수", "논문수", "1인당논문수", "전국순위", "권역순위"}, ...]
    """
    cmp = compare_group if compare_group is not None else COMPARE_GROUP
    nat_year = national_df[
        (national_df["연도"] == year) & (national_df["학교명"].isin(cmp))
    ]

    reg_filtered = regional_df
    if region_name and "권역명" in regional_df.columns:
        reg_filtered = regional_df[regional_df["권역명"] == region_name]

    reg_year = reg_filtered[
        (reg_filtered["연도"] == year) & (reg_filtered["학교명"].isin(cmp))
    ]

    reg_rank_map = {
        r["학교명"]: int(r["권역순위"])
        for _, r in reg_year.iterrows()
    }

    result = []
    for _, row in nat_year.iterrows():
        name = row["학교명"]
        result.append({
            "학교명": name,
            "전임교원수": int(row["전임교원수"]),
            "논문수": round(float(row["SCI/SCOPUS논문수"]), 2),
            "1인당논문수": round(float(row["1인당논문수"]), 4),
            "전국순위": int(row["전국순위"]),
            "권역순위": reg_rank_map.get(name),
        })

    result.sort(key=lambda x: x["1인당논문수"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# 8. 사용 가능 연도 목록
# ---------------------------------------------------------------------------

def get_available_years(national_df: pd.DataFrame) -> list[int]:
    """CSV에 존재하는 연도 목록을 반환한다."""
    return sorted(national_df["연도"].unique().tolist())
