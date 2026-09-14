"""chart_generator 단위 테스트 (VIS-U01 ~ VIS-U07).

대상: report_app/chart_generator.py

이 모듈은 순수 입출력(pure I/O) 함수 5종으로 구성된다. 입력은 dict/DataFrame/list,
출력은 PNG 를 담은 BytesIO 다. 따라서 픽셀 비교(pixel diff) 없이도
"무엇이 그려졌는가" 를 Axes 객체 수준에서 검증할 수 있다.

기본값(default)은 config 모듈이 아니라 chart_generator 모듈 속성이므로
monkeypatch 대상은 `cg.UNIVERSITY` 다(from ... import 로 바인딩된 사본).

matplotlib 백엔드(backend)는 conftest 가 이미 Agg 로 고정했고,
autouse 픽스처가 매 테스트 후 `plt.close("all")` 과 rcParams 복원을 수행한다.
다만 Figure 누수(figure leak) 단언은 teardown 이 아니라 각 테스트 본문에서 한다
(teardown 실패는 xfail 이 흡수하지 못해 ERROR 가 되기 때문).
"""

from __future__ import annotations

import types
from io import BytesIO

import matplotlib
import matplotlib.axes
import matplotlib.pyplot as plt
import pytest
from PIL import Image

import report_app.chart_generator as cg
from tests.fixtures.make_frames import make_reg

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
NAN = float("nan")


# ===========================================================================
# 로컬 헬퍼 (local helper)
# ===========================================================================

def _capture_subplots(monkeypatch) -> list[dict]:
    """`cg.plt.subplots` 를 감싸 호출 인자와 생성된 Figure/Axes 를 기록한다.

    반환 리스트의 각 원소는 {"args", "kwargs", "fig", "axes"} 다.
    _save_fig 가 Figure 를 close 한 뒤에도 Axes 의 patches/title 은 그대로
    읽을 수 있으므로, PNG 픽셀 비교 없이 그려진 내용을 검증할 수 있다.
    """
    records: list[dict] = []
    original = cg.plt.subplots

    def _wrapper(*args, **kwargs):
        fig, axes = original(*args, **kwargs)
        records.append({"args": args, "kwargs": kwargs, "fig": fig, "axes": axes})
        return fig, axes

    monkeypatch.setattr(cg.plt, "subplots", _wrapper)
    return records


def _trend(years=(2024, 2025), start=0.2000, step=0.0250) -> dict:
    """create_trend_chart / create_avg_comparison 용 hoseo_trend."""
    return {y: {"1인당논문수": round(start + i * step, 4)} for i, y in enumerate(years)}


def _averages(years=(2024, 2025)) -> dict:
    """전국/권역/비교군 평균 3종을 담은 averages."""
    return {
        y: {
            "전국평균": round(0.3000 + i * 0.01, 4),
            "권역평균": round(0.2800 + i * 0.01, 4),
            "비교군평균": round(0.2600 + i * 0.01, 4),
        }
        for i, y in enumerate(years)
    }


def _ranks(years=(2024, 2025)) -> dict:
    """create_rank_trend_chart 용 rank_changes (권역순위 모두 존재)."""
    return {y: {"권역순위": 3 - i, "전국순위": 50 - i * 5} for i, y in enumerate(years)}


def _regional(year: int = 2025):
    """단일 권역(충청권) 3개교 DataFrame."""
    return make_reg(
        [
            {"year": year, "name": name, "교원": 100, "논문": 20 + i}
            for i, name in enumerate(["호서대학교", "순천향대학교", "선문대학교"])
        ]
    )


def _multi_region_frame(year: int = 2025):
    """충청권 3개교 + 수도권 4개교가 섞인 권역별 DataFrame (V08 재현용)."""
    rows = [
        {"year": year, "name": name, "교원": 100, "논문": 20 + i, "권역": "충청권"}
        for i, name in enumerate(["호서대학교", "순천향대학교", "선문대학교"])
    ]
    rows += [
        {"year": year, "name": name, "교원": 100, "논문": 30 + i, "권역": "수도권"}
        for i, name in enumerate(["서울대학교", "연세대학교", "고려대학교", "한양대학교"])
    ]
    return make_reg(rows)


def _compare_rows() -> list:
    """create_compare_group_bar 용 compare_data."""
    return [
        {"학교명": "호서대학교", "1인당논문수": 0.2451},
        {"학교명": "선문대학교", "1인당논문수": 0.1333},
        {"학교명": "한서대학교", "1인당논문수": 0.1800},
    ]


