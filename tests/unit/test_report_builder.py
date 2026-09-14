"""report_builder 단위 테스트 (DOC-U01 ~ DOC-U09).

대상: report_app/report_builder.py

build_report 는 디스크를 전혀 건드리지 않고 메모리 내 docx(BytesIO)를 반환한다.
따라서 모든 검증은 반환된 바이트를 python-docx 로 다시 열어(re-open) 수행한다.

기본값(default)은 config 모듈이 아니라 report_builder 모듈 속성이므로
monkeypatch 대상은 `rb.UNIVERSITY`, `rb.REPORT_FONT`, `rb.COMPARE_GROUP_NAME`, `rb.date` 다.
"""

from __future__ import annotations

import datetime
import io
import re
import zipfile

import docx
import pytest
from docx.image.exceptions import UnrecognizedImageError
from docx.oxml.ns import qn

import report_app.report_builder as rb
from tests.fixtures.tiny_png import fake_charts, small_png_buf

ZIP_MAGIC = b"PK\x03\x04"
HEADING_RE = re.compile(r"^[1-5]\. ")


# ===========================================================================
# 로컬 헬퍼 (local helper)
# ===========================================================================

class _FixedDate:
    """`rb.date` 대역(stub): today() 를 고정해 표지 문자열을 결정적으로 만든다."""

    @staticmethod
    def today() -> datetime.date:
        return datetime.date(2026, 9, 14)


@pytest.fixture
def fixed_date(monkeypatch):
    """생성일(today) 고정 — 문서 비교 테스트에서 날짜 변동을 제거한다."""
    monkeypatch.setattr(rb, "date", _FixedDate)
    return _FixedDate.today()


def _trend() -> dict:
    """연도 2개, 두 번째 해의 권역순위는 None('-' 표시 검증용)."""
    return {
        2024: {"논문수": 20.0, "전임교원수": 100, "1인당논문수": 0.2000, "권역순위": 3, "전국순위": 50},
        2025: {"논문수": 25.0, "전임교원수": 102, "1인당논문수": 0.2451, "권역순위": None, "전국순위": 45},
    }


def _averages() -> dict:
    return {
        y: {"전국평균": 0.3000, "권역평균": 0.2800, "비교군평균": 0.2600}
        for y in (2024, 2025)
    }


def _compare_data() -> list:
    """대상 대학 1개 + 비교 대학 2개. 마지막 행의 권역순위는 None."""
    return [
        {"학교명": "호서대학교", "전임교원수": 1234, "논문수": 302.5,
         "1인당논문수": 0.2451, "전국순위": 45, "권역순위": 3},
        {"학교명": "선문대학교", "전임교원수": 300, "논문수": 40.0,
         "1인당논문수": 0.1333, "전국순위": 120, "권역순위": 8},
        {"학교명": "한서대학교", "전임교원수": 250, "논문수": 30.0,
         "1인당논문수": 0.1200, "전국순위": 150, "권역순위": None},
    ]


def _yoy(top: int = 3, bottom: int = 3) -> dict:
    return {
        "상위": [
            {"학교명": f"상위대학교{i}", "증감률": 12.3, "기준연도": 0.3000, "비교연도": 0.2600}
            for i in range(top)
        ],
        "하위": [
            {"학교명": f"하위대학교{i}", "증감률": -8.4, "기준연도": 0.1000, "비교연도": 0.2000}
            for i in range(bottom)
        ],
        "호서": None,
    }


def _rank_changes() -> dict:
    return {2024: {"권역순위": 3, "전국순위": 50}, 2025: {"권역순위": None, "전국순위": 45}}


def _narratives() -> dict:
    return {
        "trend": "• 추이 서술 첫 줄\n• 추이 서술 둘째 줄",
        "comparison": "• 평균 비교 서술",
        "regional": "• 권역 비교 서술",
        "yoy": "• 전년대비 서술",
    }


def _build(**overrides) -> io.BytesIO:
    """baseline 인자로 build_report 를 호출한다. overrides 로 개별 인자만 바꾼다."""
    kwargs = dict(
        year=2025,
        hoseo_trend=_trend(),
        averages=_averages(),
        compare_data=_compare_data(),
        yoy_changes=_yoy(),
        rank_changes=_rank_changes(),
        charts=fake_charts(),
        narratives=_narratives(),
    )
    kwargs.update(overrides)
    return rb.build_report(**kwargs)


