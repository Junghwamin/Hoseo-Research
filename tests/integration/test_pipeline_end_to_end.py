"""전 계층 관통 통합 테스트 (INT-01, INT-02).

data_loader → chart_generator → gpt_reporter → report_builder 를 실제
`output/*.csv` 로 한 번에 통과시켜, 계층 사이의 계약(dict 키 이름, 컬럼명,
BytesIO 차트, narratives 키)이 맞물리는지 확인한다.

GPT 호출은 `tests.fixtures.fake_openai.make_fake_client` 대역으로 대체하므로
네트워크 호출은 0회다(gpt_reporter 는 클라이언트를 첫 인자로 받기만 한다).
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest
from docx import Document

import report_app.chart_generator as cg
import report_app.data_loader as dl
import report_app.gpt_reporter as gr
from report_app.config import REPORT_TITLE
from report_app.report_builder import build_report
from tests.conftest import REALDATA_AVAILABLE
from tests.fixtures.fake_openai import make_fake_client

pytestmark = pytest.mark.skipif(
    not REALDATA_AVAILABLE, reason="샌드박스에 output/*.csv 실데이터가 없음"
)

BASE_YEAR = 2025


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """샌드박스로 복사된 실제 CSV 를 load_all_data 로 읽는다."""
    national_df, regional_df = dl.load_all_data()
    return national_df, regional_df


def _collect_stats(national_df, regional_df, university: str, region_name: str, year: int) -> dict:
    """3단계 화면이 계산하는 통계 5종을 그대로 만든다 (research.py:_calc_stats)."""
    return {
        "trend": dl.get_hoseo_trend(
            national_df, regional_df, university=university, region_name=region_name
        ),
        "averages": dl.get_averages(national_df, regional_df, region_name=region_name),
        "ranks": dl.get_rank_changes(
            national_df, regional_df, university=university, region_name=region_name
        ),
        "yoy": dl.get_yoy_changes(
            regional_df, year, university=university, region_name=region_name
        ),
        "compare": dl.get_compare_group_data(
            national_df, regional_df, year, region_name=region_name
        ),
    }


def _build_charts(regional_df, stats: dict, university: str, region_name: str, year: int) -> dict:
    """5종 차트를 앱과 동일한 인자로 생성한다 (research.py:995-1000).

    `create_comparison_bar` 는 연도만 필터하므로(chart_generator.py:176),
    앱이 그러듯 호출 전에 권역으로 먼저 걸러 넘긴다(research.py:516-517).
    """
    region_only = regional_df[regional_df["권역명"] == region_name]
    return {
        "trend": cg.create_trend_chart(
            stats["trend"], stats["averages"], university=university, region_name=region_name
        ),
        "bar": cg.create_comparison_bar(
            region_only, year, university=university, region_name=region_name
        ),
        "avg": cg.create_avg_comparison(
            stats["trend"], stats["averages"], year,
            university=university, region_name=region_name,
        ),
        "rank": cg.create_rank_trend_chart(
            stats["ranks"], university=university, region_name=region_name
        ),
        "compare": cg.create_compare_group_bar(stats["compare"], year, university=university),
    }


def _build_document(stats: dict, charts: dict, narratives: dict,
                    university: str, region_name: str, year: int) -> Document:
    buf = build_report(
        year=year,
        hoseo_trend=stats["trend"],
        averages=stats["averages"],
        compare_data=stats["compare"],
        yoy_changes=stats["yoy"],
        rank_changes=stats["ranks"],
        charts=charts,
        narratives=narratives,
        university=university,
        region_name=region_name,
    )
    assert isinstance(buf, BytesIO)
    # 재오픈 검증: 저장된 바이트가 유효한 docx 여야 한다
    return Document(BytesIO(buf.getvalue()))


def _image_count(doc: Document) -> int:
    return sum(1 for rel in doc.part.rels.values() if "image" in rel.reltype)


def _visible_paragraphs(doc: Document) -> list[str]:
    return [p.text for p in doc.paragraphs if p.text.strip()]


# ---------------------------------------------------------------------------
# INT-01 — 전 계층 관통
# ---------------------------------------------------------------------------

@pytest.mark.realdata
def test_full_pipeline_hoseo_chungcheong(real_frames):
    """INT-01: 실데이터로 load → 통계 5종 → 차트 5종 → docx 까지 관통한다."""
    national_df, regional_df = real_frames
    university, region_name = "호서대학교", "충청권"

    # 행 수를 리터럴로 박지 않는다. 새 연도 데이터가 들어오면 늘어나는 것이
    # 정상이고, 이 테스트의 목적은 규모 기록이 아니라 파이프라인 관통이다.
    # 데이터 규모 기록은 INF-01 의 @characterization 쪽이 담당한다.
    assert national_df.shape[1] == 6, "전국 CSV 컬럼 수"
    assert regional_df.shape[1] == 8, "권역 CSV 컬럼 수"
    assert national_df.shape[0] >= 1000, "전국 CSV 가 비정상적으로 작다"
    assert regional_df.shape[0] >= national_df.shape[0], (
        "권역 CSV 는 다중캠퍼스 대학 때문에 전국 CSV 보다 행이 많거나 같아야 한다"
    )

    stats = _collect_stats(national_df, regional_df, university, region_name, BASE_YEAR)

    # --- 통계 계층 ---
    data_years = sorted(int(y) for y in national_df["연도"].unique())
    assert sorted(stats["trend"].keys()) == data_years, (
        "추이 딕셔너리가 CSV 의 연도를 그대로 담아야 한다"
    )
    assert BASE_YEAR in data_years, (
        f"기준 연도 {BASE_YEAR} 가 데이터에 없다 — 이 테스트의 고정 단언들이 "
        f"그 해 값을 근거로 하므로 BASE_YEAR 는 의도적으로 고정해 둔다"
    )
    current = stats["trend"][BASE_YEAR]
    assert current["전임교원수"] == 432
    assert current["1인당논문수"] == pytest.approx(0.1182, abs=1e-4)
    assert current["전국순위"] == 77
    assert current["권역순위"] == 19
    assert stats["ranks"][BASE_YEAR]["전국순위_변화"] == -5, "2024→2025 전국순위 5계단 하락"
    assert len(stats["compare"]) == 5, "비교군 천안·아산 5개교"
    assert {row["학교명"] for row in stats["compare"]} == {
        "순천향대학교", "선문대학교", "한서대학교", "나사렛대학교", "호서대학교",
    }
    assert len(stats["yoy"]["상위"]) == 3 and len(stats["yoy"]["하위"]) == 3
    assert stats["yoy"]["호서"]["학교명"] == university

    # --- 차트 계층: 5종 모두 비어 있지 않은 PNG ---
    charts = _build_charts(regional_df, stats, university, region_name, BASE_YEAR)
    assert set(charts) == {"trend", "bar", "avg", "rank", "compare"}
    for key, buf in charts.items():
        payload = buf.getvalue()
        assert payload.startswith(b"\x89PNG"), f"{key} 차트가 PNG 가 아니다"
        assert len(payload) > 1000, f"{key} 차트가 비어 있다"

    # --- 문서 계층 ---
    doc = _build_document(
        stats, charts,
        {"trend": "T-추이", "comparison": "T-비교", "regional": "T-권역", "yoy": "T-증감"},
        university, region_name, BASE_YEAR,
    )

    paragraphs = _visible_paragraphs(doc)
    assert paragraphs[0] == university, "표지 첫 줄은 대학명"
    assert paragraphs[1] == REPORT_TITLE
    assert f"기준 연도: {BASE_YEAR}년" in paragraphs

    assert len(doc.tables) == 3, "연도별 추이 / 비교군 / 전년대비 증감 3개 표"
    assert [len(t.rows) for t in doc.tables] == [1 + len(data_years), 6, 7], (
        "표 행 수: 헤더+데이터 연도 수, 헤더+비교군 5개교, 헤더+상위 3+하위 3"
    )
    assert _image_count(doc) == 5, "차트 5종이 모두 서로 다른 이미지로 삽입돼야 한다"

    body = "\n".join(paragraphs)
    for marker in ("T-추이", "T-비교", "T-권역", "T-증감"):
        assert marker in body, f"narratives 의 {marker} 가 문서에 없다"

    header_cells = [cell.text for cell in doc.tables[0].rows[0].cells]
    assert header_cells == [
        "연도", "전임교원수", "SCI/SCOPUS 논문수", "1인당 논문수", "충청권 순위", "전국 순위",
    ]


# ---------------------------------------------------------------------------
# INT-02 — gpt_reporter 포함 관통
# ---------------------------------------------------------------------------

@pytest.mark.realdata
@pytest.mark.characterization
def test_full_pipeline_with_fake_gpt_client(real_frames):
    """INT-02: 통계 5종 → 서술 4종(가짜 클라이언트) → 문서 삽입까지 관통한다.

    섹션마다 다른 대역 클라이언트를 써서, 4개의 서술이 각각 제 섹션에
    들어갔는지 마커로 확인한다. 네트워크 호출은 `completions.calls` 로 센다.
    """
    national_df, regional_df = real_frames
    university, region_name = "호서대학교", "충청권"
    stats = _collect_stats(national_df, regional_df, university, region_name, BASE_YEAR)

    clients = {
        key: make_fake_client(content=f"INT02-{key.upper()} 서술 본문")
        for key in ("trend", "comparison", "regional", "yoy")
    }

    narratives = {
        "trend": gr.generate_trend_narrative(
            clients["trend"][0], stats["trend"], stats["averages"],
            university=university, region_name=region_name,
        ),
        "comparison": gr.generate_comparison_narrative(
            clients["comparison"][0], stats["compare"], stats["averages"], BASE_YEAR,
            university=university, region_name=region_name,
        ),
        "regional": gr.generate_regional_narrative(
            clients["regional"][0], stats["trend"], stats["ranks"],
            university=university, region_name=region_name,
        ),
        "yoy": gr.generate_yoy_narrative(
            clients["yoy"][0], stats["yoy"], BASE_YEAR,
            university=university, region_name=region_name,
        ),
    }

    # --- 네트워크 0회: 대역이 정확히 1번씩만 불렸다 ---
    total_calls = 0
    for key, (_client, completions) in clients.items():
        assert len(completions.calls) == 1, f"{key} 서술이 1회 호출되지 않았다"
        total_calls += len(completions.calls)
        call = completions.last_call
        assert call["model"] == "gpt-4o"
        assert call["max_tokens"] == 2000
        assert call["temperature"] == pytest.approx(0.4)
        assert university in completions.last_user_prompt
        assert region_name in completions.last_user_prompt
        assert "대학 IR" in completions.last_system_prompt
    assert total_calls == 4, "GPT 호출은 섹션당 1회, 총 4회여야 한다"

    # 프롬프트가 실제 통계에서 만들어졌는지 (빈 껍데기가 아닌지)
    trend_prompt = clients["trend"][1].last_user_prompt
    assert '"2025"' in trend_prompt and "전임교원수" in trend_prompt
    yoy_prompt = clients["yoy"][1].last_user_prompt
    assert "증감률" in yoy_prompt and "2024년 대비 2025년" in yoy_prompt

    # --- 4개 서술이 문서에 들어갔다 ---
    charts = _build_charts(regional_df, stats, university, region_name, BASE_YEAR)
    doc = _build_document(stats, charts, narratives, university, region_name, BASE_YEAR)

    body = "\n".join(_visible_paragraphs(doc))
    for key in ("trend", "comparison", "regional", "yoy"):
        assert f"INT02-{key.upper()} 서술 본문" in body, f"{key} 서술이 문서에 없다"
    assert len(doc.tables) == 3
    assert _image_count(doc) == 5