# 5종 차트를 동일한 서명으로 호출하는 팩토리 (VIS-U01 에서 parametrize)
CHART_FACTORIES = {
    "create_trend_chart": lambda: cg.create_trend_chart(_trend(), _averages()),
    "create_comparison_bar": lambda: cg.create_comparison_bar(_regional(), 2025),
    "create_avg_comparison": lambda: cg.create_avg_comparison(_trend(), _averages(), 2025),
    "create_rank_trend_chart": lambda: cg.create_rank_trend_chart(_ranks()),
    "create_compare_group_bar": lambda: cg.create_compare_group_bar(_compare_rows(), 2025),
}


# ===========================================================================
# VIS-U01: 5종 차트의 반환 계약
# ===========================================================================

@pytest.mark.parametrize("func_name", sorted(CHART_FACTORIES))
def test_vis_u01_chart_returns_valid_png_and_closes_figure(func_name):
    """VIS-U01: 5종 차트가 유효한 PNG BytesIO 를 반환하고 Figure 를 남기지 않는다."""
    buf = CHART_FACTORIES[func_name]()

    assert isinstance(buf, BytesIO), f"{func_name} 는 BytesIO 를 반환해야 한다"
    raw = buf.getvalue()
    assert raw[:8] == PNG_MAGIC, f"{func_name} 반환값이 PNG 매직 바이트(magic bytes)로 시작하지 않는다"
    assert len(raw) > 1000, f"{func_name} PNG 가 {len(raw)}바이트로 너무 작다(빈 차트 의심)"

    buf.seek(0)
    with Image.open(buf) as image:
        assert image.format == "PNG", f"{func_name} 이미지를 PIL 이 PNG 로 인식하지 못했다"
        assert image.size[0] > 0 and image.size[1] > 0

    assert plt.get_fignums() == [], f"{func_name} 호출 후 Figure 가 남았다(누수): {plt.get_fignums()}"


def test_vis_u01_seek_position_is_zero_after_return():
    """VIS-U01: 반환된 BytesIO 의 읽기 위치(seek position)가 0 이어야 바로 삽입 가능하다."""
    buf = cg.create_trend_chart(_trend(), _averages())
    assert buf.tell() == 0, "반환 직후 read() 가 전체 PNG 를 읽을 수 있어야 한다"
    assert buf.read(8) == PNG_MAGIC
    assert plt.get_fignums() == []


def test_vis_u01_module_level_university_default_is_used(monkeypatch):
    """VIS-U01: university 를 생략하면 config 가 아니라 `cg.UNIVERSITY` 모듈 속성이 쓰인다."""
    monkeypatch.setattr(cg, "UNIVERSITY", "가짜대학교")
    records = _capture_subplots(monkeypatch)

    cg.create_avg_comparison(_trend(), _averages(), 2025)

    labels = [label.get_text() for label in records[-1]["axes"].get_yticklabels()]
    assert "가짜대학교" in labels, f"모듈 속성 UNIVERSITY 가 기본값으로 쓰여야 한다: {labels}"
    assert plt.get_fignums() == []


# ===========================================================================
# VIS-U02: 경계값 특성화 (현재 동작 기록)
# ===========================================================================

BOUNDARY_CASES = [
    pytest.param(lambda: cg.create_trend_chart(_trend(years=(2025,)), _averages(years=(2025,))),
                 id="trend-year1"),
    pytest.param(lambda: cg.create_trend_chart({}, {}), id="trend-empty-dict"),
    pytest.param(lambda: cg.create_comparison_bar(make_reg([]), 2025), id="bar-empty-frame"),
    pytest.param(lambda: cg.create_comparison_bar(_regional(), 1999), id="bar-year-absent"),
    pytest.param(lambda: cg.create_comparison_bar(_regional(), 2025, university="없는대학교"),
                 id="bar-target-absent"),
    pytest.param(lambda: cg.create_avg_comparison(_trend(years=(2025,)), _averages(years=(2025,)),
                                                  2025, university="없는대학교"),
                 id="avg-target-absent"),
    pytest.param(lambda: cg.create_rank_trend_chart({}), id="rank-empty-dict"),
    pytest.param(lambda: cg.create_rank_trend_chart(
        {2024: {"권역순위": None, "전국순위": 50}, 2025: {"권역순위": None, "전국순위": 45}}),
        id="rank-all-none"),
    pytest.param(lambda: cg.create_compare_group_bar([], 2025), id="compare-empty-list"),
    pytest.param(lambda: cg.create_avg_comparison(
        {2025: {"1인당논문수": 0.2}},
        {2025: {"전국평균": NAN, "권역평균": 0.28, "비교군평균": 0.26}},
        2025),
        id="avg-nan-not-first"),
]


