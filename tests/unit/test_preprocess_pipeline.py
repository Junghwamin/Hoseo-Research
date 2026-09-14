"""전처리 파이프라인 순수 함수 계약 — ETL-U05~U11, ETL-C01.

대상: 전임교원_연구실적_전처리.py
  - calculate_metrics   :434-443
  - calculate_rankings  :449-514
  - merge_campuses      :369-428
  - filter_universities :358-363
  - scan_raw_files      :94-117
  - load_config         :51-88
  - export_csv/excel    :520-625
  - REGION_MAP          :38-45

`main()` 과 `process_in_memory()` 는 디스크 쓰기가 발생하므로 여기서 호출하지 않는다
(Phase 2 통합 테스트 담당). ETL-U09 의 정규식 대조만 소스 정적 분석으로 처리한다.
"""

from __future__ import annotations

import ast
import inspect
import re
import unicodedata

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
_METRIC_COLUMNS = ["학교명", "전임교원수", "SCI논문수"]


def _metric_frame(rows: list[tuple]) -> pd.DataFrame:
    """(학교명, 전임교원수, SCI논문수) 튜플 목록으로 calculate_metrics 입력을 만든다."""
    return pd.DataFrame(rows, columns=_METRIC_COLUMNS)


def _ranking_frame(rows: list[tuple]) -> pd.DataFrame:
    """(학교명, 1인당논문수) 튜플 목록으로 calculate_rankings 입력을 만든다."""
    frame = pd.DataFrame(rows, columns=["학교명", "1인당논문수"])
    frame["전임교원수"] = 100.0
    frame["SCI논문수"] = frame["1인당논문수"] * 100.0
    return frame[["학교명", "전임교원수", "SCI논문수", "1인당논문수"]]


def _export_national(year_rows: list[tuple]) -> pd.DataFrame:
    """export_csv/export_excel 이 요구하는 전국 프레임 5개 컬럼을 만든다."""
    frame = pd.DataFrame(
        year_rows, columns=["학교명", "전임교원수", "SCI논문수", "1인당논문수", "전국순위"]
    )
    return frame


def _export_region(year_rows: list[tuple]) -> pd.DataFrame:
    """export_csv/export_excel 이 요구하는 권역 프레임 7개 컬럼을 만든다."""
    return pd.DataFrame(
        year_rows,
        columns=[
            "학교명",
            "전임교원수",
            "SCI논문수",
            "1인당논문수",
            "권역명",
            "권역순위",
            "전국순위",
        ],
    )


# ---------------------------------------------------------------------------
# ETL-U05 : calculate_metrics
# ---------------------------------------------------------------------------
def test_etl_u05_calculate_metrics(pp_module):
    """ETL-U05: 1인당논문수 = 내장 round(논문/교원, 4), 교원 0 → 0.0, 입력 불변."""
    source = _metric_frame(
        [
            ("A", 100.0, 20.0),
            ("B", 0.0, 10.0),      # (b) 분모 0 → 0.0 (ZeroDivisionError 아님)
            ("C", 510.0, 56.5845),  # (c) 내장 round 경계
            ("D", 3.0, 1.0),
        ]
    )
    before = source.copy(deep=True)

    result = pp_module.calculate_metrics(source)

    # (a) 내장 round(논문/교원, 4) 와 정확히 일치
    for name, faculty, papers in before.itertuples(index=False):
        expected = round(papers / faculty, 4) if faculty > 0 else 0.0
        actual = result.loc[result["학교명"] == name, "1인당논문수"].iloc[0]
        assert actual == pytest.approx(expected, abs=0.0), f"{name} 1인당논문수 불일치"

    # (b) 전임교원수 0 → 0.0
    assert result.loc[result["학교명"] == "B", "1인당논문수"].iloc[0] == 0.0

    # (c) 내장 round 와 numpy round 가 갈리는 지점을 명시적으로 대조한다.
    #     56.5845 / 510 = 0.11095 → 내장 round: 0.1109 / numpy round: 0.111
    quotient = 56.5845 / 510
    assert round(quotient, 4) == 0.1109
    assert float(np.round(quotient, 4)) == 0.111
    assert result.loc[result["학교명"] == "C", "1인당논문수"].iloc[0] == 0.1109, (
        "numpy 반올림(0.111)이 아니라 파이썬 내장 round(0.1109) 여야 한다"
    )

    # (e) 입력 DataFrame 은 건드리지 않는다 (copy 반환)
    assert result is not source
    assert "1인당논문수" not in source.columns, "입력 프레임에 컬럼이 추가되었다"
    pd.testing.assert_frame_equal(source, before)


