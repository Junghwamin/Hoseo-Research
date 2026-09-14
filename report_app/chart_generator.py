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
그래프 생성 모듈 (matplotlib)

각 함수는 BytesIO 이미지 객체를 반환한다 (Word 파일 삽입 및 Streamlit 미리보기용).

Note:
    Python 3.13+ 에서 matplotlib 3.8.x의 MarkerStyle deepcopy 재귀 버그가 존재한다.
    이를 우회하기 위해 마커를 fmt 문자열("o-") 대신 keyword(marker="o")로 분리하고,
    set_xticks 호출 전에 마커가 없는 상태로 tick을 설정한다.
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

from report_app.config import COMPARE_GROUP, UNIVERSITY

# 한글 폰트 설정 (OS별 자동 감지)
import platform as _platform
import matplotlib.font_manager as _fm

# Python 3.13+ 에서 matplotlib deepcopy 재귀 버그 방지를 위한 monkey-patch
_PY_VERSION = sys.version_info[:2]
if _PY_VERSION >= (3, 13):
    import copy as _copy
    _orig_deepcopy = _copy.deepcopy
    def _safe_deepcopy(x, memo=None, _nil=[]):
        """deepcopy 재귀 깊이 제한 (matplotlib path 버그 우회)"""
        try:
            return _orig_deepcopy(x, memo)
        except RecursionError:
            return x
    _copy.deepcopy = _safe_deepcopy

def _setup_korean_font():
    """OS별 한글 폰트를 자동 감지하여 설정한다."""
    system = _platform.system()
    if system == "Windows":
        font_name = "Malgun Gothic"
    elif system == "Darwin":  # macOS
        available = {f.name for f in _fm.fontManager.ttflist}
        if "Apple SD Gothic Neo" in available:
            font_name = "Apple SD Gothic Neo"
        else:
            font_name = "AppleGothic"
    else:  # Linux (Streamlit Cloud 포함)
        font_name = "NanumGothic"
        # packages.txt로 설치된 NanumGothic 폰트를 matplotlib에 등록
        _nanum_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        if Path(_nanum_path).exists():
            _fm.fontManager.addfont(_nanum_path)
    matplotlib.rcParams["font.family"] = font_name
    matplotlib.rcParams["axes.unicode_minus"] = False

_setup_korean_font()

# 색상 팔레트
COLOR_HOSEO = "#0A0A0A"      # 호서대 강조 (거의 블랙)
COLOR_OTHERS = "#BDBDBD"     # 기타 연한 그레이
COLOR_NATIONAL = "#555555"   # 전국 다크 그레이
COLOR_REGIONAL = "#888888"   # 권역 미디엄 그레이
COLOR_COMPARE = "#AAAAAA"    # 비교군 라이트 그레이