@pytest.mark.characterization
@pytest.mark.parametrize("call", BOUNDARY_CASES)
def test_vis_u02_boundary_inputs_do_not_raise(call):
    """VIS-U02: 경계 입력에서 예외 없이 PNG 가 나오는 현재 동작을 기록한다(특성화).

    NaN 이 values 리스트의 **첫 원소가 아니면** max() 가 NaN 을 건너뛰므로
    set_xlim 이 통과한다(chart_generator.py:256). 첫 원소일 때의 ValueError 는
    VIS-U03 에서 별도로 잠근다.
    """
    buf = call()
    assert isinstance(buf, BytesIO)
    assert buf.getvalue()[:8] == PNG_MAGIC
    assert plt.get_fignums() == []


@pytest.mark.characterization
def test_vis_u02_avg_comparison_nan_position_matters():
    """VIS-U02: max() 의 NaN 전파 특성상 NaN 위치에 따라 성패가 갈리는 현재 동작을 기록한다."""
    # 두 번째 위치의 NaN: max([0.2, nan, 0.28, 0.26]) == 0.28 이라 set_xlim 을 통과한다.
    assert max([0.2, NAN, 0.28, 0.26]) == 0.28

    averages = {2025: {"전국평균": NAN, "권역평균": 0.28, "비교군평균": 0.26}}
    buf = cg.create_avg_comparison({2025: {"1인당논문수": 0.2}}, averages, 2025)

    assert buf.getvalue()[:8] == PNG_MAGIC
    assert plt.get_fignums() == []


# ===========================================================================
# VIS-U03: Figure 누수 (확정 결함)
# ===========================================================================

@pytest.mark.xfail(
    strict=True,
    reason="Figure 누수: _save_fig 미도달 시 close 안 됨 (chart_generator.py:256 set_xlim ValueError)",
)
def test_vis_u03_avg_comparison_does_not_leak_figure_on_error():
    """VIS-U03: 대상 대학 값이 NaN 이라 set_xlim 이 실패해도 Figure 를 닫아야 한다.

    현재 create_avg_comparison 은 plt.subplots 로 Figure 를 만든 뒤
    ax.set_xlim(0, max(values) * 1.3) 에서 ValueError 를 던지며,
    close 를 담당하는 _save_fig 에 도달하지 못해 Figure 가 전역 레지스트리에 남는다.
    고쳐진 뒤에는 예외 경로에서도 누수가 없어야 한다.
    """
    hoseo_trend = {2025: {"1인당논문수": NAN}}
    averages = {2025: {"전국평균": 0.30, "권역평균": 0.28, "비교군평균": 0.26}}

    with pytest.raises(ValueError, match="Axis limits cannot be NaN or Inf"):
        cg.create_avg_comparison(hoseo_trend, averages, 2025)

    assert plt.get_fignums() == [], (
        f"예외 경로에서 Figure 가 닫히지 않고 남았다(누수): {plt.get_fignums()}"
    )


# ===========================================================================
# VIS-U04: V08 - create_comparison_bar 권역 필터 누락 (확정 결함)
# ===========================================================================

def test_vis_u04_comparison_bar_filters_by_region_name(monkeypatch):
    """VIS-U04: region_name='충청권' 이면 충청권 3개교만 막대로 그려져야 한다(V08).

    현재 chart_generator.py:176 은 '연도' 로만 필터하고 region_name 은 제목 문자열에만
    쓰인다. 그래서 6개 권역이 모두 담긴 권역별_순위.csv 를 넘기면
    "충청권 대학 비교" 제목 아래 전국 대학이 전부 그려진다.
    """
    frame = _multi_region_frame(2025)
    records = _capture_subplots(monkeypatch)

    cg.create_comparison_bar(frame, 2025, university="호서대학교", region_name="충청권")

    axes = records[-1]["axes"]
    drawn = [label.get_text() for label in axes.get_xticklabels()]
    assert len(axes.patches) == 3, (
        f"충청권 3개교만 그려져야 하는데 막대 {len(axes.patches)}개가 그려졌다: {drawn}"
    )
    assert set(drawn) == {"호서대학교", "순천향대학교", "선문대학교"}, f"수도권 대학이 섞였다: {drawn}"