def test_etl_u05_calculate_metrics_empty_frame(pp_module):
    """ETL-U05(d): 빈 DataFrame 을 넣어도 예외 없이 1인당논문수 컬럼이 생긴다."""
    empty = _metric_frame([])
    result = pp_module.calculate_metrics(empty)

    assert len(result) == 0
    assert list(result.columns) == _METRIC_COLUMNS + ["1인당논문수"]


# ---------------------------------------------------------------------------
# ETL-U06 : calculate_rankings
# ---------------------------------------------------------------------------
def test_etl_u06_national_rank_is_min_method_int(pp_module):
    """ETL-U06: 전국순위는 1인당논문수 내림차순 method='min' 정수 순위다."""
    frame = _ranking_frame([("A", 1.0), ("B", 1.0), ("C", 0.5), ("D", 0.5), ("E", 0.0)])

    national, _regional = pp_module.calculate_rankings(frame)

    assert pd.api.types.is_integer_dtype(national["전국순위"]), "전국순위가 정수형이 아니다"
    ranks = dict(zip(national["학교명"], national["전국순위"]))
    assert ranks == {"A": 1, "B": 1, "C": 3, "D": 3, "E": 5}, f"동점 처리가 달라졌다: {ranks}"

    # 전국 프레임은 전국순위 오름차순으로 정렬되어 나온다 (전처리.py:512)
    assert national["전국순위"].tolist() == sorted(national["전국순위"].tolist())


def test_etl_u06_multi_region_university_gets_one_row_per_region(pp_module):
    """ETL-U06: univ_region_map 의 다중권역 대학은 권역마다 1행, 전국순위는 전국 프레임과 동일."""
    frame = _ranking_frame([("A", 1.0), ("B", 1.0), ("C", 0.5), ("D", 0.5), ("E", 0.0)])
    univ_region_map = {"A": ["수도권", "충청권"], "B": ["충청권"]}

    national, regional = pp_module.calculate_rankings(
        frame, univ_region_map=univ_region_map
    )

    # 권역 프레임에는 매핑된 대학만 등장한다.
    assert set(regional["학교명"]) == {"A", "B"}
    assert len(regional) == 3, "A 2행(수도권·충청권) + B 1행(충청권) 이어야 한다"

    pairs = set(zip(regional["학교명"], regional["권역명"]))
    assert pairs == {("A", "수도권"), ("A", "충청권"), ("B", "충청권")}

    # 각 행의 전국순위는 전국 프레임의 값과 같아야 한다.
    national_ranks = dict(zip(national["학교명"], national["전국순위"]))
    for name, rank in zip(regional["학교명"], regional["전국순위"]):
        assert rank == national_ranks[name], f"{name} 전국순위가 권역 프레임에서 달라졌다"

    # 권역순위는 권역 내부에서 다시 매겨진다 (수도권은 A 혼자 → 1위)
    lookup = {
        (row["학교명"], row["권역명"]): row["권역순위"]
        for _, row in regional.iterrows()
    }
    assert lookup[("A", "수도권")] == 1
    assert lookup[("A", "충청권")] == 1
    assert lookup[("B", "충청권")] == 1  # A 와 동점

    # 정렬 키는 [권역명, 권역순위] 오름차순 (동점 행의 상대 순서는 단언하지 않는다)
    keys = list(zip(regional["권역명"], regional["권역순위"]))
    assert keys == sorted(keys), f"[권역명, 권역순위] 정렬이 깨졌다: {keys}"
    assert pd.api.types.is_integer_dtype(regional["권역순위"])


