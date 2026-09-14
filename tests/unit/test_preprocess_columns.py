"""전처리 `find_columns` 컬럼 자동 탐지(column auto-detection) 계약 — ETL-U01~U04, U12.

대상: 전임교원_연구실적_전처리.py:123-312 `find_columns`.

대부분 `make_raw_header()` 합성 헤더만 쓰므로 디스크·openpyxl 없이 돈다.
예외는 ETL-U04 의 값 오라클(value oracle) 두 개로, 반환 형태(return shape)에
의존하지 않게 파이프라인 끝단의 숫자를 본다.

연도별 레이아웃 요약(실제 Raw 상위 11행 덤프 기준):
  - 2016: 전임교원/SCI 모두 하위 '계' 헤더 없음 → fallback 이 헤더 열 자체를 채택(정상)
  - 2017: 전임교원은 '계/남/여', SCI 는 '남/여' 뿐 → fallback 이 '남' 열만 채택(V01 결함)
  - 2018/2025: 모든 그룹이 '계/남/여' → '계' 열 정확히 선택
"""

from __future__ import annotations

import pytest

from tests.conftest import RAW_DIR
from tests.fixtures.make_raw_header import make_raw_header, make_raw_with_rows

# 2017 실제 Raw 파일(있을 때만 realdata 오라클을 돈다)
_RAW_2017_MATCHES = sorted(RAW_DIR.glob("2017년*.xlsx")) if RAW_DIR.exists() else []
_RAW_2017 = _RAW_2017_MATCHES[0] if _RAW_2017_MATCHES else None

# 2017 레이아웃에서 SCI 그룹을 이루는 두 열 (하위 헤더 '남' / '여')
_SCI_MALE_COL_2017 = 19
_SCI_FEMALE_COL_2017 = 20

# V01 오라클: 호서대학교 2017년 SCI/SCOPUS 논문수
#   현행(남만)  = 61.4167
#   정답(남+여) = 61.4167 + 15.9447 = 77.3614
_HOSEO_2017_MALE = 61.4167
_HOSEO_2017_FEMALE = 15.9447
_HOSEO_2017_TOTAL = 77.3614
_HOSEO_2017_FACULTY = 477


def _cell(df, row: int, col: int) -> str:
    """헤더 셀을 find_columns 와 같은 방식(줄바꿈 제거 + strip)으로 정규화한다."""
    value = df.iat[row, col]
    return "" if value is None else str(value).replace("\n", "").strip()


# ---------------------------------------------------------------------------
# ETL-U01 / U02 : 정상 탐지 계약
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", ["2018", "2025"])
def test_etl_u01_find_columns_modern_layout(pp_module, style):
    """ETL-U01: 신형(2018/2025) 레이아웃의 6개 반환 키를 정확한 인덱스로 고정한다."""
    cols = pp_module.find_columns(make_raw_header(style))

    assert cols == {
        "학교명": 5,
        "학교종류": 1,
        "지역": 3,
        "전임교원수": 6,
        "SCI논문수": 24,
        "data_start_row": 8,
    }, f"{style} 레이아웃 컬럼 탐지 결과가 달라졌다: {cols}"


@pytest.mark.parametrize("style", ["2018", "2025"])
def test_etl_u01_modern_layout_picks_the_total_subheader(pp_module, style):
    """ETL-U01: 신형 레이아웃이 고른 전임교원/SCI 열의 하위 헤더가 모두 '계'여야 한다."""
    df = make_raw_header(style)
    cols = pp_module.find_columns(df)

    # 줄바꿈이 섞인 상위 헤더('전임\n교원', 'SCI급\n/SCOPUS\n학술지')를 거쳐 찾아낸 결과다.
    assert _cell(df, 3, cols["전임교원수"]) == "전임교원", "상위 헤더가 '전임교원'이 아니다"
    assert "SCOPUS" in _cell(df, 5, cols["SCI논문수"]), "상위 헤더에 SCOPUS 가 없다"
    assert _cell(df, 7, cols["전임교원수"]) == "계", "전임교원수 열의 하위 헤더가 '계'가 아니다"
    assert _cell(df, 7, cols["SCI논문수"]) == "계", "SCI 열의 하위 헤더가 '계'가 아니다"