@pytest.mark.characterization
def test_vis_u04_comparison_bar_title_always_shows_region_name(monkeypatch):
    """VIS-U04: 필터와 무관하게 제목에는 region_name 이 들어가는 현재 동작을 기록한다(특성화)."""
    records = _capture_subplots(monkeypatch)

    cg.create_comparison_bar(_multi_region_frame(2025), 2025, region_name="충청권")

    title = records[-1]["axes"].get_title()
    assert title == "2025년 충청권 대학 전임교원 1인당 SCI/SCOPUS 논문수"
    assert plt.get_fignums() == []


# ===========================================================================
# VIS-U05: create_rank_trend_chart 축 개수 분기
# ===========================================================================

@pytest.mark.parametrize(
    ("case_id", "rank_changes", "expected_args", "expected_figsize", "expected_axes"),
    [
        pytest.param(
            "권역순위-전부None",
            {2024: {"권역순위": None, "전국순위": 50}, 2025: {"권역순위": None, "전국순위": 45}},
            (),
            (7, 5),
            1,
            id="all-none-single-axis",
        ),
        pytest.param(
            "권역순위-전부존재",
            {2024: {"권역순위": 3, "전국순위": 50}, 2025: {"권역순위": 2, "전국순위": 45}},
            (1, 2),
            (12, 5),
            2,
            id="all-present-two-axes",
        ),
    ],
)
def test_vis_u05_rank_trend_axis_layout(
    monkeypatch, case_id, rank_changes, expected_args, expected_figsize, expected_axes
):
    """VIS-U05: 권역순위 유무에 따라 subplots 호출 인자(축 개수/figsize)가 달라진다."""
    records = _capture_subplots(monkeypatch)

    buf = cg.create_rank_trend_chart(rank_changes)

    assert len(records) == 1, f"subplots 가 {len(records)}회 호출됐다({case_id})"
    record = records[0]
    assert record["args"] == expected_args, f"{case_id}: subplots 위치 인자 불일치"
    assert record["kwargs"] == {"figsize": expected_figsize}, f"{case_id}: figsize 불일치"

    axes = record["axes"]
    if expected_axes == 1:
        assert isinstance(axes, matplotlib.axes.Axes), f"{case_id}: 단일 Axes 여야 한다"
    else:
        assert not isinstance(axes, matplotlib.axes.Axes)
        assert len(axes) == expected_axes, f"{case_id}: 축 {expected_axes}개여야 한다"

    assert buf.getvalue()[:8] == PNG_MAGIC
    assert plt.get_fignums() == []


@pytest.mark.characterization
def test_vis_u05_rank_trend_partial_none_raises_type_error():
    """VIS-U05: 권역순위가 '일부만' None 이면 TypeError 로 실패하는 현재 동작을 기록한다(특성화).

    has_regional 은 any() 로 판정하므로(chart_generator.py:291) 하나라도 값이 있으면
    권역 축을 그리려 하고, None 이 섞인 리스트를 그대로 ax1.plot 에 넘겨
    float(None) 에서 TypeError 가 난다. (Figure 누수 자체는 VIS-U03 에서 잠근다.)
    """
    rank_changes = {2024: {"권역순위": None, "전국순위": 50}, 2025: {"권역순위": 2, "전국순위": 45}}

    with pytest.raises(TypeError) as excinfo:
        cg.create_rank_trend_chart(rank_changes)

    assert "NoneType" in str(excinfo.value), f"예상과 다른 TypeError: {excinfo.value}"


# ===========================================================================
# VIS-U06: _setup_korean_font OS 분기
# ===========================================================================

class _FakeFontEntry:
    """font_manager.ttflist 원소 대역(stub): name 속성만 필요하다."""

    def __init__(self, name: str):
        self.name = name


class _FakeFontManagerModule:
    """`cg._fm`(matplotlib.font_manager) 대역(stub)."""

    def __init__(self, installed: list):
        self.added: list = []
        self.fontManager = types.SimpleNamespace(
            ttflist=[_FakeFontEntry(name) for name in installed],
            addfont=self.added.append,
        )


def _make_fake_path(exists: bool):
    """`cg.Path` 대역: exists() 결과를 고정한다 (pathlib 전역 오염 방지)."""

    class _FakePath:
        def __init__(self, raw: str):
            self.raw = raw

        def exists(self) -> bool:
            return exists

    return _FakePath