@pytest.mark.parametrize("empty_map", [None, {}])
def test_etl_u06_legacy_path_fixes_region_name_to_chungcheong(pp_module, empty_map):
    """ETL-U06: univ_region_map 이 None/{} 이면 region_names 기반 레거시 경로를 탄다."""
    frame = _ranking_frame([("A", 1.0), ("B", 0.8), ("C", 0.5)])

    _national, regional = pp_module.calculate_rankings(
        frame, region_names=["A", "C"], univ_region_map=empty_map
    )

    assert set(regional["학교명"]) == {"A", "C"}, "region_names 밖의 대학이 섞였다"
    assert set(regional["권역명"]) == {"충청권"}, "레거시 경로의 권역명은 '충청권' 고정이다"
    assert dict(zip(regional["학교명"], regional["권역순위"])) == {"A": 1, "C": 2}
    assert regional["권역순위"].tolist() == [1, 2], "권역순위 오름차순 정렬이어야 한다"


def test_etl_u06_empty_region_names_yields_empty_regional_frame(pp_module):
    """ETL-U06: 레거시 경로에서 region_names 가 비면 권역 프레임이 비어 나온다."""
    frame = _ranking_frame([("A", 1.0), ("B", 0.5)])

    _national, regional = pp_module.calculate_rankings(frame)

    assert regional.empty
    assert "권역명" in regional.columns and "권역순위" in regional.columns


@pytest.mark.characterization
def test_etl_u06_nan_metric_raises_int_casting_error(pp_module):
    """ETL-U06[특성화]: 1인당논문수에 NaN 이 섞이면 IntCastingNaNError 로 터진다.

    rank() 가 NaN 을 NaN 순위로 남기고 곧바로 .astype(int) 하기 때문이다
    (전처리.py:471-473). 현행 동작을 기록만 한다.
    """
    frame = _ranking_frame([("A", 1.0), ("B", 0.5)])
    frame.loc[1, "1인당논문수"] = np.nan

    with pytest.raises(pd.errors.IntCastingNaNError):
        pp_module.calculate_rankings(frame)


# ---------------------------------------------------------------------------
# ETL-U07 : merge_campuses
# ---------------------------------------------------------------------------
def test_etl_u07_merge_campuses_sums_aliases_and_collects_regions(pp_module, capsys):
    """ETL-U07: 별칭 캠퍼스를 정규명으로 합산하고 권역 목록을 등장 순서대로 모은다."""
    df = pd.DataFrame(
        {
            "학교명": ["단국대학교", "단국대학교(천안)", "미등록대학교"],
            "학교종류": ["대학교", "대학교", "대학교"],
            "지역": ["경기", "충남", "서울"],
            "전임교원수": [100.0, 50.0, 10.0],
            "SCI논문수": [20.0, 5.0, 1.0],
        }
    )
    name_mapping = {"단국대학교": "단국대학교", "단국대학교(천안)": "단국대학교"}

    _res = pp_module.merge_campuses(df, name_mapping)  # 반환 길이에 중립 (V14 로 3-튜플이 됨)
    merged, univ_region_map = _res[0], _res[1]

    # 캠퍼스 2행 → 1행, 교원·논문 합산
    assert list(merged.columns) == ["학교명", "전임교원수", "SCI논문수"]
    assert len(merged) == 1
    assert merged["학교명"].iloc[0] == "단국대학교"
    assert merged["전임교원수"].iloc[0] == pytest.approx(150.0)
    assert merged["SCI논문수"].iloc[0] == pytest.approx(25.0)

    # 다중 캠퍼스는 모든 권역에 등록된다 (등장 순서: 경기→수도권, 충남→충청권)
    assert univ_region_map == {"단국대학교": ["수도권", "충청권"]}

    # 미매핑 학교는 결과에서 빠지고 경고가 표준출력으로 나간다
    assert "미등록대학교" not in set(merged["학교명"])
    captured = capsys.readouterr().out
    assert "[경고]" in captured
    assert "미등록대학교" in captured
    assert "universities.json" in captured


