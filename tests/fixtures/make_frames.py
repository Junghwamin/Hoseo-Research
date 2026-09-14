"""data_loader / chart_generator / report_builder 용 합성 DataFrame 팩토리.

실데이터(1,308행)를 쓰지 않고도 계약을 고정하기 위한 소형 프레임이다.
컬럼 이름은 전처리 스크립트가 내보내는 실제 이름과 정확히 일치해야 한다
(전처리.py:536, :549 및 data_loader 의 참조).

짧은 별칭(교원/논문/1인당/전국/권역/권역순위)을 쓰면 긴 실제 컬럼명으로
자동 변환되고, 1인당논문수와 순위는 지정하지 않으면 계산해 채운다.
"""

from __future__ import annotations

import pandas as pd

NATIONAL_COLUMNS = [
    "연도",
    "학교명",
    "전임교원수",
    "SCI/SCOPUS논문수",
    "1인당논문수",
    "전국순위",
]
REGIONAL_COLUMNS = [
    "연도",
    "학교명",
    "전임교원수",
    "SCI/SCOPUS논문수",
    "1인당논문수",
    "권역명",
    "권역순위",
    "전국순위",
]
LEGACY_REGIONAL_COLUMNS = [
    "연도",
    "학교명",
    "전임교원수",
    "SCI/SCOPUS논문수",
    "1인당논문수",
    "충청권순위",
    "전국순위",
]

_ALIASES = {
    "year": "연도",
    "name": "학교명",
    "교원": "전임교원수",
    "논문": "SCI/SCOPUS논문수",
    "1인당": "1인당논문수",
    "전국": "전국순위",
    "권역": "권역명",
    "순위": "권역순위",
}


def _normalize(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        out[_ALIASES.get(key, key)] = value
    return out


def _fill_per_capita(rows: list[dict]) -> None:
    """1인당논문수 미지정 시 전처리와 동일한 규칙으로 채운다.

    전처리.py:437-442 와 같은 규칙: 교원수 <= 0 이면 0.0,
    아니면 내장 round(논문/교원, 4).
    """
    for row in rows:
        if "1인당논문수" in row and row["1인당논문수"] is not None:
            continue
        faculty = row.get("전임교원수", 0) or 0
        papers = row.get("SCI/SCOPUS논문수", 0) or 0
        row["1인당논문수"] = round(papers / faculty, 4) if faculty > 0 else 0.0


def _fill_rank(rows: list[dict], rank_col: str, group_cols: list[str]) -> None:
    """순위 미지정 시 1인당논문수 내림차순 min 순위로 채운다 (전처리.py:471-473)."""
    missing = [r for r in rows if r.get(rank_col) is None]
    if not missing:
        return
    frame = pd.DataFrame(rows)
    frame[rank_col] = (
        frame.groupby(group_cols)["1인당논문수"]
        .rank(ascending=False, method="min")
        .astype(int)
    )
    for row, value in zip(rows, frame[rank_col].tolist()):
        if row.get(rank_col) is None:
            row[rank_col] = value


def make_nat(rows: list[dict]) -> pd.DataFrame:
    """전국 데이터 프레임(전체_대학_데이터.csv 포맷)을 만든다.

    Example:
        make_nat([
            {"year": 2024, "name": "A", "교원": 100, "논문": 20},
            {"year": 2025, "name": "A", "교원": 100, "논문": 30},
        ])
    """
    prepared = [_normalize(dict(row)) for row in rows]
    for row in prepared:
        row.setdefault("전국순위", None)
    _fill_per_capita(prepared)
    _fill_rank(prepared, "전국순위", ["연도"])
    return pd.DataFrame(prepared, columns=NATIONAL_COLUMNS)


def make_reg(rows: list[dict]) -> pd.DataFrame:
    """권역 데이터 프레임(권역별_순위.csv 포맷)을 만든다.

    권역명을 생략하면 "충청권" 으로 채운다. 다중 권역 대학은
    같은 (연도, 학교명) 을 권역명만 달리해 두 행으로 넣으면 된다.
    """
    prepared = [_normalize(dict(row)) for row in rows]
    for row in prepared:
        row.setdefault("권역명", "충청권")
        row.setdefault("권역순위", None)
        row.setdefault("전국순위", None)
    _fill_per_capita(prepared)
    _fill_rank(prepared, "권역순위", ["연도", "권역명"])
    _fill_rank(prepared, "전국순위", ["연도"])
    return pd.DataFrame(prepared, columns=REGIONAL_COLUMNS)


def make_legacy_reg(rows: list[dict]) -> pd.DataFrame:
    """레거시 충청권_순위.csv 포맷(권역명 없음, 충청권순위 컬럼)을 만든다.

    `_ensure_new_format` 변환과 V02(업로드 경로 미변환) 재현에 쓴다.
    """
    frame = make_reg(rows)
    frame = frame[frame["권역명"] == "충청권"].drop(columns=["권역명"])
    frame = frame.rename(columns={"권역순위": "충청권순위"})
    return frame[LEGACY_REGIONAL_COLUMNS].reset_index(drop=True)


def simple_pair(years=(2024, 2025), university="호서대학교"):
    """대상 대학 1개 + 비교군 2개로 이루어진 최소 (national, regional) 쌍."""
    rows = []
    for index, year in enumerate(years):
        rows += [
            {"year": year, "name": university, "교원": 100, "논문": 20 + index * 5},
            {"year": year, "name": "순천향대학교", "교원": 200, "논문": 60 + index * 5},
            {"year": year, "name": "선문대학교", "교원": 50, "논문": 5 + index},
        ]
    return make_nat(rows), make_reg(rows)