@pytest.mark.parametrize(
    ("system", "installed", "nanum_exists", "expected_family", "expected_added"),
    [
        pytest.param("Windows", [], True, "Malgun Gothic", [], id="Windows"),
        pytest.param("Darwin", ["Apple SD Gothic Neo"], True, "Apple SD Gothic Neo", [],
                     id="Darwin-apple-sd-gothic-neo"),
        pytest.param("Darwin", ["Helvetica"], True, "AppleGothic", [], id="Darwin-fallback"),
        pytest.param("Linux", [], True, "NanumGothic",
                     ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf"], id="Linux-nanum-present"),
        pytest.param("Linux", [], False, "NanumGothic", [], id="Linux-nanum-absent"),
    ],
)
def test_vis_u06_setup_korean_font_per_os(
    monkeypatch, system, installed, nanum_exists, expected_family, expected_added
):
    """VIS-U06: OS 3분기에서 rcParams['font.family'] 와 addfont 호출이 기대대로 결정된다."""
    fake_fm = _FakeFontManagerModule(installed)
    monkeypatch.setattr(cg, "_platform", types.SimpleNamespace(system=lambda: system))
    monkeypatch.setattr(cg, "_fm", fake_fm)
    monkeypatch.setattr(cg, "Path", _make_fake_path(nanum_exists))

    with matplotlib.rc_context():
        cg._setup_korean_font()

        assert matplotlib.rcParams["font.family"] == [expected_family], (
            f"{system} 분기 폰트 불일치: {matplotlib.rcParams['font.family']}"
        )
        assert matplotlib.rcParams["axes.unicode_minus"] is False, "마이너스 기호 깨짐 방지 설정이 빠졌다"

    assert fake_fm.added == expected_added, f"{system} 분기 addfont 호출 불일치: {fake_fm.added}"


# ===========================================================================
# VIS-U07: 대학명 [:-2] 절단
# ===========================================================================

@pytest.mark.xfail(strict=True, reason="대학명 [:-2] 절단이 괄호 표기 대학을 깨뜨림")
def test_vis_u07_compare_group_bar_title_not_truncated(monkeypatch):
    """VIS-U07: 괄호가 붙은 대학명이어도 제목에 깨진 절단 문자열이 남으면 안 된다.

    chart_generator.py:381 은 `univ[:-2]` 로 '대학교' 의 뒤 두 글자를 잘라
    "호서" 같은 접두어를 만든다. '고려대학교(세종)' 처럼 괄호 표기가 붙은
    대학명에서는 '고려대학교(세' 라는 깨진 문자열이 그대로 제목에 들어간다.
    """
    university = "고려대학교(세종)"
    compare_data = [
        {"학교명": university, "1인당논문수": 0.2451},
        {"학교명": "선문대학교", "1인당논문수": 0.1333},
    ]
    records = _capture_subplots(monkeypatch)

    cg.create_compare_group_bar(compare_data, 2025, university=university)

    title = records[-1]["axes"].get_title()
    assert "고려대학교(세비교군" not in title, f"절단된 대학명이 제목에 남았다: {title!r}"


@pytest.mark.xfail(strict=True, reason="대학명 [:-2] 절단이 괄호 표기 대학을 깨뜨림")
def test_vis_u07_trend_chart_legend_not_truncated(monkeypatch):
    """VIS-U07: 추이 차트 범례(legend)의 비교군 라벨도 절단으로 깨지면 안 된다."""
    university = "고려대학교(세종)"
    records = _capture_subplots(monkeypatch)

    cg.create_trend_chart(_trend(), _averages(), university=university)

    labels = [text.get_text() for text in records[-1]["axes"].get_legend().get_texts()]
    assert "고려대학교(세비교군 평균" not in labels, f"절단된 대학명이 범례에 남았다: {labels}"


@pytest.mark.characterization
def test_vis_u07_truncation_is_harmless_for_plain_names(monkeypatch):
    """VIS-U07: '…대학교' 형태의 평범한 이름에서는 [:-2] 가 의도대로 동작함을 기록한다(특성화).

    주의: 이 단언은 `[:-2]` 절단 메커니즘 자체를 고정한다. VIS-U07 을 고치면서
    절단 방식을 바꾸면(예: '대학교' suffix 제거) 기대 문자열도 함께 갱신해야 한다.
    """
    records = _capture_subplots(monkeypatch)

    cg.create_compare_group_bar(_compare_rows(), 2025, university="호서대학교")

    title = records[-1]["axes"].get_title()
    assert title == "2025년 호서대비교군 1인당 SCI/SCOPUS 논문수"
    assert plt.get_fignums() == []