def test_etl_u07_merge_campuses_without_region_column(pp_module, capsys):
    """ETL-U07: '지역' 컬럼이 없으면 합산은 되고 univ_region_map 은 빈 dict 다."""
    df = pd.DataFrame(
        {
            "학교명": ["단국대학교", "단국대학교(천안)"],
            "학교종류": ["대학교", "대학교"],
            "전임교원수": [100.0, 50.0],
            "SCI논문수": [20.0, 5.0],
        }
    )
    name_mapping = {"단국대학교": "단국대학교", "단국대학교(천안)": "단국대학교"}

    _res = pp_module.merge_campuses(df, name_mapping)  # 반환 길이에 중립 (V14 로 3-튜플이 됨)
    merged, univ_region_map = _res[0], _res[1]
    capsys.readouterr()

    assert univ_region_map == {}
    assert len(merged) == 1
    assert merged["전임교원수"].iloc[0] == pytest.approx(150.0)


def test_etl_u07_merge_campuses_ignores_unknown_region_codes(pp_module, capsys):
    """ETL-U07: REGION_MAP 에 없는 시도 값은 권역 목록에 들어가지 않는다."""
    df = pd.DataFrame(
        {
            "학교명": ["호서대학교"],
            "학교종류": ["대학교"],
            "지역": ["해외"],
            "전임교원수": [10.0],
            "SCI논문수": [1.0],
        }
    )

    _res = pp_module.merge_campuses(df, {"호서대학교": "호서대학교"})  # 반환 길이에 중립 (V14 로 3-튜플이 됨)
    merged, univ_region_map = _res[0], _res[1]
    capsys.readouterr()

    assert len(merged) == 1, "권역 미상이어도 합산 결과에는 남는다"
    assert univ_region_map == {}


# ---------------------------------------------------------------------------
# ETL-U08 : filter_universities (특성화)
# ---------------------------------------------------------------------------
@pytest.mark.characterization
def test_etl_u08_filter_universities_keeps_only_daehakgyo(pp_module):
    """ETL-U08[특성화]: 학교종류 '대학교'만 남기고 'nan'/빈 문자열 행을 버린 뒤 인덱스를 리셋한다.

    '산업대학'(청운대·호원대)·'전문대학'이 통째로 빠지는 현행 동작을 기록한다.
    """
    df = pd.DataFrame(
        {
            "학교명": [
                "호서대학교",
                "청운대학교",
                "호원대학교",
                "어느전문대학",
                "",
                "nan",
                "순천향대학교",
            ],
            "학교종류": [
                "대학교",
                "산업대학",
                "산업대학",
                "전문대학",
                "대학교",
                "대학교",
                "대학교",
            ],
            "전임교원수": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            "SCI논문수": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        }
    )

    result = pp_module.filter_universities(df)

    assert result["학교명"].tolist() == ["호서대학교", "순천향대학교"]
    assert set(result["학교종류"]) == {"대학교"}
    # '산업대학'으로 분류된 대학은 종류 필터에서 통째로 빠진다.
    assert "청운대학교" not in set(result["학교명"])
    assert "호원대학교" not in set(result["학교명"])
    # 문자열 'nan'(astype(str) 결과)과 빈 문자열이 제거된다.
    assert "" not in set(result["학교명"]) and "nan" not in set(result["학교명"])
    # 인덱스는 0..N-1 로 리셋된다.
    assert result.index.tolist() == [0, 1]


