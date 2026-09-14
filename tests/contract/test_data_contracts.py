"""계층 간 데이터 계약(data contract) 고정 테스트.

담당 테스트 ID
    - DL-C01 : data_loader 5개 함수의 반환 키 집합(key set)을 정확히 고정하고,
               그 결과를 chart_generator / report_builder / gpt_reporter 에
               그대로 흘려 보내 계층 간 계약이 살아 있는지 확인한다.
               합성(synthetic) 프레임만 쓰므로 실데이터가 없어도 돌아간다.
    - INF-01 : output/ 의 실제 CSV 3종에 대한 포맷·내부 정합성(internal
               consistency) 계약.
    - INF-02 : 충청권_순위.csv 가 권역별_순위.csv 의 충청권 부분집합과
               동일함을 고정.

================================================================================
중요 — 이 파일이 고정하는 것은 "값의 정확성"이 아니라 "포맷과 내부 정합성"이다
================================================================================
output/ 의 CSV 들은 확정 결함 두 건 때문에 **값 자체가 부정확**하다.

    V01 : 2017년 Raw 파일 파싱 오류로 2017년 수치가 신뢰할 수 없다.
    V14 : 사립 134개교만 집계되어 국·공립이 빠진 "전국"이다
          (연도별 행 수 128~134 는 그 결함의 흔적이다).

따라서 여기서 단언하는 것은 다음뿐이다.
    - 컬럼 순서(column order), UTF-8 BOM, 결측(NaN) 0건
    - 키 유일성과 중복의 정체(다중 캠퍼스 대학)
    - 순위(rank) 가 자기 파일 안에서 method='min' 규칙을 지키는가
    - 1인당논문수 == round(논문수 / 교원수, 4) 라는 파생 규칙
    - 두 권역 파일 사이의 값 일치

즉 "숫자가 맞다" 가 아니라 "파일이 자기 자신과 어긋나지 않는다" 를 잠근다.
V01/V14 가 고쳐지면 행 수·연도별 대학 수는 바뀌므로, 그 수치를 기록하는
테스트에는 @pytest.mark.characterization 을 달아 두었다(계약이 아니다).
"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import report_app.chart_generator as cg
import report_app.data_loader as dl
import report_app.gpt_reporter as gr
import report_app.report_builder as rb
from tests.conftest import REALDATA_AVAILABLE, SANDBOX
from tests.fixtures.fake_openai import make_fake_client
from tests.fixtures.make_frames import simple_pair

# ---------------------------------------------------------------------------
# 공통 상수
# ---------------------------------------------------------------------------

#: 합성 시나리오의 비교군. config.COMPARE_GROUP 에 의존하지 않도록 명시한다.
SYNTH_COMPARE_GROUP = ["호서대학교", "순천향대학교", "선문대학교"]
SYNTH_YEAR = 2025
SYNTH_UNIV = "호서대학교"
SYNTH_REGION = "충청권"

#: 각 반환값이 가져야 할 "정확한" 키 집합 (부분집합이 아니라 완전 일치).
TREND_KEYS = {"논문수", "전임교원수", "1인당논문수", "권역순위", "전국순위"}
AVERAGE_KEYS = {"전국평균", "권역평균", "비교군평균"}
RANK_CHANGE_KEYS = {"권역순위", "전국순위", "권역순위_변화", "전국순위_변화"}
YOY_TOP_KEYS = {"상위", "하위", "호서"}
YOY_ENTRY_KEYS = {"학교명", "증감률", "기준연도", "비교연도"}
COMPARE_ENTRY_KEYS = {"학교명", "전임교원수", "논문수", "1인당논문수", "전국순위", "권역순위"}

#: 실제 CSV 3종의 컬럼 순서 계약.
NATIONAL_COLUMNS = [
    "연도", "학교명", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수", "전국순위",
]
REGIONAL_COLUMNS = [
    "연도", "학교명", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수",
    "권역명", "권역순위", "전국순위",
]
LEGACY_REGIONAL_COLUMNS = [
    "연도", "학교명", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수",
    "충청권순위", "전국순위",
]

NUMERIC_COLUMNS = ["연도", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수"]

UTF8_BOM = b"\xef\xbb\xbf"

OUTPUT_DIR = SANDBOX / "output"
NATIONAL_PATH = OUTPUT_DIR / "전체_대학_데이터.csv"
REGIONAL_PATH = OUTPUT_DIR / "권역별_순위.csv"
LEGACY_PATH = OUTPUT_DIR / "충청권_순위.csv"

#: 권역별_순위.csv 에서 (연도, 학교명) 이 중복되는 대학 = 다중 캠퍼스 대학.
#: 본교와 분교가 서로 다른 권역에 있어 두 행으로 나뉜다.
MULTI_CAMPUS_UNIVERSITIES = {
    "경동대학교",
    "단국대학교",
    "상명대학교",
    "예원예술대학교",
    "을지대학교",
    "홍익대학교",
}

_LEGACY_AVAILABLE = LEGACY_PATH.exists()

realdata = pytest.mark.skipif(
    not REALDATA_AVAILABLE, reason="output/ 실데이터(전국·권역 CSV)가 없다"
)
legacydata = pytest.mark.skipif(
    not (REALDATA_AVAILABLE and _LEGACY_AVAILABLE),
    reason="output/충청권_순위.csv 가 없다",
)


# ---------------------------------------------------------------------------
# 로컬 헬퍼
# ---------------------------------------------------------------------------

def _read(path):
    """실제 CSV 를 프로덕션 코드와 동일한 인코딩 규칙으로 읽는다."""
    return pd.read_csv(path, encoding="utf-8-sig")


def _expected_per_capita(papers: float, faculty: int) -> float:
    """전처리 스크립트와 동일한 1인당논문수 규칙.

    전처리는 numpy 의 round 가 아니라 파이썬 내장 round 를 쓴다.
    numpy .round(4) 로 계산하면 2의 거듭제곱 근처에서 마지막 자리가
    1e-4 만큼 어긋나므로 반드시 내장 round 를 써야 한다.
    """
    return round(papers / faculty, 4) if faculty > 0 else 0.0


def _assert_min_rank_rule(ranks: list[int], label: str) -> None:
    """method='min' 순위(rank) 규칙을 구조적으로 검증한다.

    규칙:
        - 최솟값은 1 이다.
        - 어떤 순위 r 에 대해 "r 보다 작은 순위를 가진 행의 수" 는 정확히 r-1 이다.
          (동점은 같은 순위를 공유하고, 다음 순위는 그만큼 건너뛴다)
    """
    assert ranks, f"{label}: 비어 있는 순위 목록"
    assert min(ranks) == 1, f"{label}: 순위가 1부터 시작하지 않는다 (min={min(ranks)})"
    for r in set(ranks):
        fewer = sum(1 for other in ranks if other < r)
        assert fewer == r - 1, (
            f"{label}: 순위 {r} 앞에 {fewer}개가 있다 (method='min' 이면 {r - 1}개여야 한다)"
        )


def _call_all_loaders():
    """DL-C01 시나리오의 data_loader 5개 반환값을 한 번에 만든다."""
    national_df, regional_df = simple_pair(years=(2024, SYNTH_YEAR), university=SYNTH_UNIV)
    trend = dl.get_hoseo_trend(
        national_df, regional_df, university=SYNTH_UNIV, region_name=SYNTH_REGION
    )
    averages = dl.get_averages(
        national_df, regional_df,
        compare_group=SYNTH_COMPARE_GROUP, region_name=SYNTH_REGION,
    )
    rank_changes = dl.get_rank_changes(
        national_df, regional_df, university=SYNTH_UNIV, region_name=SYNTH_REGION
    )
    yoy = dl.get_yoy_changes(
        regional_df, SYNTH_YEAR, university=SYNTH_UNIV, region_name=SYNTH_REGION
    )
    compare = dl.get_compare_group_data(
        national_df, regional_df, SYNTH_YEAR,
        compare_group=SYNTH_COMPARE_GROUP, region_name=SYNTH_REGION,
    )
    return national_df, regional_df, trend, averages, rank_changes, yoy, compare


# ===========================================================================
# DL-C01 — 모듈 간 키 계약
# ===========================================================================

def test_dlc01_data_loader_반환_키집합이_정확히_고정된다():
    """DL-C01: data_loader 5개 함수의 반환 키 집합(key set)을 정확히 고정한다.

    부분집합 검사가 아니라 완전 일치 검사다. 키가 하나라도 늘거나 줄면
    chart_generator / report_builder / gpt_reporter 가 함께 깨진다.
    """
    _, _, trend, averages, rank_changes, yoy, compare = _call_all_loaders()

    # (1) get_hoseo_trend -------------------------------------------------
    assert set(trend.keys()) == {2024, SYNTH_YEAR}, "연도 키가 국가 데이터와 다르다"
    assert all(isinstance(y, int) for y in trend), "연도 키는 int 여야 한다"
    for year, entry in trend.items():
        assert set(entry) == TREND_KEYS, f"get_hoseo_trend[{year}] 키 불일치: {set(entry)}"

    # (2) get_averages ----------------------------------------------------
    assert set(averages.keys()) == {2024, SYNTH_YEAR}
    for year, entry in averages.items():
        assert set(entry) == AVERAGE_KEYS, f"get_averages[{year}] 키 불일치: {set(entry)}"

    # (3) get_rank_changes ------------------------------------------------
    assert set(rank_changes.keys()) == {2024, SYNTH_YEAR}
    for year, entry in rank_changes.items():
        assert set(entry) == RANK_CHANGE_KEYS, (
            f"get_rank_changes[{year}] 키 불일치: {set(entry)}"
        )

    # (4) get_yoy_changes -------------------------------------------------
    assert set(yoy) == YOY_TOP_KEYS, f"get_yoy_changes 최상위 키 불일치: {set(yoy)}"
    assert isinstance(yoy["상위"], list) and isinstance(yoy["하위"], list)
    for bucket in ("상위", "하위"):
        for entry in yoy[bucket]:
            assert set(entry) == YOY_ENTRY_KEYS, (
                f"get_yoy_changes['{bucket}'] 원소 키 불일치: {set(entry)}"
            )
    assert yoy["호서"] is not None, "대상 대학이 증감 목록에 없다"
    assert set(yoy["호서"]) == YOY_ENTRY_KEYS

    # (5) get_compare_group_data ------------------------------------------
    assert isinstance(compare, list) and compare, "비교군 데이터가 비어 있다"
    assert {d["학교명"] for d in compare} == set(SYNTH_COMPARE_GROUP)
    for entry in compare:
        assert set(entry) == COMPARE_ENTRY_KEYS, (
            f"get_compare_group_data 원소 키 불일치: {set(entry)}"
        )


def test_dlc01_로더_출력이_차트_보고서_GPT_로_그대로_흐른다():
    """DL-C01: 로더 반환값을 하위 3계층에 그대로 넣어 예외 없이 통과함을 고정한다.

    chart_generator 5개, gpt_reporter 4개(가짜 클라이언트), report_builder 1개.
    여기서 깨지면 계층 간 계약(layer contract)이 끊어진 것이다.
    """
    _, regional_df, trend, averages, rank_changes, yoy, compare = _call_all_loaders()

    # --- 1) chart_generator 5개 ------------------------------------------
    charts = {
        "trend": cg.create_trend_chart(
            trend, averages, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
        "bar": cg.create_comparison_bar(
            regional_df, SYNTH_YEAR, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
        "avg": cg.create_avg_comparison(
            trend, averages, SYNTH_YEAR, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
        "rank": cg.create_rank_trend_chart(
            rank_changes, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
        "compare": cg.create_compare_group_bar(compare, SYNTH_YEAR, university=SYNTH_UNIV),
    }
    assert set(charts) == {"trend", "bar", "avg", "rank", "compare"}
    for key, buf in charts.items():
        head = buf.getvalue()[:8]
        assert head.startswith(b"\x89PNG"), f"charts['{key}'] 가 PNG 가 아니다: {head!r}"
        buf.seek(0)

    # --- 2) gpt_reporter 4개 (가짜 클라이언트) ----------------------------
    client, completions = make_fake_client(content="고정 서술문")
    narratives = {
        "trend": gr.generate_trend_narrative(
            client, trend, averages, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
        "comparison": gr.generate_comparison_narrative(
            client, compare, averages, SYNTH_YEAR,
            university=SYNTH_UNIV, region_name=SYNTH_REGION,
        ),
        "regional": gr.generate_regional_narrative(
            client, trend, rank_changes, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
        "yoy": gr.generate_yoy_narrative(
            client, yoy, SYNTH_YEAR, university=SYNTH_UNIV, region_name=SYNTH_REGION
        ),
    }
    assert set(narratives) == {"trend", "comparison", "regional", "yoy"}
    assert all(v == "고정 서술문" for v in narratives.values())
    assert len(completions.calls) == 4, "GPT 호출 횟수가 섹션 수와 다르다"

    # --- 3) report_builder ------------------------------------------------
    docx_buf = rb.build_report(
        year=SYNTH_YEAR,
        hoseo_trend=trend,
        averages=averages,
        compare_data=compare,
        yoy_changes=yoy,
        rank_changes=rank_changes,
        charts=charts,
        narratives=narratives,
        university=SYNTH_UNIV,
        region_name=SYNTH_REGION,
    )
    payload = docx_buf.getvalue()
    assert payload[:2] == b"PK", "build_report 결과가 docx(zip) 가 아니다"
    assert len(payload) > 5_000, f"docx 가 비정상적으로 작다: {len(payload)} bytes"


def test_dlc01_gpt_프롬프트가_로더_JSON_을_직렬화할_수_있다():
    """DL-C01: 로더 반환값이 json.dumps 가능한 타입만 담고 있음을 고정한다.

    gpt_reporter 는 로더 결과를 json.dumps 로 프롬프트에 박는다
    (gpt_reporter.py 의 각 generate_* 참조). numpy 스칼라가 섞이면
    TypeError 로 터지므로 직렬화 가능성 자체가 계약이다.
    """
    _, _, trend, averages, rank_changes, yoy, compare = _call_all_loaders()
    client, completions = make_fake_client()

    gr.generate_trend_narrative(client, trend, averages, university=SYNTH_UNIV)
    prompt = completions.last_user_prompt
    assert SYNTH_UNIV in prompt
    assert '"1인당논문수"' in prompt, "추이 데이터가 프롬프트에 직렬화되지 않았다"

    gr.generate_yoy_narrative(client, yoy, SYNTH_YEAR, university=SYNTH_UNIV)
    assert "증감률" in completions.last_user_prompt

    gr.generate_comparison_narrative(client, compare, averages, SYNTH_YEAR)
    assert "전국순위" in completions.last_user_prompt

    gr.generate_regional_narrative(client, trend, rank_changes)
    assert "전국순위_변화" in completions.last_user_prompt


# ===========================================================================
# INF-01 — 실제 output CSV 포맷 계약
# ===========================================================================

@realdata
@pytest.mark.realdata
@pytest.mark.parametrize(
    ("filename", "expected_columns"),
    [
        ("전체_대학_데이터.csv", NATIONAL_COLUMNS),
        ("권역별_순위.csv", REGIONAL_COLUMNS),
        ("충청권_순위.csv", LEGACY_REGIONAL_COLUMNS),
    ],
)
def test_inf01_CSV_컬럼순서와_BOM_과_결측(filename, expected_columns):
    """INF-01: 실제 CSV 3종의 컬럼 순서·UTF-8 BOM·결측 0건을 고정한다.

    컬럼 순서까지 고정하는 이유: 앱과 인스톨러가 CSV 를 헤더 이름으로만
    읽는 게 아니라 미리보기 표로 그대로 보여주기 때문이다.
    """
    path = OUTPUT_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} 없음")

    assert path.read_bytes()[:3] == UTF8_BOM, f"{filename}: UTF-8 BOM 이 없다"

    frame = _read(path)
    assert list(frame.columns) == expected_columns, (
        f"{filename}: 컬럼 순서 불일치\n실제: {list(frame.columns)}\n기대: {expected_columns}"
    )

    for column in NUMERIC_COLUMNS:
        assert pd.api.types.is_numeric_dtype(frame[column]), (
            f"{filename}: {column} 이 숫자 타입이 아니다 ({frame[column].dtype})"
        )
    nan_counts = {c: int(frame[c].isna().sum()) for c in frame.columns}
    assert all(v == 0 for v in nan_counts.values()), f"{filename}: 결측 발생 {nan_counts}"

    assert sorted(frame["연도"].unique().tolist()) == list(range(2016, 2026)), (
        f"{filename}: 연도 집합이 2016~2025 가 아니다"
    )


@realdata
@pytest.mark.realdata
@pytest.mark.characterization
def test_inf01_현재_행수와_연도별_대학수를_기록한다():
    """INF-01(기록): 실제 CSV 의 현재 행 수와 연도별 대학 수를 기록한다.

    이 수치는 계약이 아니라 V14(사립 134개교만 집계)의 흔적이다.
    V01/V14 를 고치면 이 테스트를 함께 갱신해야 한다.
    """
    national = _read(NATIONAL_PATH)
    regional = _read(REGIONAL_PATH)

    assert national.shape == (1308, 6), "전국 CSV 행 수가 바뀌었다 (V14 수정 시 갱신)"
    assert regional.shape == (1368, 8), "권역 CSV 행 수가 바뀌었다 (V14 수정 시 갱신)"

    per_year = national.groupby("연도").size().to_dict()
    assert per_year == {
        2016: 128, 2017: 128, 2018: 128, 2019: 129, 2020: 129,
        2021: 130, 2022: 134, 2023: 134, 2024: 134, 2025: 134,
    }, "연도별 대학 수가 바뀌었다 — 전국이 사립 134개교로 한정된 현재 상태의 기록이다"

    assert sorted(regional["권역명"].unique().tolist()) == [
        "강원권", "수도권", "영남권", "제주권", "충청권", "호남권",
    ]

    if _LEGACY_AVAILABLE:
        assert _read(LEGACY_PATH).shape == (285, 7)


@realdata
@pytest.mark.realdata
def test_inf01_전국은_유일하고_권역중복은_다중캠퍼스뿐이다():
    """INF-01: 전국 CSV 의 (연도,학교명) 유일성과 권역 CSV 중복의 정체를 고정한다."""
    national = _read(NATIONAL_PATH)
    regional = _read(REGIONAL_PATH)

    duplicated = national[national.duplicated(["연도", "학교명"], keep=False)]
    assert duplicated.empty, (
        f"전국 CSV 에 (연도,학교명) 중복 {len(duplicated)}건: "
        f"{sorted(set(duplicated['학교명']))[:10]}"
    )

    # 권역 CSV 는 (연도,학교명) 이 중복될 수 있으나, (연도,학교명,권역명) 은 유일하다.
    assert not regional.duplicated(["연도", "학교명", "권역명"]).any(), (
        "권역 CSV 에 (연도,학교명,권역명) 중복이 있다"
    )

    dup_names = set(regional[regional.duplicated(["연도", "학교명"], keep=False)]["학교명"])
    assert dup_names == MULTI_CAMPUS_UNIVERSITIES, (
        "권역 CSV 중복 학교명이 다중 캠퍼스 대학 목록과 다르다\n"
        f"실제: {sorted(dup_names)}\n기대: {sorted(MULTI_CAMPUS_UNIVERSITIES)}"
    )
    for name in dup_names:
        regions = set(regional[regional["학교명"] == name]["권역명"])
        assert len(regions) >= 2, f"{name}: 중복인데 권역이 하나뿐이다 ({regions})"


@realdata
@pytest.mark.realdata
def test_inf01_순위가_1부터_시작하고_min규칙을_지킨다():
    """INF-01: 전국/권역/레거시 순위가 각 그룹에서 method='min' 규칙을 만족함을 고정한다.

    주의: 권역 CSV 의 '전국순위' 는 권역 CSV 안에서 다시 계산할 수 없다
    (다중 캠퍼스 대학이 2행이라 모수가 1368 로 부풀기 때문). 그 컬럼은
    전국 CSV 에서 복사된 값이므로 별도 테스트에서 일치만 검증한다.
    """
    national = _read(NATIONAL_PATH)
    regional = _read(REGIONAL_PATH)

    for year, group in national.groupby("연도"):
        expected = group["1인당논문수"].rank(ascending=False, method="min").astype(int)
        assert (expected.values == group["전국순위"].values).all(), (
            f"{year}년 전국순위가 1인당논문수 내림차순 min 순위와 다르다"
        )
        _assert_min_rank_rule(group["전국순위"].tolist(), f"{year}년 전국순위")

    for (year, region), group in regional.groupby(["연도", "권역명"]):
        expected = group["1인당논문수"].rank(ascending=False, method="min").astype(int)
        assert (expected.values == group["권역순위"].values).all(), (
            f"{year}년 {region} 권역순위가 1인당논문수 내림차순 min 순위와 다르다"
        )
        _assert_min_rank_rule(group["권역순위"].tolist(), f"{year}년 {region} 권역순위")


@legacydata
@pytest.mark.realdata
def test_inf01_레거시_충청권순위도_min규칙을_지킨다():
    """INF-01: 충청권_순위.csv 의 충청권순위가 연도별 min 규칙을 만족함을 고정한다."""
    legacy = _read(LEGACY_PATH)
    for year, group in legacy.groupby("연도"):
        expected = group["1인당논문수"].rank(ascending=False, method="min").astype(int)
        assert (expected.values == group["충청권순위"].values).all(), (
            f"{year}년 충청권순위가 min 순위와 다르다"
        )
        _assert_min_rank_rule(group["충청권순위"].tolist(), f"{year}년 충청권순위")


@realdata
@pytest.mark.realdata
def test_inf01_권역CSV_의_전국순위는_전국CSV_에서_복사된다():
    """INF-01: 권역 CSV 의 전국순위·교원수·논문수가 전국 CSV 와 완전히 일치함을 고정한다.

    권역 CSV 는 전국 CSV 를 권역으로 펼친 뷰(view)이므로,
    공통 컬럼 값이 하나라도 어긋나면 두 파일이 다른 스냅샷에서 나온 것이다.
    """
    national = _read(NATIONAL_PATH)
    regional = _read(REGIONAL_PATH)

    merged = regional.merge(national, on=["연도", "학교명"], suffixes=("", "_전국"))
    assert len(merged) == len(regional), (
        f"권역 CSV 의 일부 (연도,학교명) 이 전국 CSV 에 없다 "
        f"({len(regional)} → {len(merged)})"
    )
    for column in ["전임교원수", "SCI/SCOPUS논문수", "1인당논문수", "전국순위"]:
        mismatch = int((merged[column] != merged[f"{column}_전국"]).sum())
        assert mismatch == 0, f"{column} 이 전국 CSV 와 {mismatch}건 다르다"


@realdata
@pytest.mark.realdata
@pytest.mark.parametrize(
    "filename", ["전체_대학_데이터.csv", "권역별_순위.csv", "충청권_순위.csv"]
)
def test_inf01_1인당논문수는_논문수나누기교원수_반올림4자리다(filename):
    """INF-01: 1인당논문수 == round(SCI/SCOPUS논문수 / 전임교원수, 4) 를 고정한다.

    교원수가 0 이면 0.0 이다(전처리와 동일 규칙). 허용오차 1e-4.
    """
    path = OUTPUT_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} 없음")
    frame = _read(path)

    worst = 0.0
    worst_row = None
    for _, row in frame.iterrows():
        expected = _expected_per_capita(row["SCI/SCOPUS논문수"], row["전임교원수"])
        diff = abs(expected - row["1인당논문수"])
        if diff > worst:
            worst, worst_row = diff, (row["연도"], row["학교명"], expected, row["1인당논문수"])
    assert worst <= 1e-4, f"{filename}: 1인당논문수 파생 규칙 위반 (최대 오차 {worst}, {worst_row})"


# ===========================================================================
# INF-02 — 충청권 CSV 와 권역별 CSV 의 등가성
# ===========================================================================

def _regional_chungcheong_as_legacy(regional: pd.DataFrame) -> pd.DataFrame:
    """권역별 CSV 의 충청권 부분을 레거시 포맷으로 변환한다."""
    part = regional[regional["권역명"] == "충청권"].drop(columns=["권역명"])
    part = part.rename(columns={"권역순위": "충청권순위"})
    return part[LEGACY_REGIONAL_COLUMNS].sort_values(["연도", "학교명"]).reset_index(drop=True)


@legacydata
@pytest.mark.realdata
def test_inf02_충청권CSV_는_권역별CSV_의_충청권_부분과_동일하다():
    """INF-02: 충청권_순위.csv == 권역별_순위.csv 의 충청권 부분집합(rename/drop 후)."""
    regional = _read(REGIONAL_PATH)
    legacy = _read(LEGACY_PATH)

    expected = _regional_chungcheong_as_legacy(regional)
    actual = legacy[LEGACY_REGIONAL_COLUMNS].sort_values(["연도", "학교명"]).reset_index(drop=True)

    assert len(actual) == len(expected), (
        f"행 수 불일치: 충청권 CSV {len(actual)}행 vs 권역 CSV 충청권 {len(expected)}행"
    )
    assert_frame_equal(actual, expected, check_dtype=True)


@legacydata
@pytest.mark.realdata
def test_inf02_ensure_new_format_이_권역별CSV_충청권과_일치한다():
    """INF-02: dl._ensure_new_format(충청권 CSV) 결과가 권역별 CSV 의 충청권 부분과 같다.

    레거시 자동 변환(충청권순위 → 권역순위, 권역명='충청권' 추가)이
    새 포맷과 값·컬럼 모두에서 어긋나지 않아야 한다.
    """
    regional = _read(REGIONAL_PATH)
    legacy = _read(LEGACY_PATH)

    converted = dl._ensure_new_format(legacy)
    assert "권역순위" in converted.columns and "권역명" in converted.columns
    assert "충청권순위" not in converted.columns
    assert set(converted["권역명"]) == {"충청권"}
    # 컬럼 순서는 변환이 보장하지 않으므로 집합으로만 비교한 뒤 재정렬한다.
    assert set(converted.columns) == set(REGIONAL_COLUMNS), (
        f"변환 결과 컬럼 집합 불일치: {sorted(converted.columns)}"
    )

    actual = (
        converted[REGIONAL_COLUMNS].sort_values(["연도", "학교명"]).reset_index(drop=True)
    )
    expected = (
        regional[regional["권역명"] == "충청권"][REGIONAL_COLUMNS]
        .sort_values(["연도", "학교명"])
        .reset_index(drop=True)
    )
    assert_frame_equal(actual, expected, check_dtype=True)