def test_etl_u02_find_columns_legacy_2016(pp_module):
    """ETL-U02: 2016 구형 레이아웃은 성별 분리가 없어 fallback 이 헤더 열 자체를 채택한다(정상)."""
    df = make_raw_header("2016")
    cols = pp_module.find_columns(df)

    assert cols == {
        "학교명": 5,
        "학교종류": 1,
        "지역": 3,
        "전임교원수": 6,
        "SCI논문수": 12,
        "data_start_row": 7,
    }, f"2016 레이아웃 컬럼 탐지 결과가 달라졌다: {cols}"

    # fallback(전처리.py:207-208, :256-257)이 도는 근거:
    # 선택된 열이 곧 헤더 셀 자체이며, 그 아래 그룹 창(window)에 '계' 하위 헤더가 없다.
    assert _cell(df, 3, cols["전임교원수"]) == "전임교원"
    assert "SCOPUS" in _cell(df, 5, cols["SCI논문수"])
    for row in range(6, 11):
        for col in range(cols["SCI논문수"], min(cols["SCI논문수"] + 6, df.shape[1])):
            assert _cell(df, row, col) != "계", f"2016 에 '계' 하위 헤더가 있다: ({row}, {col})"

    # 2016 은 데이터가 한 행 위(7)에서 시작한다 — 신형(8)과 다르다.
    assert "대학" in str(df.iat[cols["data_start_row"], cols["학교명"]])


def test_etl_u02b_2017_non_sci_keys_are_correct(pp_module):
    """ETL-U02b: 2017 레이아웃에서 SCI 를 제외한 나머지 키는 모두 정상 탐지된다.

    V01 은 SCI 그룹에만 국한된 결함임을 못 박는다. ETL-U03(특성화)이 V01 수정과
    함께 삭제되어도 이 긍정 계약(positive contract)은 남아야 한다.
    """
    df = make_raw_header("2017")
    cols = pp_module.find_columns(df)

    non_sci = {key: value for key, value in cols.items() if key != "SCI논문수"}
    assert non_sci == {
        "학교명": 5,
        "학교종류": 1,
        "지역": 3,
        "전임교원수": 6,
        "data_start_row": 8,
    }, f"2017 레이아웃의 비-SCI 키가 달라졌다: {non_sci}"

    # 전임교원수는 같은 파일에서도 '계'(6)를 제대로 고른다.
    assert _cell(df, 3, 6) == "전임교원"
    assert _cell(df, 7, cols["전임교원수"]) == "계", "전임교원수 열의 하위 헤더가 '계'가 아니다"
    assert "대학" in str(df.iat[cols["data_start_row"], cols["학교명"]])


# ---------------------------------------------------------------------------
# ETL-U03 : V01 현행 동작 기록 (특성화)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ETL-U04 : V01 결함 잠금 (xfail strict — 오늘은 반드시 실패)
# ---------------------------------------------------------------------------
def test_etl_u04_2017_sci_must_cover_both_genders(pp_module, tmp_path):
    """ETL-U04: 2017 레이아웃의 SCI 집계가 남+여 전체(호서대 77.3614)여야 한다.

    두 단계로 단언한다.
      (1) 형태 가드 — 단일 int 열을 반환한다면 그 열의 하위 헤더가 '남'이면 안 된다.
          (수정이 반환 형태를 바꾸는 방식이라면 이 단언은 자동으로 통과한다)
      (2) 값 오라클 — 반환 형태와 무관하게 파이프라인 끝단 숫자로 검증한다.
          19번 열(남) 61.4167 + 20번 열(여) 15.9447 = 77.3614.
          오늘은 61.4167 이 나온다.
    """
    # --- (1) 형태 가드 ---
    df17 = make_raw_header("2017")
    sci = pp_module.find_columns(df17)["SCI논문수"]
    assert not (isinstance(sci, int) and _cell(df17, 7, sci) == "남"), (
        f"find_columns 가 '남' 전용 열({sci})을 SCI 집계 열로 골랐다"
    )

    # --- (2) 값 오라클 (반환 형태 독립) ---
    raw = make_raw_with_rows(
        "2017",
        [
            {
                0: "2016",
                1: "대학교",
                2: "사립",
                3: "충남",
                4: "기존",
                5: "호서대학교",
                6: _HOSEO_2017_FACULTY,
                _SCI_MALE_COL_2017: _HOSEO_2017_MALE,
                _SCI_FEMALE_COL_2017: _HOSEO_2017_FEMALE,
            }
        ],
    )
    xlsx = tmp_path / "2017년_합성.xlsx"
    raw.to_excel(xlsx, header=False, index=False)

    df = pp_module.read_excel(xlsx)
    df = pp_module.filter_universities(df)
    df = pp_module.merge_campuses(df, {"호서대학교": "호서대학교"})[0]  # 반환 길이에 중립 (V14 로 3-튜플이 됨)
    df = pp_module.calculate_metrics(df)

    hoseo = df[df["학교명"] == "호서대학교"]
    assert len(hoseo) == 1, "호서대학교 행이 정확히 1개여야 한다"
    assert hoseo["SCI논문수"].iloc[0] == pytest.approx(_HOSEO_2017_TOTAL, abs=1e-4), (
        "2017 SCI/SCOPUS 논문수가 남+여 합이 아니다"
    )