# ---------------------------------------------------------------------------
# ETL-U09 : scan_raw_files
# ---------------------------------------------------------------------------
def test_etl_u09_scan_raw_files(pp_module, tmp_path):
    """ETL-U09: 'YYYY년' 또는 'YYYY_' 패턴 xlsx 를 연도 오름차순으로 수집한다.

    R-ETL-03 수정으로 디스크 스캔과 업로드 처리(process_in_memory)가 같은
    연도 정규식을 쓴다. 이전에는 스캔만 'YYYY년' 을 요구해 `2022_c.xlsx` 를
    무시했는데, 같은 파일이 업로드로는 처리되어 사용자가 결과 차이를 겪었다.
    엄격한 쪽으로 통일하면 지금 되던 업로드가 거부되는 회귀이므로
    관대한 쪽으로 맞췄다.
    """
    nfd_name = unicodedata.normalize("NFD", "2023년_b.xlsx")
    for name in ("2024년_a.xlsx", nfd_name, "no_year.xlsx", "2022_c.xlsx", "x.csv"):
        (tmp_path / name).touch()

    result = pp_module.scan_raw_files(tmp_path)

    assert list(result.keys()) == [2022, 2023, 2024], f"연도 추출/정렬이 깨졌다: {list(result)}"
    assert unicodedata.normalize("NFC", result[2022].name) == "2022_c.xlsx"
    assert unicodedata.normalize("NFC", result[2023].name) == "2023년_b.xlsx"
    assert unicodedata.normalize("NFC", result[2024].name) == "2024년_a.xlsx"
    # 빈 파일이므로 내용은 읽지 않는다 (파일명만 본다)
    assert all(path.stat().st_size == 0 for path in result.values())

    # NFC 정규화(전처리.py:110)가 필요한 이유: NFD 문자열은 '년' 리터럴과 매칭되지 않는다.
    pattern = re.compile(r"(\d{4})년")
    assert pattern.search(nfd_name) is None, "NFD 이름이 그대로 매칭되면 정규화가 불필요하다"
    assert pattern.search(unicodedata.normalize("NFC", nfd_name)) is not None


# ---------------------------------------------------------------------------
# ETL-U10 : load_config + config JSON 무결성
# ---------------------------------------------------------------------------
def test_etl_u10_load_config_and_json_integrity(pp_module, project_root):
    """ETL-U10: config/*.json 의 개수·자기매핑·alias 유일성·지역 참조 무결성을 고정한다."""
    universities, name_mapping, regions = pp_module.load_config(project_root / "config")

    # 실제로 센 값 (2026-09 기준 config/)
    assert len(universities) == 136, f"universities 개수가 달라졌다: {len(universities)}"
    assert len(name_mapping) == 164, f"name_mapping 항목 수가 달라졌다: {len(name_mapping)}"
    assert set(regions.keys()) == {"충청권"}, f"regions 키가 달라졌다: {set(regions)}"
    assert len(regions["충청권"]) == 27, f"충청권 대학 수가 달라졌다: {len(regions['충청권'])}"
    assert "description" not in regions, "description 키는 제외되어야 한다"

    # canonical 이름은 자기 자신으로도 매핑된다 (전처리.py:77)
    canonical_names = [uni["name"] for uni in universities]
    for name in canonical_names:
        assert name_mapping[name] == name, f"{name} 자기매핑이 없다"

    # alias 는 canonical 포함 전체에서 유일해야 한다 (충돌 시 조용히 덮어써진다)
    all_keys: list[str] = []
    for uni in universities:
        all_keys.append(uni["name"])
        all_keys.extend(uni.get("aliases", []))
    duplicates = sorted({key for key in all_keys if all_keys.count(key) > 1})
    assert duplicates == [], f"중복된 이름/별칭: {duplicates}"
    assert len(all_keys) == len(name_mapping), "덮어쓰기로 항목이 유실되었다"

    # regions.json 의 모든 학교명이 universities 의 name 에 존재해야 한다
    name_set = set(canonical_names)
    for region_name, members in regions.items():
        missing = [member for member in members if member not in name_set]
        assert missing == [], f"{region_name} 에 universities 미등록 학교: {missing}"

    # 도출 가능한 권역명은 모두 모듈 REGION_MAP 의 값 집합에 포함된다
    assert set(regions.keys()) <= set(pp_module.REGION_MAP.values())


