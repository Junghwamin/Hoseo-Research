"""V20: 전처리 출력 행 순서의 결정성(determinism) 잠금.

`전임교원_연구실적_전처리.py` 의 정렬은 전부 타이브레이커가 없다.

    :496  regional_df.sort_values(["권역명", "권역순위"])
    :509  rdf.sort_values("권역순위")
    :512  national_df.sort_values("전국순위")
    :537  national_combined.sort_values(["연도", "전국순위"])
    :550  region_combined.sort_values(["연도", "권역명", "권역순위"])

pandas 기본 정렬(quicksort)은 불안정하므로 동순위 행의 상대 순서가
입력 순서와 환경에 따라 달라진다. 실측: 추적 중인
`output/전체_대학_데이터.csv` 1,308행에 동순위 그룹 28개(117행)가 있고,
10개 연도 전부에서 현재 순서가 `(전국순위, 학교명)` 정렬과 다르다.

Phase 4 에서 `output/*.csv` 를 재생성할 때 이 비결정성이
V01 수정과 무관한 가짜 diff 를 만들므로 먼저 해소해야 한다.
"""

import pandas as pd
import pytest


def _tie_frame() -> pd.DataFrame:
    """1인당논문수에 동점이 많이 생기도록 만든 입력 프레임.

    전처리 내부 단계 기준 컬럼명(`SCI논문수`)을 쓴다.
    교원수를 맞춰 두면 1인당논문수가 정확히 같아져 동순위가 만들어진다.
    """
    rows = [
        # (학교명, 지역, 전임교원수, SCI논문수) — 1인당 = SCI/교원
        ("가대학교", "충청남도", 100, 20.0),   # 0.2
        ("나대학교", "충청북도", 100, 20.0),   # 0.2  동점
        ("다대학교", "서울특별시", 100, 20.0),  # 0.2  동점
        ("라대학교", "경기도", 100, 10.0),     # 0.1
        ("마대학교", "부산광역시", 100, 10.0),  # 0.1  동점
        ("바대학교", "대구광역시", 100, 30.0),  # 0.3
    ]
    df = pd.DataFrame(rows, columns=["학교명", "지역", "전임교원수", "SCI논문수"])
    df["1인당논문수"] = [
        round(s / t, 4) for s, t in zip(df["SCI논문수"], df["전임교원수"])
    ]
    return df


# REGION_MAP 의 키는 '서울'·'충남' 같은 축약형이므로 권역명을 직접 지정한다.
_UNIV_REGIONS = {
    "가대학교": ["충청권"],
    "나대학교": ["충청권"],
    "다대학교": ["수도권"],
    "라대학교": ["수도권"],
    "마대학교": ["영남권"],
    "바대학교": ["영남권"],
}


def _region_map(df: pd.DataFrame, pp) -> dict:
    return {name: list(_UNIV_REGIONS[name]) for name in df["학교명"]}


def test_v20_rankings_row_order_is_independent_of_input_order(pp_module):
    """수정 후 기대: 입력 행 순서를 바꿔도 출력 행 순서가 같아야 한다.

    구현 중립적인 오라클이다. 타이브레이커로 무엇을 쓰든
    (학교명이든 지역이든) 결정적이기만 하면 통과한다.
    """
    pp = pp_module
    base = _tie_frame()
    rmap = _region_map(base, pp)

    nat_a, reg_a = pp.calculate_rankings(base.copy(), None, rmap)
    # 입력 행 순서를 뒤집는다 (값은 동일, 순서만 다름)
    shuffled = base.iloc[::-1].reset_index(drop=True)
    nat_b, reg_b = pp.calculate_rankings(shuffled, None, rmap)

    assert nat_a["학교명"].tolist() == nat_b["학교명"].tolist(), (
        "전국 순위표의 행 순서가 입력 순서에 따라 달라진다: "
        f"{nat_a['학교명'].tolist()} vs {nat_b['학교명'].tolist()}"
    )
    if not reg_a.empty:
        assert reg_a["학교명"].tolist() == reg_b["학교명"].tolist(), (
            "권역 순위표의 행 순서가 입력 순서에 따라 달라진다"
        )


