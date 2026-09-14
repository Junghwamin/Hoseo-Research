"""전처리(preprocess) 스크립트 실데이터 골든·통합 테스트 (ETL-C01b/C02/C03, ETL-I01~I05).

이 파일의 골든 기준값은 **Phase 4 수정 이후**의 값이다.

* **V01 수정 완료** — 2017년 Raw 는 SCI/SCOPUS 그룹에 '계' 하위 헤더가 없고
  '남'/'여' 두 열뿐이다. 이제 두 열을 합산한다(호서대학교 2017 = 77.3614).
  수정 전에는 '남' 열만 집계해 61.4167 이었다.
* **V20 수정 완료** — 모든 정렬의 마지막 키에 `학교명` 이 붙어 동순위 행 순서가
  결정적이다. 따라서 골든 비교에서 행 순서까지 단언할 수 있다.
* **V14 는 수치를 바꾸지 않았다** — `merge_campuses` 가 제외 대학 목록을
  반환·출력하게만 했다. '전국순위/전국평균'은 여전히 **등재 사립 134개교 기준**이며,
  이는 사용자 결정("현행 유지 + 라벨 명시")에 따른 것이다. 보고서 §4 V14 참조.

`output/*.csv` 는 2026-09-14 에 위 수정 반영본으로 재생성했다.
재생성 검증: `(연도, 학교명)` 기준 값 비교에서 **2017년 행만** 달라졌다.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from report_app.report_builder import build_report
from tests.conftest import PROJECT_ROOT, RAW_AVAILABLE, RAW_DIR, REALDATA_AVAILABLE
from tests.fixtures.tiny_png import fake_charts

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

#: 전처리.py:106 `scan_raw_files` 의 연도 정규식
SCAN_YEAR_PATTERN = re.compile(r"(\d{4})년")

#: 전처리.py:676 `process_in_memory` 의 연도 정규식
IN_MEMORY_YEAR_PATTERN = re.compile(r"(\d{4})(?:년|_)")

#: 전처리.py:38-45 REGION_MAP 이 만들 수 있는 6개 권역
ALL_REGIONS = {"수도권", "강원권", "충청권", "호남권", "영남권", "제주권"}

NATIONAL_COLUMNS = ["연도", "학교명", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수", "전국순위"]
REGIONAL_COLUMNS = [
    "연도", "학교명", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수",
    "권역명", "권역순위", "전국순위",
]
LEGACY_CHUNGCHEONG_COLUMNS = [
    "연도", "학교명", "전임교원수", "SCI/SCOPUS논문수", "1인당논문수",
    "충청권순위", "전국순위",
]

UTF8_BOM = b"\xef\xbb\xbf"


def _raw_path(year: int) -> Path:
    """`Raw data/` 에서 해당 연도 xlsx 경로를 찾는다(NFC 정규화 포함)."""
    for path in sorted(RAW_DIR.glob("*.xlsx")):
        match = SCAN_YEAR_PATTERN.search(unicodedata.normalize("NFC", path.name))
        if match and int(match.group(1)) == year:
            return path
    pytest.skip(f"{year}년 Raw 파일을 찾을 수 없다: {RAW_DIR}")


def _raw_bytes(*years: int) -> dict[str, bytes]:
    """`process_in_memory` 에 넘길 {파일명: bytes} 를 만든다."""
    files: dict[str, bytes] = {}
    for year in years:
        path = _raw_path(year)
        files[path.name] = path.read_bytes()
    return files


def _canonical(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """동순위(tie) 행 순서 차이를 제거한 비교용 프레임.

    전처리.py:512 는 `sort_values("전국순위")` 를 타이브레이커(tie-breaker) 없이
    기본 정렬(불안정 정렬, unstable sort)로 수행하므로, 같은 순위 행들의
    상대 순서가 실행 환경(numpy 버전)에 따라 달라질 수 있다.
    값 자체의 동일성만 비교하기 위해 결정적인 키로 재정렬한다.
    """
    return frame.sort_values(keys).reset_index(drop=True)


def _run_main_in(tmp_path: Path, monkeypatch, pp_module, years=(2024, 2025)) -> Path:
    """임시 cwd 에서 `main()` 을 1회 실행하고 생성된 output 디렉터리를 돌려준다.

    `main()` 은 `Path.cwd()/"Raw data"` 를 읽고 `Path.cwd()/"output"` 에 쓴다
    (전처리.py:783-784). 실제 프로젝트 `output/` 을 덮어쓰지 않도록
    반드시 tmp_path 로 chdir 한 뒤 실행해야 한다.
    """
    raw_dir = tmp_path / "Raw data"
    raw_dir.mkdir()
    for year in years:
        src = _raw_path(year)
        shutil.copy2(src, raw_dir / src.name)

    monkeypatch.chdir(tmp_path)
    assert Path.cwd() == tmp_path, "cwd 가 tmp_path 로 바뀌지 않았다 — 실행을 중단한다"

    pp_module.main()

    output_dir = tmp_path / "output"
    assert output_dir.is_dir(), "main() 이 output 디렉터리를 만들지 않았다"
    return output_dir


def _document_text(buf: BytesIO) -> str:
    """생성된 docx 의 단락·표 셀 텍스트를 모두 이어붙인다."""
    from docx import Document

    doc = Document(BytesIO(buf.getvalue()))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# ETL-C02 / ETL-C03 / ETL-C01b — process_in_memory 계약
# ---------------------------------------------------------------------------

@pytest.mark.realdata
@pytest.mark.characterization
@pytest.mark.skipif(not RAW_AVAILABLE, reason="Raw data/*.xlsx 없음")
def test_process_in_memory_returns_documented_columns(pp_module, capsys):
    """ETL-C02: `process_in_memory` 가 돌려주는 두 프레임의 컬럼·규모·권역을 고정한다.

    주의(docstring 불일치): 전처리.py:655 는 regional_df 컬럼을
    `연도, 학교명, 전임교원수, SCI/SCOPUS논문수, 1인당논문수, 충청권순위, 전국순위`
    라고 적고 있으나, 실제 반환 컬럼은 `권역명`·`권역순위` 를 쓰는 8개 컬럼이다
    (전처리.py:764 에서 선택하는 컬럼이 곧 계약). docstring 이 레거시 포맷에
    멈춰 있는 것이며, 이 테스트는 **실제 반환 포맷** 쪽을 고정한다.
    """
    national_df, regional_df = pp_module.process_in_memory(_raw_bytes(2024, 2025))
    capsys.readouterr()  # merge_campuses 의 미매핑 경고 출력 흡수

    assert list(national_df.columns) == NATIONAL_COLUMNS, "national_df 컬럼 계약이 깨졌다"
    assert list(regional_df.columns) == REGIONAL_COLUMNS, "regional_df 컬럼 계약이 깨졌다"

    assert sorted(national_df["연도"].unique().tolist()) == [2024, 2025]

    # 연도별 대학 수와 전국순위 범위 (V14 로 등재 사립 134개교만 남은 현재 값)
    year_2025 = national_df[national_df["연도"] == 2025]
    year_2024 = national_df[national_df["연도"] == 2024]
    assert len(year_2025) == 134, "2025년 대학 수가 등재 사립 134개교와 다르다"
    assert len(year_2024) == 134, "2024년 대학 수가 등재 사립 134개교와 다르다"
    assert int(year_2025["전국순위"].min()) == 1
    assert int(year_2025["전국순위"].max()) == 128, "2025년 최하위 순위(동순위 압축 결과)"
    assert int(year_2024["전국순위"].min()) == 1
    assert int(year_2024["전국순위"].max()) == 126, "2024년 최하위 순위(동순위 압축 결과)"

    # 권역명은 REGION_MAP 이 만들 수 있는 6개 권역의 부분집합이어야 한다
    regions = set(regional_df["권역명"].unique())
    assert regions <= ALL_REGIONS, f"알 수 없는 권역명: {regions - ALL_REGIONS}"
    assert regions == ALL_REGIONS, "2024·2025 실데이터는 6개 권역을 모두 포함한다"


@pytest.mark.characterization
def test_process_in_memory_empty_input_raises_pandas_concat_error(pp_module):
    """ETL-C03: 빈 입력은 전처리 자체 검증이 아니라 pandas concat 에서 터진다.

    `process_in_memory({})` 는 연도 루프를 한 번도 돌지 않아 national_frames 가
    빈 리스트가 되고, 전처리.py:756 `pd.concat([])` 이 ValueError 를 던진다.
    즉 "입력이 비었다"는 도메인 메시지가 아니라 라이브러리 메시지가 사용자에게
    그대로 노출된다. 메시지 문구는 pandas(핀 고정 2.3.3) 소유이므로,
    pandas 상향 시 이 테스트가 깨지면 회귀가 아니라 의존성 변경이다.
    """
    with pytest.raises(ValueError, match="No objects to concatenate"):
        pp_module.process_in_memory({})


@pytest.mark.characterization
def test_process_in_memory_rejects_filename_without_year(pp_module):
    """ETL-C03: 연도를 추출할 수 없는 파일명은 ValueError 와 안내 문구로 거부된다."""
    with pytest.raises(ValueError) as excinfo:
        pp_module.process_in_memory({"연도없음.xlsx": b""})

    message = str(excinfo.value)
    assert "연도없음.xlsx" in message, "거부된 파일명이 메시지에 없다"
    assert "연도를 추출할 수 없습니다" in message
    assert "2024년" in message and "2024_" in message, "허용 패턴 안내가 사라졌다"


# ---------------------------------------------------------------------------
# ETL-I01 / ETL-I02 — main() 통합
# ---------------------------------------------------------------------------

@pytest.mark.realdata
@pytest.mark.slow
@pytest.mark.skipif(not RAW_AVAILABLE, reason="Raw data/*.xlsx 없음")
def test_main_writes_excel_and_three_csv(pp_module, tmp_path, monkeypatch, capsys):
    """ETL-I01: `main()` 이 xlsx 1개(시트 2개)와 CSV 3개를 utf-8-sig 로 쓴다."""
    output_dir = _run_main_in(tmp_path, monkeypatch, pp_module)
    capsys.readouterr()  # main() 의 진행 로그 흡수

    produced = sorted(p.name for p in output_dir.iterdir())
    assert produced == [
        "권역별_순위.csv",
        "전임교원_연구실적_전처리결과.xlsx",
        "전체_대학_데이터.csv",
        "충청권_순위.csv",
    ], "main() 산출물 목록이 바뀌었다"

    # --- Excel: 시트 2개 ---
    excel_path = output_dir / "전임교원_연구실적_전처리결과.xlsx"
    with pd.ExcelFile(excel_path) as book:
        assert book.sheet_names == ["전체_대학_데이터", "권역별_순위"], "시트 구성이 바뀌었다"

    # --- CSV: 모두 utf-8-sig BOM ---
    for name in ("전체_대학_데이터.csv", "권역별_순위.csv", "충청권_순위.csv"):
        raw = (output_dir / name).read_bytes()
        assert raw.startswith(UTF8_BOM), f"{name} 에 utf-8-sig BOM 이 없다(한글 Excel 호환 깨짐)"

    national_csv = pd.read_csv(output_dir / "전체_대학_데이터.csv", encoding="utf-8-sig")
    regional_csv = pd.read_csv(output_dir / "권역별_순위.csv", encoding="utf-8-sig")
    legacy_csv = pd.read_csv(output_dir / "충청권_순위.csv", encoding="utf-8-sig")

    assert list(national_csv.columns) == NATIONAL_COLUMNS
    assert list(regional_csv.columns) == REGIONAL_COLUMNS

    # --- 하위 호환 CSV: 권역명 없이 '충청권순위' 사용 (전처리.py:616-624) ---
    assert list(legacy_csv.columns) == LEGACY_CHUNGCHEONG_COLUMNS
    assert "권역명" not in legacy_csv.columns, "레거시 CSV 에 권역명 컬럼이 남았다"
    assert "권역순위" not in legacy_csv.columns
    assert len(legacy_csv) == 58, "충청권 2개년(29개교 × 2) 행 수"


@pytest.mark.realdata
@pytest.mark.slow
@pytest.mark.skipif(not RAW_AVAILABLE, reason="Raw data/*.xlsx 없음")
def test_main_csv_equals_process_in_memory(pp_module, tmp_path, monkeypatch, capsys):
    """ETL-I02: `main()` 의 CSV 와 `process_in_memory` 반환 프레임이 값 단위로 같다.

    연도별 결합 로직이 export_excel(:528-552), export_csv(:579-603),
    process_in_memory(:749-772) 에 3중으로 복제돼 있어 한쪽만 고치면
    조용히 갈라진다. 이 테스트가 그 드리프트(drift) 감시선이다.
    파일 바이트가 아니라 DataFrame 값으로 비교한다(줄바꿈이 OS 의존이므로).
    """
    output_dir = _run_main_in(tmp_path, monkeypatch, pp_module)
    national_mem, regional_mem = pp_module.process_in_memory(_raw_bytes(2024, 2025))
    capsys.readouterr()

    national_csv = pd.read_csv(output_dir / "전체_대학_데이터.csv", encoding="utf-8-sig")
    regional_csv = pd.read_csv(output_dir / "권역별_순위.csv", encoding="utf-8-sig")

    pd.testing.assert_frame_equal(
        _canonical(national_csv, ["연도", "학교명"]),
        _canonical(national_mem, ["연도", "학교명"]),
        check_dtype=False,
        obj="전체_대학_데이터 (main CSV vs process_in_memory)",
    )
    pd.testing.assert_frame_equal(
        _canonical(regional_csv, ["연도", "권역명", "학교명"]),
        _canonical(regional_mem, ["연도", "권역명", "학교명"]),
        check_dtype=False,
        obj="권역별_순위 (main CSV vs process_in_memory)",
    )

    # xlsx 두 시트도 같은 값이어야 한다
    excel_path = output_dir / "전임교원_연구실적_전처리결과.xlsx"
    excel_national = pd.read_excel(excel_path, sheet_name="전체_대학_데이터")
    excel_regional = pd.read_excel(excel_path, sheet_name="권역별_순위")
    pd.testing.assert_frame_equal(
        _canonical(excel_national, ["연도", "학교명"]),
        _canonical(national_csv, ["연도", "학교명"]),
        check_dtype=False,
        obj="전체_대학_데이터 (xlsx vs CSV)",
    )
    pd.testing.assert_frame_equal(
        _canonical(excel_regional, ["연도", "권역명", "학교명"]),
        _canonical(regional_csv, ["연도", "권역명", "학교명"]),
        check_dtype=False,
        obj="권역별_순위 (xlsx vs CSV)",
    )


# ---------------------------------------------------------------------------
# ETL-I03 — git 에 추적된 output/ 골든
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ETL-I04 / ETL-I05 — V14 (전국순위 모집단)
# ---------------------------------------------------------------------------

@pytest.mark.realdata
@pytest.mark.characterization
@pytest.mark.skipif(not RAW_AVAILABLE, reason="Raw data/*.xlsx 없음")
def test_2025_pipeline_drops_57_unlisted_universities(pp_module, capsys):
    """ETL-I04: 2025 Raw 의 단계별 행 수와, 미매핑으로 제외되는 57개교를 고정한다.

    이것이 V14 의 근거 데이터다. '대학교' 209개 중 57개(국립·공립·과기원 등)가
    universities.json 에 없다는 이유로 제외되고 134개교만 남으므로,
    이후 계산되는 '전국순위'와 '전국평균'은 실제 전국이 아니라
    **등재 사립 134개교 안에서의 값**이다.
    """
    universities, name_mapping, regions = pp_module.load_config(PROJECT_ROOT / "config")
    assert len(universities) == 136, "config/universities.json 등재 대학 수"
    assert len(name_mapping) == 164, "alias 를 포함한 이름 매핑 항목 수"

    raw_df = pp_module.read_excel(_raw_path(2025))
    assert len(raw_df) == 242, "read_excel 이 뽑아낸 전체 행 수"
    assert list(raw_df.columns) == ["학교명", "학교종류", "지역", "전임교원수", "SCI논문수"]

    filtered = pp_module.filter_universities(raw_df)
    assert len(filtered) == 209, "학교종류 == '대학교' 필터 후 행 수"

    capsys.readouterr()  # 여기까지의 출력 비우기
    _res = pp_module.merge_campuses(filtered, name_mapping)  # 반환 길이에 중립 (V14 로 3-튜플이 됨)
    merged, univ_region_map = _res[0], _res[1]
    captured = capsys.readouterr()

    assert len(merged) == 134, "캠퍼스 합산 후 남는 대학 수(= 등재 사립 134개교)"
    assert len(univ_region_map) == 134

    # 제외된 학교명 집합
    unmatched = set(filtered["학교명"]) - set(name_mapping)
    assert len(unmatched) == 57, "미매핑으로 제외된 학교 수"
    for name in ("충남대학교", "한국과학기술원", "국립공주대학교", "국립한밭대학교"):
        assert name in unmatched, f"'{name}' 이 제외 목록에 없다 — Raw 표기를 확인하라"

    # 제외 사실은 반환값이 아니라 stdout 경고로만 알려진다 (전처리.py:397-398)
    warnings = [line for line in captured.out.splitlines() if "[경고]" in line]
    assert len(warnings) == 57, "제외 대학마다 경고 1줄이 출력되어야 한다"
    assert "universities.json에 없습니다" in warnings[0]
    assert "충남대학교" not in set(merged["학교명"]), "제외된 대학이 결과에 남았다"


@pytest.mark.realdata
@pytest.mark.skipif(not RAW_AVAILABLE, reason="Raw data/*.xlsx 없음")
def test_excluded_population_is_visible_to_user(pp_module, capsys):
    """ETL-I05 [V14 오라클]: 순위의 모집단이 '등재 N개교 기준'으로 드러나야 한다.

    사용자 결정: universities.json 과 순위 계산식은 그대로 두고,
    대신 '등재 사립 N개교 기준'이라는 사실을 사용자에게 드러낸다.
    따라서 다음 중 **하나 이상**이 성립하면 통과한다(구현 방식은 열어 둔다):

    1. `merge_campuses` 가 제외된 대학 수 또는 목록을 **반환값으로** 노출한다.
       현재는 stdout print 뿐이라 호출자(process_in_memory·main·Streamlit)가
       사용자에게 전달할 방법이 없다 (전처리.py:397-398, :428).
    2. `report_builder.build_report` 가 만든 문서에 '등재'와 '기준'을 함께 담은
       모집단 안내 문구가 있다. 현재 문서에는 '기준 연도' 때문에 '기준'만 있고
       '등재'는 없다.
    """
    universities, name_mapping, _ = pp_module.load_config(PROJECT_ROOT / "config")
    filtered = pp_module.filter_universities(pp_module.read_excel(_raw_path(2025)))

    # 반환 형태가 바뀔 수 있으므로 언패킹하지 않는다
    result = pp_module.merge_campuses(filtered, name_mapping)
    capsys.readouterr()
    exposed_by_return = _exposes_exclusions(result)

    text = _document_text(_minimal_report())
    exposed_in_report = ("등재" in text) and ("기준" in text)

    assert exposed_by_return or exposed_in_report, (
        "전국순위는 등재 사립 134개교 기준인데, merge_campuses 반환값에도 "
        "보고서 문구에도 모집단 안내가 없다. 사용자는 209개교 중 57개교가 "
        "빠진 순위를 '전국순위'로 읽게 된다."
    )


def _exposes_exclusions(result: object) -> bool:
    """`merge_campuses` 반환값이 제외 정보를 담고 있는지 (구현 방식 무관).

    (merged_df, univ_region_map) 2-튜플 뒤에 제외 수(int) 또는
    제외 목록(list/set/tuple/dict)이 붙으면 노출된 것으로 본다.
    """
    if not isinstance(result, tuple) or len(result) < 3:
        return False
    for item in result[2:]:
        if isinstance(item, bool):
            continue
        if isinstance(item, int) and item > 0:
            return True
        if isinstance(item, (set, list, tuple, dict)) and "충남대학교" in item:
            return True
    return False


def _minimal_report() -> BytesIO:
    """모집단 안내 문구 유무만 보기 위한 최소 보고서."""
    trend = {
        2025: {
            "논문수": 20.0, "전임교원수": 100, "1인당논문수": 0.2,
            "권역순위": 1, "전국순위": 1,
        }
    }
    return build_report(
        year=2025,
        hoseo_trend=trend,
        averages={2025: {"전국평균": 0.2, "권역평균": 0.2, "비교군평균": 0.2}},
        compare_data=[{
            "학교명": "호서대학교", "전임교원수": 100, "논문수": 20.0,
            "1인당논문수": 0.2, "전국순위": 1, "권역순위": 1,
        }],
        yoy_changes={"상위": [], "하위": [], "호서": None},
        rank_changes={2025: {
            "권역순위": 1, "전국순위": 1, "권역순위_변화": None, "전국순위_변화": None,
        }},
        charts=fake_charts(),
        narratives={},
        university="호서대학교",
        region_name="충청권",
    )


# ---------------------------------------------------------------------------
# ETL-I03 — 추적 중인 output/*.csv 골든 비교
# ---------------------------------------------------------------------------

@pytest.mark.realdata
@pytest.mark.slow
@pytest.mark.skipif(not RAW_AVAILABLE, reason="Raw data/*.xlsx 없음")
@pytest.mark.skipif(not REALDATA_AVAILABLE, reason="output/*.csv 없음")
def test_in_memory_matches_tracked_output_csv(pp_module):
    """ETL-I03: Raw 10개 → process_in_memory 결과가 추적 중인 CSV 와 일치한다.

    이 저장소가 배포하는 데이터의 재현성을 지키는 테스트다. 누군가 전처리
    로직을 바꾸면 `output/*.csv` 를 함께 재생성하지 않는 한 여기서 걸린다.

    V20 으로 정렬이 결정적이 된 뒤로는 **행 순서까지** 단언한다. 이전에는
    타이브레이커가 없어 동순위 행 순서가 환경마다 달라 값만 비교해야 했다.
    """
    years = sorted(
        {
            int(SCAN_YEAR_PATTERN.search(unicodedata.normalize("NFC", p.name)).group(1))
            for p in RAW_DIR.glob("*.xlsx")
            if SCAN_YEAR_PATTERN.search(unicodedata.normalize("NFC", p.name))
        }
    )
    assert len(years) >= 2, f"Raw 파일이 부족하다: {years}"

    national_mem, regional_mem = pp_module.process_in_memory(_raw_bytes(*years))

    national_git = pd.read_csv(PROJECT_ROOT / "output" / "전체_대학_데이터.csv", encoding="utf-8-sig")
    regional_git = pd.read_csv(PROJECT_ROOT / "output" / "권역별_순위.csv", encoding="utf-8-sig")

    assert list(national_mem.columns) == NATIONAL_COLUMNS
    assert list(regional_mem.columns) == REGIONAL_COLUMNS

    # 행 순서까지 동일해야 한다 (V20 이후 정렬이 결정적)
    assert national_mem["학교명"].tolist() == national_git["학교명"].tolist(), (
        "전국 CSV 의 행 순서가 재현되지 않는다 — 정렬 타이브레이커가 사라졌는지 확인할 것"
    )

    pd.testing.assert_frame_equal(
        _canonical(national_mem, ["연도", "학교명"]),
        _canonical(national_git, ["연도", "학교명"]),
        check_dtype=False,
        atol=1e-4,
    )
    pd.testing.assert_frame_equal(
        _canonical(regional_mem, ["연도", "권역명", "학교명"]),
        _canonical(regional_git, ["연도", "권역명", "학교명"]),
        check_dtype=False,
        atol=1e-4,
    )

    # V01 수정의 값 오라클 — 2017년 호서대 SCI 는 남+여 합산이어야 한다.
    hoseo_2017 = national_git[
        (national_git["연도"] == 2017) & (national_git["학교명"] == "호서대학교")
    ]
    assert len(hoseo_2017) == 1, "2017년 호서대학교 행을 찾지 못했다"
    assert hoseo_2017.iloc[0]["SCI/SCOPUS논문수"] == pytest.approx(77.3614, abs=1e-4), (
        "V01 수정 후 2017 호서대 SCI 는 77.3614 여야 한다 "
        "(61.4167 이면 '남' 열만 집계하던 시절의 값이다)"
    )

    # 추적 중인 xlsx 두 시트도 같은 골든이다. CSV 만 재생성하고 xlsx 를 빠뜨리면
    # 배포 산출물이 서로 어긋나므로 여기서 잡는다 (전처리 :635-636).
    xlsx_path = PROJECT_ROOT / "output" / "전임교원_연구실적_전처리결과.xlsx"
    assert xlsx_path.exists(), f"추적 중인 xlsx 가 없다: {xlsx_path}"
    sheets = pd.ExcelFile(xlsx_path).sheet_names
    assert sheets == ["전체_대학_데이터", "권역별_순위"], f"시트 이름이 바뀌었다: {sheets}"

    for sheet, csv_df, keys in (
        ("전체_대학_데이터", national_git, ["연도", "학교명"]),
        ("권역별_순위", regional_git, ["연도", "권역명", "학교명"]),
    ):
        sheet_df = pd.read_excel(xlsx_path, sheet_name=sheet)
        assert list(sheet_df.columns) == list(csv_df.columns), (
            f"{sheet} 시트 컬럼이 CSV 와 다르다"
        )
        pd.testing.assert_frame_equal(
            _canonical(sheet_df, keys),
            _canonical(csv_df, keys),
            check_dtype=False,
            atol=1e-4,
            obj=f"{sheet} 시트 vs CSV",
        )