# ---------------------------------------------------------------------------
# ETL-U11 : export_csv / export_excel
# ---------------------------------------------------------------------------
def _export_fixture():
    """연도·순위가 일부러 뒤섞인 2개년 입력을 만든다."""
    national_2024 = _export_national(
        [
            ("B대학교", 200.0, 20.0, 0.1000, 2),
            ("A대학교", 100.0, 30.0, 0.3000, 1),
        ]
    )
    national_2025 = _export_national(
        [
            ("A대학교", 100.0, 10.0, 0.1000, 2),
            ("B대학교", 200.0, 60.0, 0.3000, 1),
        ]
    )
    region_2024 = _export_region(
        [
            ("A대학교", 100.0, 30.0, 0.3000, "충청권", 1, 1),
            ("B대학교", 200.0, 20.0, 0.1000, "수도권", 1, 2),
        ]
    )
    region_2025 = _export_region(
        [
            ("B대학교", 200.0, 60.0, 0.3000, "수도권", 1, 1),
            ("A대학교", 100.0, 10.0, 0.1000, "충청권", 1, 2),
        ]
    )
    # 연도 순서도 뒤집어 넣어 정렬 단언이 실제로 작동하게 한다.
    return (
        [(2025, national_2025), (2024, national_2024)],
        [(2025, region_2025), (2024, region_2024)],
    )


def test_etl_u11_export_csv_renames_sorts_and_writes_legacy(pp_module, tmp_path, capsys):
    """ETL-U11: export_csv 가 컬럼 rename·연도 0열·정렬·충청권 하위호환 파일을 보장한다."""
    all_national, all_region = _export_fixture()

    pp_module.export_csv(all_national, all_region, tmp_path)
    capsys.readouterr()

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "권역별_순위.csv",
        "전체_대학_데이터.csv",
        "충청권_순위.csv",
    ]

    national = pd.read_csv(tmp_path / "전체_대학_데이터.csv", encoding="utf-8-sig")
    assert list(national.columns) == [
        "연도",
        "학교명",
        "전임교원수",
        "SCI/SCOPUS논문수",
        "1인당논문수",
        "전국순위",
    ], "SCI논문수 → SCI/SCOPUS논문수 rename 또는 연도 0열 배치가 깨졌다"
    assert list(national.columns)[0] == "연도"
    assert "SCI논문수" not in national.columns
    assert list(zip(national["연도"], national["전국순위"])) == [
        (2024, 1),
        (2024, 2),
        (2025, 1),
        (2025, 2),
    ], "[연도, 전국순위] 정렬이 아니다"
    assert national.loc[0, "학교명"] == "A대학교"
    assert national.loc[2, "학교명"] == "B대학교"

    regional = pd.read_csv(tmp_path / "권역별_순위.csv", encoding="utf-8-sig")
    assert list(regional.columns) == [
        "연도",
        "학교명",
        "전임교원수",
        "SCI/SCOPUS논문수",
        "1인당논문수",
        "권역명",
        "권역순위",
        "전국순위",
    ]
    assert list(zip(regional["연도"], regional["권역명"], regional["권역순위"])) == [
        (2024, "수도권", 1),
        (2024, "충청권", 1),
        (2025, "수도권", 1),
        (2025, "충청권", 1),
    ], "[연도, 권역명, 권역순위] 정렬이 아니다"

    legacy = pd.read_csv(tmp_path / "충청권_순위.csv", encoding="utf-8-sig")
    assert list(legacy.columns) == [
        "연도",
        "학교명",
        "전임교원수",
        "SCI/SCOPUS논문수",
        "1인당논문수",
        "충청권순위",
        "전국순위",
    ], "레거시 파일은 권역명을 버리고 권역순위 → 충청권순위 로 rename 한다"
    assert "권역명" not in legacy.columns
    assert legacy["학교명"].tolist() == ["A대학교", "A대학교"]
    assert legacy["연도"].tolist() == [2024, 2025]


