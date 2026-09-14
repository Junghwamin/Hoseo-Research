"""Phase 3.5 리뷰에서 추가된 research.py 결함의 AppTest 잠금.

`tests/apptest/test_research_flow.py` 는 다른 에이전트가 작성했으므로
건드리지 않고 새 파일에 추가한다.

- R-RS-02 : 대상 대학이 비교군 권역 밖이면 비교군이 자기 자신 1개가 된다
"""

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import PROJECT_ROOT

APP = str((PROJECT_ROOT / "report_app" / "app.py").resolve())


def sget(at, key, default=None):
    """AppTest 의 SafeSessionState 에는 .get() 이 없다."""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def _keys(at, kind):
    return {el.key for el in at.get(kind) if getattr(el, "key", None)}


def _boot():
    at = AppTest.from_file(APP, default_timeout=60)
    # secrets 를 비우지 않으면 개발 머신의 실제 secrets.toml 로 폴백한다.
    at.secrets["_dummy"] = "x"
    at.run()
    assert at.exception == [], [e.value for e in at.exception]
    return at


def _load_existing(at):
    """기존 output/ CSV 로 데이터를 로드하고 1단계 필터 화면까지 간다."""
    at.button(key="home_research").click().run()
    at.button(key="src_existing").click().run()
    # '기존 파일로 분석 시작' — key 가 없는 버튼이라 라벨로 찾는다
    start = [b for b in at.button if "기존 파일" in (b.label or "")]
    if not start:
        pytest.skip("기존 output/ 소스 카드를 찾지 못했다 (샌드박스에 CSV 없음)")
    start[0].click().run()
    assert sget(at, "data_loaded") is True
    # 2단계로 이동했으므로 1단계로 되돌아가 필터를 연다
    if "sidebar_step_0" in _keys(at, "button"):
        at.button(key="sidebar_step_0").click().run()
    assert at.exception == [], [e.value for e in at.exception]
    return at


def _select_out_of_region_target(at):
    """비교군(천안·아산 5개교)과 다른 권역의 대학을 대상으로 고른다."""
    sel = [s for s in at.selectbox if s.key == "_filter_target_univ"]
    if not sel:
        pytest.skip("_filter_target_univ 셀렉트박스가 렌더되지 않았다")
    options = list(sel[0].options)
    target = next((u for u in ("제주국제대학교", "제주대학교") if u in options), None)
    if target is None:
        pytest.skip("제주권 대학이 데이터에 없다")
    sel[0].select(target).run()
    assert at.exception == [], [e.value for e in at.exception]
    return at, target


@pytest.mark.realdata
@pytest.mark.characterization
def test_rrs02_타권역_대상_선택시_비교군이_자기자신뿐이다():
    """[수정 후 삭제] 현행 동작 기록.

    config.COMPARE_GROUP 5개교가 전부 충청권이라, 대상이 타 권역이면
    기본 체크(research.py:437-440)가 전부 False 가 되고
    :488 compare_candidates=[] -> :500 compare_group_final=[target] 가 된다.
    """
    at = _load_existing(_boot())
    at, target = _select_out_of_region_target(at)

    ms = [m for m in at.multiselect if m.key == "_filter_compare_widget"]
    assert ms, "비교군 multiselect 가 렌더되지 않았다"
    assert list(ms[0].options) == [], (
        f"비교군 후보가 비어 있어야 현행 결함이다. 실제: {list(ms[0].options)}"
    )


@pytest.mark.realdata
def test_rrs02_타권역_대상이어도_비교군이_성립해야_한다():
    """수정 후 기대 (구현 중립).

    둘 중 하나를 만족하면 통과한다.
    (a) 비교군 후보가 2개 이상 제시된다 (권역 상위 N개 자동 채움), 또는
    (b) 비교군이 성립하지 않는다는 경고가 화면에 표시된다.
    """
    at = _load_existing(_boot())
    at, target = _select_out_of_region_target(at)

    ms = [m for m in at.multiselect if m.key == "_filter_compare_widget"]
    candidates = list(ms[0].options) if ms else []
    warned = any(
        ("비교군" in (w.value or "")) for w in at.warning
    )

    assert len(candidates) >= 2 or warned, (
        f"{target} 선택 시 비교군 후보가 {len(candidates)}개이고 경고도 없다. "
        "비교군평균이 대상 대학 자기 값이 되는데 사용자에게 알려지지 않는다."
    )
