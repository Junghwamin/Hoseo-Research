"""UI-01~UI-13 — report_app/components/* 및 report_app/pages/home.py 컴포넌트 테스트.

각 컴포넌트를 app.py 없이 단독으로 AppTest.from_function 으로 띄워
반환값 / 위젯 트리 / session_state 부작용을 관측 경계에서 고정한다.

하네스 제약 (tests/conftest.py 참조):
    - AppTest.from_function 에 넘기는 래퍼 함수의 **본문은 ASCII 전용**이어야 한다.
      Windows 에서 임시 스크립트가 cp949 로 기록되고 UTF-8 로 해석되어
      한글이 들어가면 SyntaxError 가 난다. 한글 문자열은 kwargs 로 주입한다.
      (이 테스트 파일 본체는 UTF-8 로 읽히므로 한글 이름/독스트링 사용 가능)
    - at.session_state 에는 .get() 이 없다. sget() 헬퍼를 쓴다.
    - sys.path / cwd / MPLBACKEND 는 conftest 모듈 레벨에서 이미 확정되어 있다.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from tests.fixtures.tiny_png import SMALL_PNG_BYTES

# 첫 run 은 fragment/dialog 초기화 때문에 기본값 3초를 넘길 수 있다.
_TIMEOUT = 30


# ===========================================================================
# 공통 헬퍼
# ===========================================================================
def sget(at: AppTest, key: str, default=None):
    """at.session_state 에는 .get() 이 없어 KeyError 를 직접 흡수한다."""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def _md_text(at: AppTest) -> str:
    """렌더된 모든 markdown 요소를 하나의 문자열로 합친다."""
    return "\n".join(m.value for m in at.markdown)


def _btn_map(at: AppTest) -> dict[str, bool]:
    """버튼 key -> disabled 매핑. 렌더되지 않은 버튼은 키 자체가 없다."""
    return {b.key: b.disabled for b in at.button}


def _require_clean(at: AppTest, what: str) -> AppTest:
    """렌더 크래시를 RuntimeError 로 올린다.

    AssertionError 로 올리면 xfail(raises=AssertionError) 결함 잠금 테스트가
    '기대한 실패'로 흡수해 크래시를 숨긴다. 반드시 다른 예외형이어야 한다.
    """
    if at.exception:
        raise RuntimeError(f"{what} 렌더 중 예외: {[e.value for e in at.exception]}")
    return at


# ===========================================================================
# AppTest 래퍼 — 본문은 반드시 ASCII 전용 (파일 상단 주석 참조)
# ===========================================================================
def _w_sidebar(current_module, current_step, max_step, api_key_set):
    import streamlit as st
    from report_app.components.sidebar import render_sidebar

    st.session_state["_ret"] = render_sidebar(
        current_module=current_module,
        current_step=current_step,
        max_step=max_step,
        api_key_set=api_key_set,
    )


def _w_toolbar(module_name, step_name):
    from report_app.components.toolbar import render_toolbar

    render_toolbar(module_name, step_name)


def _w_metric_cards(metrics):
    from report_app.components.metric_card import render_metric_cards

    render_metric_cards(metrics)


def _w_gpt_section(section_key, title, hint, mode, result):
    import streamlit as st
    from report_app.components.gpt_section import render_gpt_section

    def _ok():
        return result

    def _boom():
        raise RuntimeError("rate_limit_exceeded")

    fn = {"ok": _ok, "raise": _boom}.get(mode)
    render_gpt_section(
        section_key=section_key,
        title=title,
        hint=hint,
        generate_fn=fn,
    )


def _w_chart_card(title, subtitle, png, rows, chart_key):
    import pandas as pd
    from io import BytesIO
    from report_app.components.chart_card import render_chart_card

    df = pd.DataFrame(rows) if rows else None
    render_chart_card(
        title=title,
        subtitle=subtitle,
        chart_buf=BytesIO(png),
        breakdown_df=df,
        chart_key=chart_key,
        year=2025,
    )


def _w_home():
    import streamlit as st
    from report_app.pages.home import render_home

    st.session_state["_ret"] = render_home()


# ===========================================================================
# AppTest 빌더
# ===========================================================================
def _run_sidebar(
    current_module: str = "research",
    current_step: int = 1,
    max_step: int = 1,
    api_key_set: bool = False,
) -> AppTest:
    at = AppTest.from_function(
        _w_sidebar,
        kwargs={
            "current_module": current_module,
            "current_step": current_step,
            "max_step": max_step,
            "api_key_set": api_key_set,
        },
        default_timeout=_TIMEOUT,
    )
    at.run()
    return _require_clean(at, "사이드바")


def _run_chart_card(
    title: str = "연도별 추이",
    subtitle: str = "2023~2025년",
    rows: list[dict] | None = None,
    chart_key: str = "trend",
) -> AppTest:
    at = AppTest.from_function(
        _w_chart_card,
        kwargs={
            "title": title,
            "subtitle": subtitle,
            "png": SMALL_PNG_BYTES,
            "rows": rows,
            "chart_key": chart_key,
        },
        default_timeout=_TIMEOUT,
    )
    at.run()
    return _require_clean(at, "차트 카드")


def _run_gpt_section(
    section_key: str = "narrative_trend",
    title: str = "섹션 1. 연도별 추이",
    hint: str = "연도별 수치 변화 분석",
    mode: str = "ok",
    result: str = "GPT 가 생성한 서술 본문.",
) -> AppTest:
    at = AppTest.from_function(
        _w_gpt_section,
        kwargs={
            "section_key": section_key,
            "title": title,
            "hint": hint,
            "mode": mode,
            "result": result,
        },
        default_timeout=_TIMEOUT,
    )
    at.run()
    return _require_clean(at, "GPT 섹션")


def _run_metric_cards(metrics: list[dict]) -> AppTest:
    at = AppTest.from_function(
        _w_metric_cards, kwargs={"metrics": metrics}, default_timeout=_TIMEOUT
    )
    at.run()
    return _require_clean(at, "메트릭 카드")


def _run_home() -> AppTest:
    at = AppTest.from_function(_w_home, default_timeout=_TIMEOUT)
    at.run()
    return _require_clean(at, "홈")


# ===========================================================================
# UI-01 — CSS 계약
# ===========================================================================
# UI-01 은 이 파일이 아니라 tests/contract/test_css_contract.py 에서 다룬다.
# (styles.py 가 정의하는 클래스 집합 vs 컴포넌트가 참조하는 클래스 집합 대조는
#  AppTest 런타임이 아니라 정적 계약 검사에 속하므로 담당 파일을 분리했다.)


# ===========================================================================
# UI-02 — 사이드바 모듈 클릭
# ===========================================================================
def test_ui02_모듈_버튼_클릭시_선택_모듈을_반환하고_클릭_플래그를_소비한다():
    """home 에서 '연구실적' 클릭 → ('research', None) 반환, 내부 플래그는 남지 않는다."""
    at = _run_sidebar(current_module="home", current_step=0, max_step=1)

    # 클릭 전: 현재 모듈이 그대로 반환된다.
    assert sget(at, "_ret") == ("home", None)
    # 활성 모듈(home)은 버튼이 아니라 HTML div 로 렌더되므로 버튼 트리에 없다.
    assert "sidebar_mod_home" not in _btn_map(at)

    at.button(key="sidebar_mod_research").click().run()

    assert sget(at, "_ret") == ("research", None)
    # on_click 콜백이 세운 플래그는 render_sidebar 가 같은 run 에서 pop 한다.
    assert "_nav_module_clicked" not in at.session_state


# ===========================================================================
# UI-03 — 사이드바 단계 게이팅
# ===========================================================================
def test_ui03_단계_게이팅은_max_step_이하만_활성화하고_현재_단계는_버튼을_렌더하지_않는다():
    """current_step=3, max_step=3 → 1·2단계 활성, 3단계 버튼 부재, 4·5단계 비활성."""
    at = _run_sidebar(current_module="research", current_step=3, max_step=3)
    buttons = _btn_map(at)

    # 키는 0-based (sidebar_step_0 == 1단계)
    assert buttons["sidebar_step_0"] is False, "완료된 1단계는 클릭 가능해야 한다"
    assert buttons["sidebar_step_1"] is False, "완료된 2단계는 클릭 가능해야 한다"
    assert "sidebar_step_2" not in buttons, "현재 단계(3)는 HTML 로만 렌더되어 버튼이 없다"
    assert buttons["sidebar_step_3"] is True, "max_step 초과인 4단계는 비활성"
    assert buttons["sidebar_step_4"] is True, "max_step 초과인 5단계는 비활성"


def test_ui03_활성_단계_버튼_클릭시_1indexed_단계번호를_반환한다():
    """sidebar_step_0(=1단계) 클릭 → ('research', 1)."""
    at = _run_sidebar(current_module="research", current_step=3, max_step=3)

    at.button(key="sidebar_step_0").click().run()

    assert sget(at, "_ret") == ("research", 1)
    assert "_nav_step_clicked" not in at.session_state


# ===========================================================================
# UI-04 — '처음부터 다시' 버튼 (V04 전제)
# ===========================================================================


# ===========================================================================
# UI-05 — 사이드바 API Key 영역
# ===========================================================================
@pytest.mark.parametrize(
    ("api_key_set", "expected", "forbidden"),
    [
        (False, "미설정", "설정됨"),
        (True, "설정됨", "미설정"),
    ],
    ids=["unset", "set"],
)
def test_ui05_api_key_상태_뱃지는_설정_여부에_따라_달라진다(api_key_set, expected, forbidden):
    at = _run_sidebar(api_key_set=api_key_set)
    markdown = _md_text(at)

    assert expected in markdown
    assert forbidden not in markdown


def test_ui05_변경_버튼_클릭시_sidebar_api_change_플래그가_남는다():
    """이 플래그는 sidebar 가 pop 하지 않는다 — 소비 책임은 app.py 에 있다."""
    at = _run_sidebar(api_key_set=False)

    at.button(key="sidebar_api_change_btn").click().run()

    assert sget(at, "sidebar_api_change") is True


# ===========================================================================
# UI-06 — 상단 툴바
# ===========================================================================
def test_ui06_툴바는_단일_마크다운에_모듈명_단계명_날짜_버전을_담는다():
    module_name = "전임교원 연구실적 분석"
    step_name = "2단계: 통계 확인"
    today = datetime.now().strftime("%Y-%m-%d")  # 렌더 직전에 계산 (자정 경계 회피)

    at = AppTest.from_function(
        _w_toolbar,
        kwargs={"module_name": module_name, "step_name": step_name},
        default_timeout=_TIMEOUT,
    )
    at.run()
    _require_clean(at, "툴바")

    assert len(at.markdown) == 1, "툴바는 단일 st.markdown 으로 렌더되어야 한다"
    html = at.markdown[0].value
    assert module_name in html
    assert step_name in html
    assert today in html
    assert "v5.0" in html


@pytest.mark.parametrize(
    ("step_name", "expected_items"),
    [("2단계: 통계 확인", 3), (None, 2)],
    ids=["with_step", "without_step"],
)
def test_ui06_브레드크럼_항목수는_단계명_유무에_따라_결정된다(step_name, expected_items):
    """단계명이 있으면 홈/모듈/단계 3개, 없으면 홈/모듈 2개."""
    at = AppTest.from_function(
        _w_toolbar,
        kwargs={"module_name": "연구실적", "step_name": step_name},
        default_timeout=_TIMEOUT,
    )
    at.run()
    _require_clean(at, "툴바")

    assert at.markdown[0].value.count("ir-toolbar-breadcrumb-item") == expected_items


# ===========================================================================
# UI-07 — 메트릭 카드
# ===========================================================================
@pytest.mark.parametrize(
    ("delta_type", "arrow"),
    [("up", "▲"), ("down", "▼")],
    ids=["up", "down"],
)
def test_ui07_delta_type_에_따라_방향_클래스와_화살표가_붙는다(delta_type, arrow):
    at = _run_metric_cards(
        [{"label": "1인당 논문수", "value": "0.2847", "delta": "+12.3%", "delta_type": delta_type}]
    )

    html = at.markdown[0].value
    assert f"ir-metric-delta {delta_type}" in html
    assert arrow in html


def test_ui07_delta_가_없으면_delta_영역을_렌더하지_않는다():
    at = _run_metric_cards([{"label": "전임교원수", "value": "1,024"}])

    assert "ir-metric-delta" not in at.markdown[0].value


def test_ui07_빈_리스트를_넘기면_아무것도_렌더하지_않는다():
    at = _run_metric_cards([])

    assert len(at.markdown) == 0


# ===========================================================================
# UI-08 — GPT 서술 섹션 (@st.fragment)
# ===========================================================================
def test_ui08_생성_버튼_클릭시_결과가_session_state_와_text_area_에_모두_반영된다():
    """@st.fragment 는 AppTest 에서 스크립트 전체 재실행으로 관측된다."""
    result = "GPT 가 생성한 서술 본문."
    at = _run_gpt_section(section_key="narrative_trend", mode="ok", result=result)

    assert at.text_area[0].value == "", "생성 전에는 빈 text_area 여야 한다"

    at.button(key="gen_narrative_trend").click().run()

    assert sget(at, "narrative_trend") == result
    assert at.text_area[0].value == result
    assert len(at.error) == 0


def test_ui08_generate_fn_이_없으면_생성_버튼이_비활성화된다():
    at = _run_gpt_section(section_key="narrative_avg", mode="none")

    assert _btn_map(at)["gen_narrative_avg"] is True


def test_ui08_generate_fn_이_예외를_던지면_st_error_로_표시된다():
    at = _run_gpt_section(section_key="narrative_region", mode="raise")

    at.button(key="gen_narrative_region").click().run()

    assert len(at.error) >= 1
    assert "rate_limit_exceeded" in at.error[0].value
    assert not at.exception, "예외는 컴포넌트 내부에서 흡수되어야 한다"


# ===========================================================================
# UI-09 — 차트 카드
# ===========================================================================
def test_ui09_breakdown_이_있으면_제목_마크다운과_데이터프레임_다운로드버튼을_각각_1개_렌더한다():
    title = "연도별 1인당 논문수 추이"
    at = _run_chart_card(title=title, rows=[{"연도": 2024, "값": 0.2}, {"연도": 2025, "값": 0.3}])

    assert title in at.markdown[0].value, "첫 markdown 이 카드 헤더(제목)여야 한다"
    assert len(at.dataframe) == 1
    assert len(at.get("download_button")) == 1


def test_ui09_확대_버튼_클릭시_다이얼로그_인자_3종이_session_state_에_적재된다():
    """@st.dialog 은 인자를 직접 못 받아 _chart_dialog_* 키를 경유한다."""
    title = "충청권 비교"
    at = _run_chart_card(title=title, rows=[{"학교명": "호서대학교", "순위": 3}], chart_key="region")

    at.button(key="zoom_region").click().run()

    assert sget(at, "_chart_dialog_title") == title
    assert sget(at, "_chart_dialog_buf") is not None
    assert sget(at, "_chart_dialog_df") is not None


# ===========================================================================
# UI-10 — 홈 화면
# ===========================================================================
def test_ui10_클릭이_없으면_None_을_반환한다():
    at = _run_home()

    assert "_ret" in at.session_state, "render_home 이 실행되지 않았다"
    assert at.session_state["_ret"] is None


def test_ui10_연구실적_카드_클릭시_research_를_반환한다():
    at = _run_home()

    at.button(key="home_research").click().run()

    assert sget(at, "_ret") == "research"


def test_ui10_준비중_모듈_카드의_버튼은_비활성화되어_있다():
    at = _run_home()
    buttons = _btn_map(at)

    assert buttons["home_edu"] is True
    assert buttons["home_emp"] is True


# ===========================================================================
# UI-11 — HTML 이스케이프 (결함 잠금)
# ===========================================================================
_ESCAPE_PROBE = "<b>X</b> & Y"


def _run_with_untrusted_title(component: str) -> AppTest:
    """사용자 제공 문자열이 그대로 제목으로 들어가는 세 컴포넌트를 각각 렌더한다."""
    if component == "chart_card":
        return _run_chart_card(title=_ESCAPE_PROBE, chart_key="escape")
    if component == "gpt_section":
        return _run_gpt_section(section_key="narrative_escape", title=_ESCAPE_PROBE, mode="none")
    if component == "metric_card":
        return _run_metric_cards([{"label": _ESCAPE_PROBE, "value": "1"}])
    raise RuntimeError(f"알 수 없는 컴포넌트: {component}")


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="V18: HTML 미이스케이프 — unsafe_allow_html=True 마크다운에 문자열을 그대로 보간한다",
)
@pytest.mark.parametrize("component", ["chart_card", "gpt_section", "metric_card"])
def test_ui11_제목_문자열의_html_특수문자는_이스케이프되어야_한다(component):
    """수정 후 기대 동작: html.escape() 를 거쳐 <b> 가 &lt;b&gt; 로 렌더된다."""
    at = _run_with_untrusted_title(component)
    markdown = _md_text(at)

    assert "&lt;b&gt;" in markdown, (
        f"{component}: 제목이 이스케이프되지 않아 원문 태그가 그대로 DOM 에 삽입된다"
    )


# ===========================================================================
# UI-12 — st.image / st.dataframe 의 use_container_width 지원 중단 경고
# ===========================================================================
# 주의: streamlit 은 logger 마다 propagate=False 를 설정하므로(logger.py:124)
# caplog 의 기본 루트 핸들러로는 이 경고를 절대 잡을 수 없다.
# 실제 방출 지점(streamlit.deprecation_util)에 caplog.handler 를 직접 붙인다.
_DEPRECATION_LOGGER = "streamlit.deprecation_util"


@pytest.mark.characterization
def test_ui12_차트_카드는_지원중단된_use_container_width_경고를_2건_발생시킨다(caplog):
    """현행 동작 기록 — 수정 후 삭제.

    chart_card 는 st.image 와 st.dataframe 에 각각 use_container_width=True 를
    넘긴다. 이 파라미터는 2025-12-31 이후 제거 예정이므로 width= 로 바꿔야 한다.
    경고는 브라우저가 아니라 로거로만 나가 at.warning 에는 잡히지 않는다.
    """
    caplog.set_level(logging.WARNING, logger=_DEPRECATION_LOGGER)
    emitter = logging.getLogger(_DEPRECATION_LOGGER)
    emitter.addHandler(caplog.handler)
    try:
        at = _run_chart_card(rows=[{"연도": 2025, "값": 0.3}], chart_key="deprecation")
    finally:
        # 프로세스 전역 로거에 테스트별 핸들러를 남기면 다른 파일까지 오염된다.
        emitter.removeHandler(caplog.handler)

    assert len(at.warning) == 0, "지원 중단 경고는 st.warning 으로 노출되지 않는다"

    hits = [r for r in caplog.records if "use_container_width" in r.getMessage()]
    assert len(hits) == 2, (
        f"st.image + st.dataframe 에서 2건을 기대했으나 {len(hits)}건: "
        f"{[r.getMessage()[:60] for r in caplog.records]}"
    )


# ===========================================================================
# UI-13 — chart_card 의 breakdown 래핑 (결함 잠금)
# ===========================================================================
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="D11 chart_card 래핑 불완전 — 여는 div 와 닫는 div 가 별도 markdown 으로 쪼개져 "
    "Streamlit 이 자동 삽입하는 컨테이너 사이에서 무효 HTML 이 된다",
)
def test_ui13_breakdown_래핑에_고아_닫는_div_마크다운이_없어야_한다():
    """수정 후 기대 동작: 래핑은 단일 markdown 또는 st.container 로 처리한다."""
    at = _run_chart_card(rows=[{"연도": 2025, "값": 0.3}], chart_key="wrap")

    orphans = [m.value for m in at.markdown if m.value.strip() == "</div>"]

    assert not orphans, f"닫는 태그만 담긴 markdown 요소가 존재한다: {orphans}"