def test_etl_u11_export_csv_skips_legacy_file_when_no_chungcheong(pp_module, tmp_path, capsys):
    """ETL-U11: 충청권 행이 하나도 없으면 충청권_순위.csv 를 만들지 않는다(전처리.py:617)."""
    national = _export_national([("A대학교", 100.0, 30.0, 0.3000, 1)])
    region = _export_region([("A대학교", 100.0, 30.0, 0.3000, "수도권", 1, 1)])

    pp_module.export_csv([(2025, national)], [(2025, region)], tmp_path)
    capsys.readouterr()

    written = sorted(path.name for path in tmp_path.iterdir())
    assert written == ["권역별_순위.csv", "전체_대학_데이터.csv"]
    assert not (tmp_path / "충청권_순위.csv").exists()


def test_etl_u11_export_excel_two_sheets(pp_module, tmp_path, capsys):
    """ETL-U11: export_excel 은 rename·연도 0열·정렬을 유지한 2개 시트를 쓴다."""
    all_national, all_region = _export_fixture()
    target = tmp_path / "결과.xlsx"

    pp_module.export_excel(all_national, all_region, target)
    capsys.readouterr()

    assert target.exists()
    with pd.ExcelFile(target) as workbook:
        assert workbook.sheet_names == ["전체_대학_데이터", "권역별_순위"]
        national = pd.read_excel(workbook, sheet_name="전체_대학_데이터")
        regional = pd.read_excel(workbook, sheet_name="권역별_순위")

    assert list(national.columns) == [
        "연도",
        "학교명",
        "전임교원수",
        "SCI/SCOPUS논문수",
        "1인당논문수",
        "전국순위",
    ]
    assert list(zip(national["연도"], national["전국순위"])) == [
        (2024, 1),
        (2024, 2),
        (2025, 1),
        (2025, 2),
    ]
    assert list(regional.columns)[0] == "연도"
    assert "SCI/SCOPUS논문수" in regional.columns and "SCI논문수" not in regional.columns
    assert list(zip(regional["연도"], regional["권역명"], regional["권역순위"])) == [
        (2024, "수도권", 1),
        (2024, "충청권", 1),
        (2025, "수도권", 1),
        (2025, "충청권", 1),
    ]


# ---------------------------------------------------------------------------
# ETL-C01 : REGION_MAP 동일성 계약
# ---------------------------------------------------------------------------
def test_etl_c01_region_map_matches_report_app_config(pp_module, project_root):
    """ETL-C01: 전처리와 report_app/config.py 의 REGION_MAP 이 완전히 동일해야 한다.

    config.py 는 import 시 Path.cwd() 를 평가하므로(:80) 여기서는 import 하지 않고
    ast.literal_eval 로 소스에서 리터럴만 추출해 비교한다.
    """
    config_py = project_root / "report_app" / "config.py"
    assert config_py.exists(), f"config.py 를 찾을 수 없다: {config_py}"

    tree = ast.parse(config_py.read_text(encoding="utf-8"))
    extracted = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "REGION_MAP"
            for target in node.targets
        ):
            extracted = ast.literal_eval(node.value)
            break

    assert extracted is not None, "config.py 에서 REGION_MAP 대입을 찾지 못했다"
    assert extracted == pp_module.REGION_MAP, (
        "전처리와 config.py 의 REGION_MAP 이 갈라졌다. "
        f"전처리에만 있음={set(pp_module.REGION_MAP) - set(extracted)}, "
        f"config 에만 있음={set(extracted) - set(pp_module.REGION_MAP)}"
    )
    assert len(extracted) == 17, f"17개 시도여야 한다: {len(extracted)}"
    assert set(extracted.values()) == {
        "수도권",
        "강원권",
        "충청권",
        "호남권",
        "영남권",
        "제주권",
    }
    assert len(set(extracted.values())) == 6