def _reopen(buf: io.BytesIO):
    """반환 BytesIO 를 소비하지 않고 docx.Document 로 다시 연다."""
    return docx.Document(io.BytesIO(buf.getvalue()))


def _document_xml(buf: io.BytesIO) -> bytes:
    """docx(zip) 안의 word/document.xml 만 꺼낸다.

    zip 엔트리의 타임스탬프는 저장 시각(초 단위)으로 들어가므로 컨테이너
    바이트 전체는 결정적이지 않다. 본문 결정성은 document.xml 로 비교한다.
    """
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as archive:
        return archive.read("word/document.xml")


def _cell_fill(cell) -> str | None:
    """셀의 w:shd/@w:fill 배경색을 읽는다 (없으면 None)."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    return None if shd is None else shd.get(qn("w:fill"))


def _all_text(document) -> str:
    """본문 단락 + 모든 표 셀의 텍스트를 하나로 합친다."""
    parts = [p.text for p in document.paragraphs]
    parts += [
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    ]
    return "\n".join(parts)


def _headings(document) -> list:
    """'1. ' ~ '5. ' 로 시작하는 섹션 제목 단락."""
    return [p.text for p in document.paragraphs if HEADING_RE.match(p.text)]


# ===========================================================================
# DOC-U01: 전체 fixture 조립 계약
# ===========================================================================

def test_doc_u01_full_report_structure(fixed_date):
    """DOC-U01: 전체 입력으로 만든 보고서의 표/이미지/폭/제목 구성을 고정한다."""
    buf = _build()

    assert isinstance(buf, io.BytesIO)
    assert buf.getvalue()[:4] == ZIP_MAGIC, "docx 는 ZIP 컨테이너(PK\\x03\\x04)로 시작해야 한다"
    assert buf.tell() == 0, "반환 직후 바로 읽을 수 있도록 seek(0) 되어야 한다"

    document = _reopen(buf)

    assert len(document.tables) == 3, "연도별 추이·비교군 현황·전년대비 증감 3개 표"
    assert len(document.inline_shapes) == 5, "차트 5종이 모두 삽입되어야 한다"

    widths_cm = [round(shape.width.cm, 1) for shape in document.inline_shapes]
    assert widths_cm == [14.0, 12.0, 15.0, 14.0, 11.0], (
        f"삽입 순서/폭 불일치(trend, avg, bar, rank, compare): {widths_cm}"
    )

    headings = _headings(document)
    assert len(headings) == 5, f"섹션 제목 5개여야 한다: {headings}"
    assert headings[0].startswith("1. 전임교원 1인당 SCI/SCOPUS 논문수 추이")
    assert headings[4] == "5. 전년대비 증감 현황 (2024→2025년)"


def test_doc_u01_cover_page_uses_module_level_defaults(monkeypatch, fixed_date):
    """DOC-U01: 표지의 대학명은 `rb.UNIVERSITY` 모듈 속성, 생성일은 `rb.date` 로 결정된다."""
    monkeypatch.setattr(rb, "UNIVERSITY", "가짜대학교")

    document = _reopen(_build())
    texts = [p.text for p in document.paragraphs]

    assert "가짜대학교" in texts, f"university 생략 시 모듈 기본값이 표지에 쓰여야 한다: {texts[:10]}"
    assert rb.REPORT_TITLE in texts
    assert "기준 연도: 2025년" in texts
    assert "생성일: 2026년 9월 14일" in texts


def test_doc_u01_university_argument_overrides_default(monkeypatch, fixed_date):
    """DOC-U01: university 인자를 주면 모듈 기본값 대신 그 값이 표지에 쓰인다."""
    monkeypatch.setattr(rb, "UNIVERSITY", "가짜대학교")

    document = _reopen(_build(university="순천향대학교"))
    texts = [p.text for p in document.paragraphs]

    assert "순천향대학교" in texts
    assert "가짜대학교" not in texts


# ===========================================================================
# DOC-U02: 빈 charts/narratives, 미사용 인자
# ===========================================================================

def test_doc_u02_empty_charts_and_narratives(fixed_date):
    """DOC-U02: charts/narratives 가 비어도 예외 없이 표와 제목 구조는 유지된다."""
    document = _reopen(_build(charts={}, narratives={}))

    assert len(document.inline_shapes) == 0, "차트가 없으면 이미지도 0개여야 한다"
    assert len(document.tables) == 3, "차트가 없어도 표 3개는 그대로 생성된다"
    assert len(_headings(document)) == 5, "섹션 제목 5개는 항상 생성된다"


def test_doc_u02_partial_charts_insert_only_given_keys(fixed_date):
    """DOC-U02: charts 딕셔너리에 있는 키만 이미지로 삽입된다."""
    document = _reopen(_build(charts={"trend": small_png_buf(), "compare": small_png_buf()}))

    widths_cm = [round(shape.width.cm, 1) for shape in document.inline_shapes]
    assert widths_cm == [14.0, 11.0], f"trend(14cm)·compare(11cm)만 들어가야 한다: {widths_cm}"


@pytest.mark.characterization
def test_doc_u02_averages_and_rank_changes_are_dead_parameters(fixed_date):
    """DOC-U02: averages/rank_changes 를 바꿔도 문서가 동일한 현재 동작을 기록한다(특성화).

    build_report 의 서명에는 남아 있지만 본문 어디에서도 쓰이지 않는
    미사용 인자(dead parameter)다. 서명 정리 시 이 테스트를 함께 갱신할 것.
    """
    baseline = _document_xml(_build())
    mutated = _document_xml(_build(averages={}, rank_changes={}))

    assert baseline == mutated, "averages/rank_changes 가 문서에 영향을 준다면 계약이 바뀐 것이다"


# ===========================================================================
# DOC-U03: 전년대비 증감 표
# ===========================================================================

@pytest.mark.parametrize(
    ("case_id", "yoy_changes"),
    [
        pytest.param("빈-리스트", {"상위": [], "하위": [], "호서": None}, id="empty-lists"),
        pytest.param("빈-딕셔너리", {}, id="empty-dict"),
    ],
)
def test_doc_u03_empty_yoy_falls_back_to_notice(fixed_date, case_id, yoy_changes):
    """DOC-U03: 증감 데이터가 없으면 표 대신 '(전년도 데이터 없음)' 문구가 들어간다."""
    document = _reopen(_build(yoy_changes=yoy_changes))
    texts = [p.text for p in document.paragraphs]

    assert "(전년도 데이터 없음)" in texts, f"{case_id}: 안내 문구가 없다"
    assert len(document.tables) == 2, f"{case_id}: 증감 표가 생성되지 않아 표는 2개여야 한다"


def test_doc_u03_yoy_table_rows_and_rate_format(fixed_date):
    """DOC-U03: 상위 3 + 하위 3 이면 헤더 포함 7행이고 증감률은 '+x.x%' 포맷이다."""
    document = _reopen(_build())
    table = document.tables[2]

    assert len(table.rows) == 7, f"헤더 1 + 데이터 6 = 7행이어야 한다: {len(table.rows)}"
    assert [c.text for c in table.rows[0].cells] == [
        "구분", "대학명", "2024년 실적", "2025년 실적", "증감률(%)"
    ]
    assert [c.text for c in table.rows[1].cells] == [
        "상위 1", "상위대학교0", "0.2600", "0.3000", "+12.3%"
    ]
    assert [c.text for c in table.rows[4].cells] == [
        "하위 1", "하위대학교0", "0.2000", "0.1000", "-8.4%"
    ]
    assert [row.cells[0].text for row in table.rows[1:]] == [
        "상위 1", "상위 2", "상위 3", "하위 1", "하위 2", "하위 3"
    ]


def test_doc_u03_yoy_table_handles_asymmetric_counts(fixed_date):
    """DOC-U03: 상위/하위 개수가 달라도 행 수가 그대로 따라간다."""
    document = _reopen(_build(yoy_changes=_yoy(top=2, bottom=1)))
    table = document.tables[2]

    assert len(table.rows) == 4
    assert [row.cells[0].text for row in table.rows[1:]] == ["상위 1", "상위 2", "하위 1"]


# ===========================================================================
# DOC-U04: V11 - lstrip 이 줄 선두 음수 부호를 제거 (확정 결함)
# ===========================================================================

@pytest.mark.xfail(
    strict=True,
    reason="V11: lstrip 이 줄 선두 음수 부호까지 제거 (Phase 4 수정 대상 아님 — xfail 유지)",
)
def test_doc_u04_narrative_preserves_leading_minus_sign():
    """DOC-U04: 불릿 기호만 제거하고 줄 선두의 음수 부호는 보존해야 한다(V11).

    report_builder.py:81 의 `line.lstrip("•-· ")` 는 문자 집합 제거라
    불릿 '-' 과 숫자의 음수 부호 '-' 를 구분하지 못한다.
    '• -0.5편 감소' 가 '0.5편 감소' 로 바뀌어 감소가 증가처럼 읽힌다.
    V11 은 Phase 4 수정 대상이 아니므로 이 xfail 은 그대로 남는다.
    """
    document = docx.Document()

    rb._add_narrative(document, "• -0.5편 감소\n- 정상 불릿\n-3.2% 하락\n• ▼1위 하락")

    texts = [p.text for p in document.paragraphs if p.text]
    assert texts == ["-0.5편 감소", "정상 불릿", "-3.2% 하락", "▼1위 하락"], (
        f"음수 부호가 손실됐다: {texts}"
    )


@pytest.mark.characterization
def test_doc_u04_narrative_strips_bullet_markers_only():
    """DOC-U04: 불릿 기호(•, -, ·) 제거와 ▼·문장 중간 부호 보존을 기록한다(특성화).

    줄 선두 음수 부호가 함께 지워지는 V11 결함 동작은 여기서 단언하지 않는다
    (같은 동작을 통과·결함 양쪽으로 이중 분류하지 않기 위해).
    """
    document = docx.Document()

    rb._add_narrative(document, "- 정상 불릿\n· 가운뎃점 불릿\n• ▼1위 하락\n• 전년 대비 -1.2편")

    texts = [p.text for p in document.paragraphs if p.text]
    assert texts == ["정상 불릿", "가운뎃점 불릿", "▼1위 하락", "전년 대비 -1.2편"]


@pytest.mark.characterization
def test_doc_u04_narrative_skips_blank_and_bullet_only_lines():
    """DOC-U04: 빈 줄과 불릿만 있는 줄은 단락을 만들지 않는 현재 동작을 기록한다(특성화)."""
    document = docx.Document()

    rb._add_narrative(document, "• 첫 줄\n\n•\n   \n• 둘째 줄")

    texts = [p.text for p in document.paragraphs if p.text]
    assert texts == ["첫 줄", "둘째 줄"]


# ===========================================================================
# DOC-U05: 동아시아(eastAsia) 폰트 미설정 (확정 결함 후보)
# ===========================================================================

def test_doc_u05_set_font_applies_east_asia_font():
    """DOC-U05: _set_font 는 w:eastAsia 에도 REPORT_FONT 를 지정해야 한다.

    python-docx 의 `run.font.name = ...` 은 w:ascii 와 w:hAnsi 만 설정한다.
    한글은 Word 에서 eastAsia 계열로 렌더되므로, eastAsia 가 비면
    '맑은 고딕' 지정이 한글 본문에 적용되지 않는다.
    """
    document = docx.Document()
    run = document.add_paragraph().add_run("한글 본문")

    rb._set_font(run, size_pt=10)

    rFonts = run._element.get_or_add_rPr().rFonts
    assert rFonts is not None, "rFonts 요소 자체가 없다"
    assert rFonts.get(qn("w:ascii")) == rb.REPORT_FONT
    assert rFonts.get(qn("w:hAnsi")) == rb.REPORT_FONT
    assert rFonts.get(qn("w:eastAsia")) == rb.REPORT_FONT, (
        f"eastAsia 폰트가 설정되지 않았다: {rFonts.get(qn('w:eastAsia'))!r}"
    )


def test_doc_u05_set_font_size_bold_color(monkeypatch):
    """DOC-U05: _set_font 의 크기·굵기·색상 지정은 현재도 정상 동작한다."""
    monkeypatch.setattr(rb, "REPORT_FONT", "테스트폰트")
    document = docx.Document()
    run = document.add_paragraph().add_run("x")

    rb._set_font(run, size_pt=9, bold=True, color_hex="2E75B6")

    assert run.font.name == "테스트폰트", "REPORT_FONT 는 모듈 속성에서 읽어야 한다"
    assert run.font.size.pt == 9
    assert run.font.bold is True
    assert str(run.font.color.rgb) == "2E75B6"


# ===========================================================================
# DOC-U06: 손상된 이미지 버퍼 (현재 동작 특성화)
# ===========================================================================

@pytest.mark.characterization
@pytest.mark.parametrize(
    ("case_id", "bad_buf"),
    [
        pytest.param("빈-BytesIO", io.BytesIO(b""), id="empty-bytesio"),
        pytest.param("손상-바이트", io.BytesIO(b"not a png at all" * 8), id="garbage-bytes"),
    ],
)
def test_doc_u06_broken_chart_buffer_raises(fixed_date, case_id, bad_buf):
    """DOC-U06: 빈/손상 차트 버퍼면 보고서 생성 전체가 예외로 실패함을 기록한다(특성화).

    _add_image 는 검증 없이 run.add_picture 에 넘기므로 python-docx 의
    UnrecognizedImageError 가 build_report 밖으로 그대로 전파된다.
    """
    with pytest.raises(UnrecognizedImageError):
        _build(charts={"trend": bad_buf})


@pytest.mark.characterization
def test_doc_u06_exhausted_buffer_is_rewound(fixed_date):
    """DOC-U06: 이미 read() 로 소진된 BytesIO 도 _add_image 의 seek(0) 덕분에 정상 삽입된다."""
    exhausted = small_png_buf()
    assert exhausted.read() != b"", "사전 조건: 버퍼를 끝까지 읽어 소진시킨다"
    assert exhausted.tell() > 0

    document = _reopen(_build(charts={"trend": exhausted}))

    assert len(document.inline_shapes) == 1
    assert round(document.inline_shapes[0].width.cm, 1) == 14.0


# ===========================================================================
# DOC-U07: 표 셀 스타일과 숫자 포맷
# ===========================================================================

def test_doc_u07_trend_table_shading_and_formats(fixed_date):
    """DOC-U07: 연도별 추이 표의 헤더 배경·줄무늬·숫자 포맷·권역순위 '-' 를 고정한다."""
    document = _reopen(_build())
    table = document.tables[0]

    assert [_cell_fill(c) for c in table.rows[0].cells] == ["2E75B6"] * 6, "헤더 배경색"
    assert [_cell_fill(row.cells[0]) for row in table.rows] == ["2E75B6", "D6E4F0", "FFFFFF"], (
        "짝수 데이터 행 D6E4F0, 홀수 행 FFFFFF 줄무늬(zebra striping)"
    )

    assert [c.text for c in table.rows[0].cells] == [
        "연도", "전임교원수", "SCI/SCOPUS 논문수", "1인당 논문수", "충청권 순위", "전국 순위"
    ]
    assert [c.text for c in table.rows[1].cells] == [
        "2024", "100명", "20.00편", "0.2000", "3위", "50위"
    ]
    assert [c.text for c in table.rows[2].cells] == [
        "2025", "102명", "25.00편", "0.2451", "-", "45위"
    ], "권역순위가 None 이면 '-' 로 표시되어야 한다"


def test_doc_u07_trend_table_header_reflects_region_name(fixed_date):
    """DOC-U07: region_name 을 바꾸면 추이 표 헤더의 순위 컬럼명이 따라간다."""
    document = _reopen(_build(region_name="호남권"))
    assert document.tables[0].rows[0].cells[4].text == "호남권 순위"


def test_doc_u07_compare_table_highlights_target_university(fixed_date):
    """DOC-U07: 비교군 표에서 대상 대학 행만 FFF2CC 배경 + 굵게(bold) 강조된다."""
    document = _reopen(_build(university="호서대학교"))
    table = document.tables[1]

    assert [_cell_fill(row.cells[0]) for row in table.rows] == [
        "2E75B6", "FFF2CC", "FFFFFF", "D6E4F0"
    ], "0번 데이터 행(호서)은 강조색, 나머지는 zebra"

    bolds = [row.cells[0].paragraphs[0].runs[0].bold for row in table.rows[1:]]
    assert bolds == [True, False, False], f"대상 대학 행만 굵게여야 한다: {bolds}"


def test_doc_u07_highlight_follows_university_argument(fixed_date):
    """DOC-U07: university 인자를 바꾸면 강조 행(FFF2CC + bold)이 그 대학으로 이동한다."""
    document = _reopen(_build(university="한서대학교"))
    table = document.tables[1]

    fills = [_cell_fill(row.cells[0]) for row in table.rows]
    assert fills == ["2E75B6", "D6E4F0", "FFFFFF", "FFF2CC"], f"강조가 이동하지 않았다: {fills}"

    bolds = [row.cells[0].paragraphs[0].runs[0].bold for row in table.rows[1:]]
    assert bolds == [False, False, True]
    assert table.rows[3].cells[0].text == "한서대학교"


def test_doc_u07_compare_table_number_formats(fixed_date):
    """DOC-U07: 비교군 표의 천단위 구분·소수 자릿수·권역순위 None 표기를 고정한다."""
    table = _reopen(_build()).tables[1]

    assert [c.text for c in table.rows[0].cells] == [
        "대학명", "전임교원수", "논문수", "1인당 논문수", "전국 순위", "충청권 순위"
    ]
    assert [c.text for c in table.rows[1].cells] == [
        "호서대학교", "1,234명", "302.50편", "0.2451", "45위", "3위"
    ]
    assert table.rows[3].cells[5].text == "-", "권역순위 None → '-'"


# ===========================================================================
# DOC-U08: 디스크 무접촉 + 본문 결정성
# ===========================================================================

def test_doc_u08_does_not_touch_disk(monkeypatch, tmp_path, fixed_date):
    """DOC-U08: build_report 는 어떤 파일도 만들지 않는다(REPORT_DIR 생성은 호출자 책임)."""
    monkeypatch.chdir(tmp_path)

    buf = _build()

    assert buf.getvalue()[:4] == ZIP_MAGIC
    assert list(tmp_path.iterdir()) == [], f"작업 디렉터리에 파일이 생성됐다: {list(tmp_path.iterdir())}"


def test_doc_u08_document_body_is_deterministic(fixed_date):
    """DOC-U08: 생성일을 고정하면 같은 입력에 대해 word/document.xml 이 바이트 단위로 같다.

    주의: docx 컨테이너(zip) 전체 바이트는 결정적이지 않다. zip 엔트리
    타임스탬프가 저장 시각(초 단위)으로 기록되기 때문이다. 본문 결정성은
    document.xml 로 비교한다.
    """
    first = _build()
    second = _build()

    assert _document_xml(first) == _document_xml(second)
    assert len(first.getvalue()) == len(second.getvalue()), "본문이 같으면 크기도 같아야 한다"


# ===========================================================================
# DOC-U09: 비교군 이름/권역명 하드코딩 (확정 결함 후보)
# ===========================================================================

@pytest.mark.xfail(strict=True, reason="비교군 이름/권역명이 상수로 하드코딩")
def test_doc_u09_no_hardcoded_hoseo_literals_for_other_university(fixed_date):
    """DOC-U09: 다른 대학·권역으로 생성하면 호서/충청권 리터럴이 문서에 남으면 안 된다.

    build_report 는 섹션 2·4 제목에 `COMPARE_GROUP_NAME`("천안·아산 5개 대학")을
    모듈 상수로 직접 박아 쓴다(report_builder.py:315, :340). 대상 대학과
    권역을 바꿔도 이 문자열이 그대로 남아 제주권 보고서에 천안·아산이 나온다.
    """
    jeju_compare = [
        {"학교명": "제주국제대학교", "전임교원수": 100, "논문수": 10.0,
         "1인당논문수": 0.1000, "전국순위": 200, "권역순위": 2},
    ]
    document = _reopen(
        _build(university="제주국제대학교", region_name="제주권", compare_data=jeju_compare)
    )
    text = _all_text(document)

    leaked = [lit for lit in ("충청권", "천안·아산 5개 대학", "호서") if lit in text]
    assert leaked == [], f"다른 대학 보고서에 하드코딩 리터럴이 남았다: {leaked}"


def test_doc_u09_region_name_propagates_to_headings_and_tables(fixed_date):
    """DOC-U09: region_name 인자는 제목과 표 헤더에 빠짐없이 반영된다.

    비교군 이름(COMPARE_GROUP_NAME) 하드코딩은 위 xfail 이 잠그므로 여기서는
    단언하지 않는다.
    """
    jeju_compare = [
        {"학교명": "제주국제대학교", "전임교원수": 100, "논문수": 10.0,
         "1인당논문수": 0.1000, "전국순위": 200, "권역순위": 2},
    ]
    document = _reopen(
        _build(university="제주국제대학교", region_name="제주권", compare_data=jeju_compare)
    )

    assert _headings(document)[2] == "3. 제주권 대학 비교 (2025년)"
    assert document.tables[0].rows[0].cells[4].text == "제주권 순위"
    assert document.tables[1].rows[0].cells[5].text == "제주권 순위"
    assert "충청권" not in _all_text(document), "권역명은 인자를 따라가야 한다"