@pytest.mark.realdata
@pytest.mark.skipif(_RAW_2017 is None, reason="Raw data/2017년*.xlsx 없음")
def test_etl_u04_realdata_2017_hoseo_sci_total(pp_module):
    """ETL-U04(realdata): 실제 2017 Raw 의 호서대 SCI/SCOPUS 논문수가 77.3614 여야 한다.

    read_excel → filter_universities → merge_campuses → calculate_metrics 경로.
    현행은 남성분(61.4167)만 집계되어 1인당논문수까지 과소 산출된다.
    """
    from pathlib import Path

    universities, name_mapping, _regions = pp_module.load_config(
        Path(pp_module.__file__).parent / "config"
    )

    df = pp_module.read_excel(_RAW_2017)
    df = pp_module.filter_universities(df)
    df = pp_module.merge_campuses(df, name_mapping)[0]  # 반환 길이에 중립 (V14 로 3-튜플이 됨)
    df = pp_module.calculate_metrics(df)

    hoseo = df[df["학교명"] == "호서대학교"]
    assert len(hoseo) == 1, "호서대학교 행이 정확히 1개여야 한다"
    assert hoseo["전임교원수"].iloc[0] == pytest.approx(_HOSEO_2017_FACULTY, abs=1e-6), (
        "전임교원수는 '계' 열이 정상 선택되므로 477 이어야 한다"
    )
    assert hoseo["SCI논문수"].iloc[0] == pytest.approx(_HOSEO_2017_TOTAL, abs=1e-4), (
        "실제 2017 파일의 호서대 SCI/SCOPUS 논문수가 남+여 합이 아니다"
    )


# ---------------------------------------------------------------------------
# ETL-U12 : 탐지 실패 시 진단 가능한 ValueError
# ---------------------------------------------------------------------------
def test_etl_u12_find_columns_raises_with_header_dump(pp_module):
    """ETL-U12: 헤더를 찾지 못하면 '컬럼 탐지 실패' + 헤더 덤프를 담은 ValueError 를 던진다."""
    import pandas as pd

    # (a) 전부 NaN 인 11x5 → 5개 항목 모두 실패로 보고된다.
    blank = pd.DataFrame(index=range(11), columns=range(5), dtype=object)
    with pytest.raises(ValueError) as excinfo:
        pp_module.find_columns(blank)

    message = str(excinfo.value)
    assert "컬럼 탐지 실패" in message
    assert "헤더 영역 내용:" in message, "디버그용 헤더 덤프 섹션이 빠졌다"
    for expected in (
        "학교명 컬럼을 찾을 수 없습니다.",
        "학교종류 컬럼을 찾을 수 없습니다.",
        "전임교원수(계) 컬럼을 찾을 수 없습니다.",
        "SCI/SCOPUS 논문수(계) 컬럼을 찾을 수 없습니다.",
        "데이터 시작 행을 찾을 수 없습니다.",
    ):
        assert expected in message, f"실패 항목 누락: {expected}"

    # (b) 값은 있으나 인식 가능한 헤더가 없는 프레임 → 덤프에 실제 셀 내용이 실린다.
    junk = pd.DataFrame(index=range(11), columns=range(5), dtype=object)
    junk.iat[0, 0] = "메타정보"
    junk.iat[3, 2] = "알수없음"
    with pytest.raises(ValueError) as excinfo:
        pp_module.find_columns(junk)

    message = str(excinfo.value)
    assert "컬럼 탐지 실패" in message
    assert "Row 0, Col 0: 메타정보" in message, "헤더 덤프에 셀 좌표/값이 없다"
    assert "Row 3, Col 2: 알수없음" in message, "헤더 덤프에 셀 좌표/값이 없다"