def _save_fig(fig: plt.Figure) -> BytesIO:
    """Figure를 PNG BytesIO로 저장하고 반환한다."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf


# ---------------------------------------------------------------------------
# 1. 연도별 1인당논문수 추이 라인차트
# ---------------------------------------------------------------------------

def create_trend_chart(
    hoseo_trend: dict[int, dict],
    averages: dict[int, dict],
    university: str | None = None,
    region_name: str = "충청권",
) -> BytesIO:
    """
    호서대 vs 전국·충청권·비교군 평균의 연도별 1인당논문수 추이 라인차트.

    Args:
        hoseo_trend: get_hoseo_trend() 반환값
        averages: get_averages() 반환값
        university: 강조 표시할 대학명. None이면 config.UNIVERSITY 사용
    """
    univ = university or UNIVERSITY
    years = sorted(hoseo_trend.keys())
    hoseo_vals = [hoseo_trend[y]["1인당논문수"] for y in years]
    nat_avg = [averages[y]["전국평균"] for y in years]
    reg_avg = [averages[y]["권역평균"] for y in years]
    cmp_avg = [averages[y]["비교군평균"] for y in years]

    fig, ax = plt.subplots(figsize=(9, 5))

    ax.plot(years, hoseo_vals, linestyle="-", marker="o", color="#0A0A0A",
            linewidth=2.5, markersize=7, markerfacecolor="white", markeredgewidth=2,
            label=univ, zorder=5)
    ax.plot(years, nat_avg, linestyle="--", marker="s", color="#555555",
            linewidth=1.8, markersize=5, markerfacecolor="white", markeredgewidth=1.5,
            label="전국 평균", alpha=0.9)
    ax.plot(years, reg_avg, linestyle=":", marker="^", color="#888888",
            linewidth=1.8, markersize=5, markerfacecolor="white", markeredgewidth=1.5,
            label=f"{region_name} 평균", alpha=0.9)
    ax.plot(years, cmp_avg, linestyle="-.", marker="D", color="#AAAAAA",
            linewidth=1.5, markersize=5, markerfacecolor="white", markeredgewidth=1.5,
            label=f"{univ[:-2]}비교군 평균", alpha=0.9)

    # 데이터 레이블 (호서대만)
    for x, y in zip(years, hoseo_vals):
        ax.annotate(f"{y:.4f}", (x, y), textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=9, color="#0A0A0A", fontweight="bold")

    ax.set_title("전임교원 1인당 SCI/SCOPUS 논문수 연도별 추이", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("연도", fontsize=11)
    ax.set_ylabel("1인당 논문수 (편)", fontsize=11)
    ax.set_xticks(years)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.4f"))
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", linestyle="--", color="#E5E5E5", linewidth=0.8, alpha=1.0)
    ax.set_facecolor("white")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D4D4D8")
    ax.tick_params(colors="#525252")
    fig.patch.set_facecolor("white")
    fig.tight_layout()

    return _save_fig(fig)


# ---------------------------------------------------------------------------
# 2. 충청권 최신연도 막대차트
# ---------------------------------------------------------------------------

def create_comparison_bar(
    regional_df: pd.DataFrame,
    year: int,
    university: str | None = None,
    region_name: str = "충청권",
) -> BytesIO:
    """
    충청권 대학의 1인당논문수 막대차트 (호서대 강조).

    Args:
        regional_df: 충청권_순위.csv 전체 DataFrame
        year: 기준 연도
        university: 강조 표시할 대학명. None이면 config.UNIVERSITY 사용
    """
    univ = university or UNIVERSITY
    df_year = regional_df[regional_df["연도"] == year]
    # 권역명 컴런이 있는 신규 포맷이면 해당 권역으로도 걷러낸다
    # (권역명이 없는 레거시 프레임은 이미 단일 권역이므로 그대로 둔다)
    if region_name and "권역명" in df_year.columns:
        df_year = df_year[df_year["권역명"] == region_name]
    df_year = df_year.sort_values("1인당논문수", ascending=False)

    names = df_year["학교명"].tolist()
    values = df_year["1인당논문수"].tolist()
    colors = [COLOR_HOSEO if n == univ else COLOR_OTHERS for n in names]

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(names, values, color=colors, edgecolor="#3F3F46", linewidth=0.8)

    # 해당 대학 바에만 hatch 패턴 추가
    for bar, name in zip(bars, names):
        if name == univ:
            bar.set_hatch("///")
            bar.set_edgecolor("#0A0A0A")

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.002,
            f"{val:.4f}",
            ha="center", va="bottom", fontsize=8,
        )

    ax.set_title(f"{year}년 {region_name} 대학 전임교원 1인당 SCI/SCOPUS 논문수", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("1인당 논문수 (편)", fontsize=11)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", linestyle="--", color="#E5E5E5", linewidth=0.8, alpha=1.0)
    ax.set_facecolor("white")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D4D4D8")
    ax.tick_params(colors="#525252")
    fig.patch.set_facecolor("white")
    fig.tight_layout()

    return _save_fig(fig)


# ---------------------------------------------------------------------------
# 3. 호서대 vs 전국/충청권/비교군 평균 비교 바차트
# ---------------------------------------------------------------------------

def create_avg_comparison(
    hoseo_trend: dict[int, dict],
    averages: dict[int, dict],
    year: int,
    university: str | None = None,
    region_name: str = "충청권",
) -> BytesIO:
    """
    특정 연도에서 대학 vs 전국/충청권/비교군 평균 수평 바차트.

    Args:
        hoseo_trend: get_hoseo_trend() 반환값
        averages: get_averages() 반환값
        year: 기준 연도
        university: 강조 표시할 대학명. None이면 config.UNIVERSITY 사용
    """
    univ = university or UNIVERSITY
    hoseo_val = hoseo_trend[year]["1인당논문수"]
    nat_val = averages[year]["전국평균"]
    reg_val = averages[year]["권역평균"]
    cmp_val = averages[year]["비교군평균"]

    labels = [univ, "전국 평균", f"{region_name} 평균", "비교군 평균"]
    values = [hoseo_val, nat_val, reg_val, cmp_val]
    colors = [COLOR_HOSEO, COLOR_NATIONAL, COLOR_REGIONAL, COLOR_COMPARE]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.barh(labels, values, color=colors, height=0.5, edgecolor="#3F3F46", linewidth=0.8)

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + 0.001,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.4f}",
            va="center", ha="left", fontsize=10,
        )

    ax.set_title(f"{year}년 1인당 논문수 평균 비교", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("1인당 논문수 (편)", fontsize=11)
    ax.set_xlim(0, max(values) * 1.3)
    ax.grid(axis="x", linestyle="--", color="#E5E5E5", linewidth=0.8, alpha=1.0)
    ax.set_facecolor("white")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D4D4D8")
    ax.tick_params(colors="#525252")
    fig.patch.set_facecolor("white")
    fig.tight_layout()

    return _save_fig(fig)


# ---------------------------------------------------------------------------
# 4. 충청권·전국 순위 변화 라인차트
# ---------------------------------------------------------------------------

def create_rank_trend_chart(
    rank_changes: dict[int, dict],
    university: str | None = None,
    region_name: str = "충청권",
) -> BytesIO:
    """
    대학의 충청권·전국 순위 연도별 변화 라인차트.
    순위는 낮을수록 좋으므로 Y축을 역전시킨다.

    Args:
        rank_changes: get_rank_changes() 반환값
        university: 표시할 대학명. None이면 config.UNIVERSITY 사용
    """
    univ = university or UNIVERSITY
    years = sorted(rank_changes.keys())
    reg_ranks = [rank_changes[y]["권역순위"] for y in years]
    nat_ranks = [rank_changes[y]["전국순위"] for y in years]

    # 충청권 순위 데이터 존재 여부 확인 (비충청권 대학은 None)
    has_regional = any(r is not None for r in reg_ranks)

    if has_regional:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    else:
        fig, ax2 = plt.subplots(figsize=(7, 5))

    if has_regional:
        # 충청권 순위
        ax1.plot(years, reg_ranks, linestyle="-", marker="o", color="#3F3F46",
                 linewidth=2.5, markersize=8, markerfacecolor="white", markeredgewidth=2)
        for x, y in zip(years, reg_ranks):
            ax1.annotate(f"{y}위", (x, y), textcoords="offset points", xytext=(0, 10),
                         ha="center", fontsize=10, color="#3F3F46", fontweight="bold")
        ax1.set_title(f"{univ} {region_name} 순위 변화", fontsize=12, fontweight="bold")
        ax1.set_xlabel("연도")
        ax1.set_ylabel(f"{region_name} 순위")
        ax1.invert_yaxis()
        ax1.set_xticks(years)
        ax1.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax1.grid(linestyle="--", color="#E5E5E5", linewidth=0.8, alpha=1.0)
        ax1.set_facecolor("white")
        ax1.spines[["top", "right"]].set_visible(False)
        ax1.spines[["left", "bottom"]].set_color("#D4D4D8")
        ax1.tick_params(colors="#525252")

    # 전국 순위
    ax2.plot(years, nat_ranks, linestyle="--", marker="s", color="#71717A",
             linewidth=2.5, markersize=8, markerfacecolor="white", markeredgewidth=1.5)
    for x, y in zip(years, nat_ranks):
        ax2.annotate(f"{y}위", (x, y), textcoords="offset points", xytext=(0, 10),
                     ha="center", fontsize=10, color="#71717A", fontweight="bold")
    ax2.set_title(f"{univ} 전국 순위 변화", fontsize=12, fontweight="bold")
    ax2.set_xlabel("연도")
    ax2.set_ylabel("전국 순위")
    ax2.invert_yaxis()
    ax2.set_xticks(years)
    ax2.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax2.grid(linestyle="--", color="#E5E5E5", linewidth=0.8, alpha=1.0)
    ax2.set_facecolor("white")
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.spines[["left", "bottom"]].set_color("#D4D4D8")
    ax2.tick_params(colors="#525252")

    fig.suptitle(f"{univ} 순위 추이", fontsize=13, fontweight="bold")
    fig.patch.set_facecolor("white")
    fig.tight_layout()

    return _save_fig(fig)


# ---------------------------------------------------------------------------
# 5. 비교군 막대차트 (비교 5개교)
# ---------------------------------------------------------------------------

def create_compare_group_bar(
    compare_data: list[dict],
    year: int,
    university: str | None = None,
) -> BytesIO:
    """
    비교 5개 대학의 1인당논문수 비교 막대차트.

    Args:
        compare_data: get_compare_group_data() 반환값
        year: 기준 연도
        university: 강조 표시할 대학명. None이면 config.UNIVERSITY 사용
    """
    univ = university or UNIVERSITY
    names = [d["학교명"] for d in compare_data]
    values = [d["1인당논문수"] for d in compare_data]
    colors = [COLOR_HOSEO if n == univ else COLOR_OTHERS for n in names]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(names, values, color=colors, edgecolor="#3F3F46", linewidth=0.8, width=0.5)

    # 해당 대학 바에만 hatch 패턴 추가
    for bar, name in zip(bars, names):
        if name == univ:
            bar.set_hatch("///")
            bar.set_edgecolor("#0A0A0A")

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.002,
            f"{val:.4f}",
            ha="center", va="bottom", fontsize=10,
        )

    ax.set_title(f"{year}년 {univ[:-2]}비교군 1인당 SCI/SCOPUS 논문수", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("1인당 논문수 (편)", fontsize=11)
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", linestyle="--", color="#E5E5E5", linewidth=0.8, alpha=1.0)
    ax.set_facecolor("white")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D4D4D8")
    ax.tick_params(colors="#525252")
    fig.patch.set_facecolor("white")
    fig.tight_layout()

    return _save_fig(fig)
