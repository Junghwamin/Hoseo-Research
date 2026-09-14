"""report_app/data_loader.py 단위 테스트 (DL-U01~U12).

합성 DataFrame 만 쓰므로 cwd·실데이터와 무관하다.
확정 결함(V10/V12)은 xfail(strict) 로 **고쳐진 뒤의 기대 동작** 을 단언하고,
현재의 결함 동작을 기록만 하는 테스트는 @characterization 으로 오늘 통과한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import report_app.data_loader as dl
from tests.fixtures.make_frames import make_legacy_reg, make_nat, make_reg


# ---------------------------------------------------------------------------
# 로컬 헬퍼
# ---------------------------------------------------------------------------

def _names(rows: list[dict]) -> list[str]:
    """증감률 결과 리스트에서 학교명만 뽑는다."""
    return [row["학교명"] for row in rows]


def _yoy_pair_rows(spec: dict[str, tuple[float, float]], region: str = "충청권") -> list[dict]:
    """{학교명: (이전연도 논문수, 기준연도 논문수)} → 2개년(2024/2025) 권역 행 목록.

    전임교원수는 100 으로 고정하므로 1인당논문수 = 논문수/100 이 된다.
    """
    rows: list[dict] = []
    for name, (prev_papers, cur_papers) in spec.items():
        rows.append({"year": 2024, "name": name, "교원": 100, "논문": prev_papers, "권역": region})
        rows.append({"year": 2025, "name": name, "교원": 100, "논문": cur_papers, "권역": region})
    return rows


# ===========================================================================
# DL-U01  _ensure_new_format
# ===========================================================================

def test_dl_u01_legacy_is_renamed_and_region_added():
    """DL-U01: 레거시(충청권순위) 프레임이 권역순위 + 권역명='충청권' 으로 변환된다."""
    legacy = make_legacy_reg(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60},
        ]
    )

    converted = dl._ensure_new_format(legacy)

    assert "권역순위" in converted.columns, "충청권순위 → 권역순위 로 rename 되어야 한다"
    assert "충청권순위" not in converted.columns, "레거시 컬럼명은 남지 않아야 한다"
    assert converted["권역명"].unique().tolist() == ["충청권"], "권역명은 전부 '충청권' 이어야 한다"
    # 순위 값 자체는 보존된다.
    assert converted["권역순위"].tolist() == legacy["충청권순위"].tolist()


def test_dl_u01_input_frame_is_not_mutated():
    """DL-U01: 변환 함수(pure function)가 입력 DataFrame 을 변형하지 않는다."""
    legacy = make_legacy_reg([{"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20}])
    before_columns = list(legacy.columns)
    before_frame = legacy.copy(deep=True)

    dl._ensure_new_format(legacy)

    assert list(legacy.columns) == before_columns, "입력 프레임의 컬럼 구성이 바뀌면 안 된다"
    assert legacy.equals(before_frame), "입력 프레임의 값이 바뀌면 안 된다"


def test_dl_u01_new_format_returns_same_object():
    """DL-U01: 이미 새 포맷이면 복사 없이 **동일 객체(identity)** 를 반환한다."""
    new_format = make_reg([{"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20}])

    assert dl._ensure_new_format(new_format) is new_format


def test_dl_u01_both_columns_present_means_no_conversion():
    """DL-U01: 충청권순위·권역순위가 공존하면 변환하지 않고 동일 객체를 반환한다."""
    both = make_reg([{"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20}])
    both["충청권순위"] = 99

    result = dl._ensure_new_format(both)

    assert result is both, "이미 권역순위가 있으면 무변환(no-op)"
    assert result["충청권순위"].tolist() == [99], "레거시 컬럼은 그대로 남는다"


def test_dl_u01_is_idempotent():
    """DL-U01: 멱등(idempotent) — f(f(x)) 가 f(x) 와 값이 같다."""
    legacy = make_legacy_reg(
        [
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 25},
        ]
    )

    once = dl._ensure_new_format(legacy)
    twice = dl._ensure_new_format(once)

    assert twice.equals(once)
    assert list(twice.columns) == list(once.columns)


# ===========================================================================
# DL-U02  load_all_data
# ===========================================================================

def _write_csv_set(tmp_path):
    """(national, new-regional, legacy-regional) CSV 3개를 tmp_path 에 utf-8-sig 로 쓴다."""
    national = make_nat(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60},
        ]
    )
    regional = make_reg(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60},
        ]
    )
    legacy = make_legacy_reg(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60},
        ]
    )
    national_path = tmp_path / "전체_대학_데이터.csv"
    regional_path = tmp_path / "권역별_순위.csv"
    legacy_path = tmp_path / "충청권_순위.csv"
    national.to_csv(national_path, index=False, encoding="utf-8-sig")
    regional.to_csv(regional_path, index=False, encoding="utf-8-sig")
    legacy.to_csv(legacy_path, index=False, encoding="utf-8-sig")
    return national_path, regional_path, legacy_path


def _patch_paths(monkeypatch, national_path, regional_path, legacy_path):
    """data_loader 모듈에 바인딩된 경로 상수 3개를 교체한다.

    config 를 패치해도 효과가 없다. data_loader.py:29-35 가 from-import 로
    **값을 모듈 전역에 바인딩**하기 때문에 반드시 data_loader 쪽을 패치해야 한다.
    """
    monkeypatch.setattr(dl, "NATIONAL_CSV", national_path)
    monkeypatch.setattr(dl, "REGIONAL_CSV", regional_path)
    monkeypatch.setattr(dl, "REGIONAL_CSV_LEGACY", legacy_path)


def test_dl_u02_reads_new_format_csv(tmp_path, monkeypatch):
    """DL-U02(a): 새 포맷 권역 CSV 가 있으면 그대로 읽는다."""
    national_path, regional_path, legacy_path = _write_csv_set(tmp_path)
    _patch_paths(monkeypatch, national_path, regional_path, legacy_path)

    national_df, regional_df = dl.load_all_data()

    assert "권역순위" in regional_df.columns
    assert "권역명" in regional_df.columns
    assert "충청권순위" not in regional_df.columns
    assert national_df["학교명"].tolist() == ["호서대학교", "순천향대학교"]


def test_dl_u02_falls_back_to_legacy_and_converts(tmp_path, monkeypatch):
    """DL-U02(b): 새 포맷이 없으면 레거시 CSV 를 읽어 새 포맷으로 변환한다."""
    national_path, regional_path, legacy_path = _write_csv_set(tmp_path)
    _patch_paths(monkeypatch, national_path, tmp_path / "없는_권역별_순위.csv", legacy_path)

    _, regional_df = dl.load_all_data()

    assert "권역순위" in regional_df.columns, "레거시도 권역순위로 변환되어야 한다"
    assert "충청권순위" not in regional_df.columns
    assert regional_df["권역명"].unique().tolist() == ["충청권"]


def test_dl_u02_raises_filenotfound_naming_both_files(tmp_path, monkeypatch):
    """DL-U02(c): 권역 CSV 가 둘 다 없으면 두 파일명을 모두 담은 FileNotFoundError."""
    national_path, _, _ = _write_csv_set(tmp_path)
    missing_new = tmp_path / "없는_권역별_순위.csv"
    missing_legacy = tmp_path / "없는_충청권_순위.csv"
    _patch_paths(monkeypatch, national_path, missing_new, missing_legacy)

    with pytest.raises(FileNotFoundError) as excinfo:
        dl.load_all_data()

    message = str(excinfo.value)
    assert missing_new.name in message, "새 포맷 파일명이 오류 메시지에 있어야 한다"
    assert missing_legacy.name in message, "레거시 파일명이 오류 메시지에 있어야 한다"


def test_dl_u02_direct_dataframes_skip_file_io(tmp_path, monkeypatch):
    """DL-U02(d): DataFrame 을 직접 넘기면 경로가 존재하지 않아도 파일을 읽지 않는다."""
    _patch_paths(
        monkeypatch,
        tmp_path / "없는_전체.csv",
        tmp_path / "없는_권역별.csv",
        tmp_path / "없는_충청권.csv",
    )
    national = make_nat([{"year": 2025, "name": "직접주입대학교", "교원": 10, "논문": 5}])
    legacy = make_legacy_reg([{"year": 2025, "name": "직접주입대학교", "교원": 10, "논문": 5}])

    national_df, regional_df = dl.load_all_data(national_df=national, regional_df=legacy)

    assert national_df is national, "national_df 는 그대로 통과(pass-through)한다"
    assert "권역순위" in regional_df.columns, "직접 주입한 레거시도 변환 대상이다"


# ===========================================================================
# DL-U03  get_hoseo_trend
# ===========================================================================

def _trend_frames():
    """2개 권역에 등재된 호서대학교 + 권역 밖 대학 1개로 구성한 (national, regional)."""
    national = make_nat(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20, "전국": 3},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 15, "전국": 5},
            {"year": 2025, "name": "타권역대학교", "교원": 50, "논문": 30, "전국": 1},
        ]
    )
    regional = make_reg(
        [
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 15, "권역": "충청권", "순위": 4},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "충청권", "순위": 2},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "수도권", "순위": 9},
            {"year": 2025, "name": "타권역대학교", "교원": 50, "논문": 30, "권역": "수도권", "순위": 1},
        ]
    )
    return national, regional


def test_dl_u03_region_filter_selects_that_region_rank():
    """DL-U03: region_name 을 주면 그 권역의 권역순위만 반영된다."""
    national, regional = _trend_frames()

    chungcheong = dl.get_hoseo_trend(national, regional, university="호서대학교", region_name="충청권")
    sudogwon = dl.get_hoseo_trend(national, regional, university="호서대학교", region_name="수도권")

    assert chungcheong[2025]["권역순위"] == 2, "충청권 필터 시 충청권 순위"
    assert sudogwon[2025]["권역순위"] == 9, "수도권 필터 시 수도권 순위"
    assert sudogwon[2024]["권역순위"] is None, "2024 수도권 행이 없으므로 None"


def test_dl_u03_missing_university_returns_empty_dict():
    """DL-U03: national_df 에 대상 대학이 없으면 빈 dict 를 반환한다."""
    national, regional = _trend_frames()

    assert dl.get_hoseo_trend(national, regional, university="없는대학교") == {}


def test_dl_u03_missing_in_regional_keeps_rank_none():
    """DL-U03: regional_df 에 대상 대학이 없으면 권역순위가 None 으로 남는다."""
    national, regional = _trend_frames()

    result = dl.get_hoseo_trend(national, regional, university="타권역대학교", region_name="충청권")

    assert set(result.keys()) == {2025}
    assert result[2025]["권역순위"] is None


def test_dl_u03_years_are_sorted_ascending():
    """DL-U03: 결과 dict 의 키가 연도 오름차순이다."""
    national, regional = _trend_frames()

    result = dl.get_hoseo_trend(national, regional, university="호서대학교", region_name="충청권")

    assert list(result.keys()) == [2024, 2025], "national_df 행 순서와 무관하게 정렬되어야 한다"


def test_dl_u03_value_types_and_rounding():
    """DL-U03: 논문수 round 2 / 1인당 round 4 / 교원수·순위는 python int."""
    national = make_nat([{"year": 2025, "name": "호서대학교", "교원": 3, "논문": 20.123456, "전국": 7}])
    regional = make_reg(
        [{"year": 2025, "name": "호서대학교", "교원": 3, "논문": 20.123456, "권역": "충청권", "순위": 2}]
    )

    row = dl.get_hoseo_trend(national, regional, university="호서대학교", region_name="충청권")[2025]

    assert row["논문수"] == round(20.123456, 2)
    assert row["1인당논문수"] == round(round(20.123456 / 3, 4), 4)
    assert type(row["전임교원수"]) is int
    assert type(row["전국순위"]) is int
    assert type(row["권역순위"]) is int
    assert isinstance(row["논문수"], float) and not isinstance(row["논문수"], np.generic)


# ===========================================================================
# DL-U04  get_averages
# ===========================================================================

def _average_frames():
    national = make_nat(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60},
            {"year": 2025, "name": "수도권대학교", "교원": 50, "논문": 5},
        ]
    )
    regional = make_reg(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "충청권"},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60, "권역": "충청권"},
            {"year": 2025, "name": "수도권대학교", "교원": 50, "논문": 5, "권역": "수도권"},
        ]
    )
    return national, regional


def test_dl_u04_matches_arithmetic_mean_rounded_4():
    """DL-U04: 전국/권역/비교군 평균이 실제 산술평균(round 4)과 일치한다."""
    national, regional = _average_frames()
    compare_group = ["호서대학교", "순천향대학교"]

    result = dl.get_averages(national, regional, compare_group=compare_group, region_name="충청권")

    nat_year = national[national["연도"] == 2025]
    reg_year = regional[(regional["연도"] == 2025) & (regional["권역명"] == "충청권")]
    cmp_year = nat_year[nat_year["학교명"].isin(compare_group)]

    assert result[2025]["전국평균"] == round(float(nat_year["1인당논문수"].mean()), 4)
    assert result[2025]["권역평균"] == round(float(reg_year["1인당논문수"].mean()), 4)
    assert result[2025]["비교군평균"] == round(float(cmp_year["1인당논문수"].mean()), 4)


def test_dl_u04_empty_compare_group_gives_zero():
    """DL-U04: compare_group=[] 이면 비교군평균이 0.0 이다(기본값 fallback 아님)."""
    national, regional = _average_frames()

    result = dl.get_averages(national, regional, compare_group=[], region_name="충청권")

    assert result[2025]["비교군평균"] == 0.0
    assert result[2025]["전국평균"] > 0.0, "다른 평균은 영향을 받지 않는다"


def test_dl_u04_region_without_rows_gives_zero():
    """DL-U04: 해당 권역 행이 하나도 없으면 권역평균이 0.0 이다."""
    national, regional = _average_frames()

    result = dl.get_averages(national, regional, compare_group=["호서대학교"], region_name="제주권")

    assert result[2025]["권역평균"] == 0.0


def test_dl_u04_region_name_none_uses_whole_regional_frame():
    """DL-U04: region_name=None 이면 regional_df 전체가 '권역평균' 이 된다.

    V03(권역 라벨과 실제 집계 범위의 불일치)의 원인이 되는 동작이지만,
    여기서는 순수 함수(pure function)의 계산 계약만 고정한다.
    권역 라벨링 문제는 research.py 심(seam)의 R7-05 가 잠근다.
    """
    national, regional = _average_frames()

    result = dl.get_averages(national, regional, compare_group=["호서대학교"], region_name=None)

    reg_year = regional[regional["연도"] == 2025]
    assert result[2025]["권역평균"] == round(float(reg_year["1인당논문수"].mean()), 4)

    only_chungcheong = regional[(regional["연도"] == 2025) & (regional["권역명"] == "충청권")]
    assert result[2025]["권역평균"] != round(float(only_chungcheong["1인당논문수"].mean()), 4), (
        "전체 프레임 평균은 충청권만의 평균과 달라야 한다(테스트 데이터 전제 확인)"
    )


# ===========================================================================
# DL-U05  get_rank_changes
# ===========================================================================

def test_dl_u05_positive_change_means_rank_improved():
    """DL-U05: 부호 규약 — 전국 12위 → 10위이면 전국순위_변화 == +2 (양수 = 개선)."""
    national = make_nat(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "전국": 12},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 30, "전국": 10},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 25, "전국": 14},
        ]
    )
    regional = make_reg(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "충청권", "순위": 5},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 30, "권역": "충청권", "순위": 3},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 25, "권역": "충청권", "순위": 6},
        ]
    )

    result = dl.get_rank_changes(national, regional, university="호서대학교", region_name="충청권")

    assert result[2024]["전국순위_변화"] == 2, "순위 숫자가 작아지면(개선) 양수"
    assert result[2024]["권역순위_변화"] == 2
    assert result[2025]["전국순위_변화"] == -4, "순위 숫자가 커지면(악화) 음수"
    assert result[2025]["권역순위_변화"] == -3


def test_dl_u05_first_year_change_is_none():
    """DL-U05: 가장 이른 연도는 비교 대상이 없으므로 변화가 None 이다."""
    national = make_nat(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "전국": 12},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 30, "전국": 10},
        ]
    )
    regional = make_reg(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "충청권", "순위": 5},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 30, "권역": "충청권", "순위": 3},
        ]
    )

    result = dl.get_rank_changes(national, regional, university="호서대학교", region_name="충청권")

    assert result[2023]["전국순위_변화"] is None
    assert result[2023]["권역순위_변화"] is None
    assert list(result.keys()) == [2023, 2024], "연도 오름차순"


def test_dl_u05_absent_in_regional_gives_none_rank_and_change():
    """DL-U05: regional_df 에 대학이 없으면 권역순위·권역순위_변화가 모두 None 이다."""
    national = make_nat(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "전국": 12},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 30, "전국": 10},
        ]
    )
    regional = make_reg([{"year": 2024, "name": "다른대학교", "교원": 10, "논문": 1, "권역": "충청권"}])

    result = dl.get_rank_changes(national, regional, university="호서대학교", region_name="충청권")

    assert [result[y]["권역순위"] for y in (2023, 2024)] == [None, None]
    assert [result[y]["권역순위_변화"] for y in (2023, 2024)] == [None, None]
    assert result[2024]["전국순위_변화"] == 2, "전국 쪽은 정상 계산된다"


@pytest.mark.characterization
def test_dl_u05_year_gap_compares_against_previous_existing_year():
    """DL-U05: [특성화] 연도가 비면 '직전 존재 연도' 와 비교한다(2024 결측 → 2025 vs 2023).

    현재 구현(data_loader.py:249-264)은 year-1 이 아니라 루프의 직전 항목을 쓴다.
    """
    national = make_nat(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "전국": 12},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 30, "전국": 10},
        ]
    )
    regional = make_reg(
        [
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "충청권", "순위": 5},
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 30, "권역": "충청권", "순위": 1},
        ]
    )

    result = dl.get_rank_changes(national, regional, university="호서대학교", region_name="충청권")

    assert list(result.keys()) == [2023, 2025]
    assert result[2025]["전국순위_변화"] == 2, "2024 가 없어도 2023 대비로 계산된다"
    assert result[2025]["권역순위_변화"] == 4


# ===========================================================================
# DL-U06  get_compare_group_data
# ===========================================================================

def _compare_frames():
    national = make_nat(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20, "전국": 3},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60, "전국": 1},
            {"year": 2025, "name": "선문대학교", "교원": 50, "논문": 5, "전국": 4},
            {"year": 2025, "name": "비교군밖대학교", "교원": 10, "논문": 9, "전국": 2},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 10, "전국": 8},
        ]
    )
    regional = make_reg(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20, "권역": "충청권", "순위": 2},
            {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60, "권역": "충청권", "순위": 1},
            {"year": 2025, "name": "선문대학교", "교원": 50, "논문": 5, "권역": "수도권", "순위": 1},
        ]
    )
    return national, regional


def test_dl_u06_filters_year_and_compare_group():
    """DL-U06: 지정 연도 + 비교군 소속 대학만 남고, 없는 대학명은 예외 없이 무시된다."""
    national, regional = _compare_frames()

    result = dl.get_compare_group_data(
        national,
        regional,
        2025,
        compare_group=["호서대학교", "순천향대학교", "선문대학교", "존재하지않는대학교"],
        region_name="충청권",
    )

    assert _names(result) == ["순천향대학교", "호서대학교", "선문대학교"]
    assert "비교군밖대학교" not in _names(result), "비교군 밖 대학은 결과에 없다"
    assert "존재하지않는대학교" not in _names(result), "데이터에 없는 대학명은 무시된다"


def test_dl_u06_sorted_by_per_capita_descending():
    """DL-U06: 1인당논문수 내림차순으로 정렬된다."""
    national, regional = _compare_frames()

    result = dl.get_compare_group_data(
        national, regional, 2025, compare_group=["호서대학교", "순천향대학교", "선문대학교"]
    )

    values = [row["1인당논문수"] for row in result]
    assert values == sorted(values, reverse=True)


def test_dl_u06_outside_region_gets_none_rank_and_types():
    """DL-U06: 권역 밖 대학은 권역순위 None, 나머지 값은 int/round 타입 계약을 지킨다."""
    national, regional = _compare_frames()

    result = dl.get_compare_group_data(
        national,
        regional,
        2025,
        compare_group=["호서대학교", "순천향대학교", "선문대학교"],
        region_name="충청권",
    )
    by_name = {row["학교명"]: row for row in result}

    assert by_name["선문대학교"]["권역순위"] is None, "수도권 대학은 충청권 필터에서 빠진다"
    assert by_name["호서대학교"]["권역순위"] == 2
    assert type(by_name["호서대학교"]["전임교원수"]) is int
    assert type(by_name["호서대학교"]["전국순위"]) is int
    assert by_name["호서대학교"]["논문수"] == round(20.0, 2)
    assert by_name["호서대학교"]["1인당논문수"] == round(0.2, 4)


# ===========================================================================
# DL-U07  detect_region / get_region_universities
# ===========================================================================

def _region_frame():
    return make_reg(
        [
            {"year": 2024, "name": "다중권역대학교", "교원": 100, "논문": 50, "권역": "수도권"},
            {"year": 2025, "name": "다중권역대학교", "교원": 100, "논문": 50, "권역": "충청권"},
            {"year": 2025, "name": "충청권대학교", "교원": 100, "논문": 10, "권역": "충청권"},
        ]
    )


def test_dl_u07_detect_region_returns_sorted_unique_regions():
    """DL-U07: 다중 권역 대학은 권역명 목록을 정렬해 반환한다."""
    assert dl.detect_region("다중권역대학교", _region_frame()) == ["수도권", "충청권"]


def test_dl_u07_detect_region_unknown_university_returns_empty():
    """DL-U07: 데이터에 없는 대학은 빈 리스트를 반환한다."""
    assert dl.detect_region("없는대학교", _region_frame()) == []


def test_dl_u07_detect_region_without_column_returns_empty():
    """DL-U07: '권역명' 컬럼이 없는 프레임은 가드가 있어 빈 리스트를 반환한다."""
    legacy = make_legacy_reg([{"year": 2025, "name": "다중권역대학교", "교원": 100, "논문": 50}])

    assert "권역명" not in legacy.columns
    assert dl.detect_region("다중권역대학교", legacy) == []


def test_dl_u07_get_region_universities_filters_region_and_year():
    """DL-U07: 권역 필터와 연도 필터가 함께 동작하고 결과는 정렬된다."""
    frame = _region_frame()

    assert dl.get_region_universities(frame, "충청권") == ["다중권역대학교", "충청권대학교"]
    assert dl.get_region_universities(frame, "충청권", year=2025) == ["다중권역대학교", "충청권대학교"]
    assert dl.get_region_universities(frame, "수도권", year=2024) == ["다중권역대학교"]
    assert dl.get_region_universities(frame, "수도권", year=2025) == []
    assert dl.get_region_universities(frame, "제주권") == []


@pytest.mark.characterization
def test_dl_u07_get_region_universities_without_column_raises_keyerror():
    """DL-U07: [특성화] detect_region 과 달리 '권역명' 가드가 없어 KeyError 가 난다.

    data_loader.py:115 은 컬럼 존재를 확인하지 않는다(detect_region:103 과 비대칭).
    """
    legacy = make_legacy_reg([{"year": 2025, "name": "다중권역대학교", "교원": 100, "논문": 50}])

    with pytest.raises(KeyError) as excinfo:
        dl.get_region_universities(legacy, "충청권")

    assert excinfo.value.args[0] == "권역명"


# ===========================================================================
# DL-U08  get_yoy_changes (정상 경로)
# ===========================================================================

def _yoy_six_universities():
    """증감률이 모두 다른 6개교 — head(3)/tail(3) 이 겹치지 않는 정상 표본."""
    return make_reg(
        _yoy_pair_rows(
            {
                "가대학교": (10, 20),  # +100.0%
                "나대학교": (10, 18),  # +80.0%
                "다대학교": (10, 15),  # +50.0%
                "라대학교": (10, 12),  # +20.0%
                "마대학교": (10, 11),  # +10.0%
                "바대학교": (10, 5),   # -50.0%
            }
        )
    )


def test_dl_u08_growth_rate_formula_and_keys():
    """DL-U08: 반환 키가 {'상위','하위','호서'} 이고 증감률 = round((현재-이전)/이전*100, 1)."""
    regional = _yoy_six_universities()

    result = dl.get_yoy_changes(regional, 2025, university="다대학교", region_name="충청권")

    assert set(result.keys()) == {"상위", "하위", "호서"}
    for row in result["상위"] + result["하위"]:
        expected = round((row["기준연도"] - row["비교연도"]) / row["비교연도"] * 100, 1)
        assert row["증감률"] == expected, f"{row['학교명']} 증감률 공식 불일치"


def test_dl_u08_top_is_descending_and_bottom_keeps_descending_order():
    """DL-U08: 상위는 최고 증감률이 먼저, 하위도 내림차순 유지(최저가 마지막)."""
    regional = _yoy_six_universities()

    result = dl.get_yoy_changes(regional, 2025, university="다대학교", region_name="충청권")

    top_rates = [row["증감률"] for row in result["상위"]]
    bottom_rates = [row["증감률"] for row in result["하위"]]

    assert top_rates == sorted(top_rates, reverse=True)
    assert top_rates[0] == 100.0, "최고 증감률이 상위 첫 번째"
    assert bottom_rates == sorted(bottom_rates, reverse=True)
    assert bottom_rates[-1] == -50.0, "최저 증감률이 하위 마지막"
    assert _names(result["상위"]) == ["가대학교", "나대학교", "다대학교"]
    assert _names(result["하위"]) == ["라대학교", "마대학교", "바대학교"]


def test_dl_u08_hoseo_key_follows_university_argument():
    """DL-U08: '호서' 키는 하드코딩이 아니라 university= 로 지정한 대학의 행이다."""
    regional = _yoy_six_universities()

    result = dl.get_yoy_changes(regional, 2025, university="마대학교", region_name="충청권")

    assert result["호서"] is not None
    assert result["호서"]["학교명"] == "마대학교"
    assert result["호서"]["증감률"] == 10.0
    assert result["호서"]["기준연도"] == round(0.11, 4)
    assert result["호서"]["비교연도"] == round(0.10, 4)


def test_dl_u08_missing_previous_year_returns_empty_result():
    """DL-U08: 전년 데이터가 없으면 {'상위': [], '하위': [], '호서': None} 이다."""
    regional = _yoy_six_universities()

    result = dl.get_yoy_changes(regional, 2024, university="다대학교", region_name="충청권")

    assert result == {"상위": [], "하위": [], "호서": None}


def test_dl_u08_region_filter_excludes_other_regions():
    """DL-U08: region_name 을 주면 다른 권역 대학은 증감률 집계에서 빠진다."""
    rows = _yoy_pair_rows({"충청가": (10, 20), "충청나": (10, 5)}, region="충청권")
    rows += _yoy_pair_rows({"수도가": (10, 99)}, region="수도권")
    regional = make_reg(rows)

    result = dl.get_yoy_changes(regional, 2025, university="충청가", region_name="충청권")

    assert "수도가" not in set(_names(result["상위"]) + _names(result["하위"]))


# ===========================================================================
# DL-U09  get_yoy_changes — V12 (확정 결함 잠금)
# ===========================================================================

def test_dl_u09_top_and_bottom_must_not_overlap():
    """DL-U09: [V12 xfail] 상위·하위 목록에 같은 대학이 동시에 나타나면 안 된다.

    비교군 5개교(기본 경로) → 현재는 정중앙 1개교가 양쪽에 중복된다.
    2개교만 있을 때는 상위와 하위가 완전히 같아진다.
    """
    five = make_reg(
        _yoy_pair_rows(
            {
                "가대학교": (10, 20),
                "나대학교": (10, 18),
                "다대학교": (10, 15),
                "라대학교": (10, 12),
                "마대학교": (10, 11),
            }
        )
    )
    result = dl.get_yoy_changes(five, 2025, university="가대학교", region_name="충청권")

    assert set(_names(result["상위"])) & set(_names(result["하위"])) == set(), (
        "상위 3개교와 하위 3개교는 서로 배타적이어야 한다"
    )

    two = make_reg(_yoy_pair_rows({"가대학교": (10, 20), "나대학교": (10, 11)}))
    result_two = dl.get_yoy_changes(two, 2025, university="가대학교", region_name="충청권")

    assert result_two["상위"] != result_two["하위"], "2개교뿐이어도 상위와 하위가 같아선 안 된다"


def test_dl_u09_zero_baseline_new_output_is_distinguishable():
    """DL-U09: [V12 xfail] 이전값 0·현재값>0 과 이전값 0·현재값 0 이 구분되어야 한다.

    표기 방식(‘신규’ 라벨 / 집계 제외 / 다른 값)은 구현에 열어두고,
    "두 행이 동일한 증감률로 뭉뚱그려지지 않는다" 만 단언한다.
    """
    regional = make_reg(_yoy_pair_rows({"신규실적대학교": (0, 30), "무실적대학교": (0, 0)}))

    result = dl.get_yoy_changes(regional, 2025, university="신규실적대학교", region_name="충청권")
    by_name = {row["학교명"]: row for row in result["상위"] + result["하위"]}
    new_row = by_name.get("신규실적대학교")
    zero_row = by_name.get("무실적대학교")

    indistinguishable = (
        new_row is not None
        and zero_row is not None
        and new_row["증감률"] == zero_row["증감률"]
    )
    assert not indistinguishable, (
        "0 → 양수(신규 실적)가 0 → 0(무실적)과 같은 증감률로 표기되면 안 된다 "
        f"(현재: 신규={new_row}, 무실적={zero_row})"
    )


# ===========================================================================
# DL-U10  다중 권역 — V10
# ===========================================================================

def _multi_region_yoy_frame():
    """수도권·충청권에 동시 등재된 '다중권역대학교' 1곳 + 충청권 단일 등재 5곳."""
    rows: list[dict] = []
    for year, papers in ((2024, 10), (2025, 30)):
        for region in ("수도권", "충청권"):
            rows.append(
                {"year": year, "name": "다중권역대학교", "교원": 100, "논문": papers, "권역": region}
            )
    rows += _yoy_pair_rows(
        {
            "가대학교": (10, 13),
            "나대학교": (10, 12),
            "다대학교": (10, 11),
            "라대학교": (10, 9),
            "마대학교": (10, 8),
        }
    )
    return make_reg(rows)


def test_dl_u10_multi_region_university_appears_once_in_yoy():
    """DL-U10(a): [V10 xfail] region_name=None 일 때 상위·하위 학교명이 유일해야 한다.

    다중권역대학교는 연도마다 2행이므로 학교명 단일키 merge 시 4행으로 불어난다.
    """
    regional = _multi_region_yoy_frame()

    result = dl.get_yoy_changes(regional, 2025, university="다중권역대학교", region_name=None)

    top_names = _names(result["상위"])
    bottom_names = _names(result["하위"])
    assert len(set(top_names)) == len(top_names), f"상위에 중복 학교명: {top_names}"
    assert len(set(bottom_names)) == len(bottom_names), f"하위에 중복 학교명: {bottom_names}"


@pytest.mark.characterization
def test_dl_u10_trend_region_rank_depends_on_row_order():
    """DL-U10(b): [특성화] region_name=None 이면 권역순위가 '마지막 행 승리' 로 정해진다.

    docstring(data_loader.py:138)은 "None이면 대학이 속한 첫 번째 권역 사용" 이라고 하지만
    구현(:163-166)은 reg_filtered 를 끝까지 순회하며 덮어써서 **마지막 행** 이 이긴다.
    따라서 같은 데이터라도 행 순서를 뒤집으면 결과가 바뀐다(순서 의존).
    """
    regional = make_reg(
        [
            {"year": 2025, "name": "다중권역대학교", "교원": 100, "논문": 50, "권역": "수도권", "순위": 1},
            {"year": 2025, "name": "다중권역대학교", "교원": 100, "논문": 50, "권역": "충청권", "순위": 7},
        ]
    )
    national = make_nat([{"year": 2025, "name": "다중권역대학교", "교원": 100, "논문": 50, "전국": 1}])

    forward = dl.get_hoseo_trend(national, regional, university="다중권역대학교", region_name=None)
    reversed_frame = regional.iloc[::-1].reset_index(drop=True)
    backward = dl.get_hoseo_trend(national, reversed_frame, university="다중권역대학교", region_name=None)

    assert forward[2025]["권역순위"] == 7, "마지막 행(충청권)의 순위가 남는다"
    assert backward[2025]["권역순위"] == 1, "행 순서를 뒤집으면 수도권 순위가 남는다"
    assert forward[2025]["권역순위"] != backward[2025]["권역순위"], (
        "docstring 의 '첫 번째 권역' 규칙이었다면 순서에 무관해야 한다"
    )


# ===========================================================================
# DL-U11  레거시 프레임 직접 투입 — V02 전제
# ===========================================================================

def _legacy_pair():
    """변환 없이 투입되는 레거시 (national, legacy-regional) 쌍 (2개년)."""
    rows = [
        {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 10},
        {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
        {"year": 2024, "name": "순천향대학교", "교원": 200, "논문": 40},
        {"year": 2025, "name": "순천향대학교", "교원": 200, "논문": 60},
    ]
    return make_nat(rows), make_legacy_reg(rows)


@pytest.mark.characterization
@pytest.mark.parametrize(
    "func_name",
    ["get_hoseo_trend", "get_rank_changes", "get_compare_group_data"],
)
def test_dl_u11_legacy_frame_breaks_three_functions(func_name):
    """DL-U11: [특성화, V02 전제] 미변환 레거시 프레임은 3개 함수에서 KeyError('권역순위').

    research.py 의 CSV 업로드 경로가 `_ensure_new_format` 을 거치지 않아 이 경로에 빠진다.
    """
    national, legacy = _legacy_pair()
    assert "권역순위" not in legacy.columns

    kwargs = {"university": "호서대학교"}
    args = (national, legacy)
    if func_name == "get_compare_group_data":
        args = (national, legacy, 2025)
        kwargs = {"compare_group": ["호서대학교", "순천향대학교"]}

    with pytest.raises(KeyError) as excinfo:
        getattr(dl, func_name)(*args, **kwargs)

    assert excinfo.value.args[0] == "권역순위"


@pytest.mark.characterization
def test_dl_u11_legacy_frame_still_works_for_averages_and_yoy():
    """DL-U11: [특성화, V02 전제] 권역순위를 안 쓰는 2개 함수는 레거시에서도 동작한다."""
    national, legacy = _legacy_pair()

    averages = dl.get_averages(national, legacy, compare_group=["호서대학교"], region_name="충청권")
    assert set(averages.keys()) == {2024, 2025}
    # '권역명' 컬럼이 없으므로 region_name 필터가 무시되고 레거시 프레임 전체가 쓰인다.
    reg_2025 = legacy[legacy["연도"] == 2025]
    assert averages[2025]["권역평균"] == round(float(reg_2025["1인당논문수"].mean()), 4)

    yoy = dl.get_yoy_changes(legacy, 2025, university="호서대학교", region_name="충청권")
    assert yoy["호서"] is not None
    assert yoy["호서"]["학교명"] == "호서대학교"
    assert yoy["호서"]["증감률"] == 100.0


# ===========================================================================
# DL-U12  결측값·타입
# ===========================================================================

@pytest.mark.characterization
def test_dl_u12_nan_faculty_count_raises_valueerror():
    """DL-U12: [특성화] 전임교원수가 NaN 이면 int() 변환에서 ValueError 가 난다.

    data_loader.py:157 에 결측 가드가 없어 예외가 그대로 호출자에게 전파된다.
    """
    national = make_nat([{"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20}])
    national.loc[0, "전임교원수"] = np.nan
    regional = make_reg([{"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20}])

    with pytest.raises(ValueError, match="NaN"):
        dl.get_hoseo_trend(national, regional, university="호서대학교", region_name="충청권")


def test_dl_u12_available_years_are_python_ints_and_sorted():
    """DL-U12: get_available_years 원소가 numpy 정수가 아닌 python int 이고 오름차순이다."""
    national = make_nat(
        [
            {"year": 2025, "name": "호서대학교", "교원": 100, "논문": 20},
            {"year": 2023, "name": "호서대학교", "교원": 100, "논문": 10},
            {"year": 2024, "name": "호서대학교", "교원": 100, "논문": 15},
            {"year": 2024, "name": "순천향대학교", "교원": 200, "논문": 40},
        ]
    )

    years = dl.get_available_years(national)

    assert years == [2023, 2024, 2025], "중복 제거 + 오름차순"
    assert all(type(year) is int for year in years), "numpy.int64 가 아닌 python int 여야 한다"
    assert not any(isinstance(year, np.generic) for year in years)


def test_dl_u12_available_years_on_empty_frame():
    """DL-U12: 빈 프레임이면 빈 리스트를 반환한다(예외 없음)."""
    empty = make_nat([]).astype({"연도": "int64"})

    assert dl.get_available_years(empty) == []
