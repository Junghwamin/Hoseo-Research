"""R7-13: pages/research.py 의 비렌더(bare) 모드 헬퍼 단위 테스트.

AppTest 없이 ScriptRunContext 가 없는 상태에서 st.session_state 를 직접
조작하여 _go / _calc_stats / _target_univ / _target_region 의 계약을 잠근다.

주의: 모든 테스트는 bare_session_state 픽스처를 요구한다(전역 mock 누수 방지).
"""

from unittest.mock import MagicMock

import pytest

import report_app.pages.research as research
from report_app.config import UNIVERSITY


NARRATIVE_KEYS = (
    "narrative_trend",
    "narrative_comparison",
    "narrative_regional",
    "narrative_yoy",
)


# ---------------------------------------------------------------------------
# _target_univ / _target_region — 기본값 계약
# ---------------------------------------------------------------------------

def test_r7_13_target_univ_기본값은_config_UNIVERSITY(bare_session_state):
    assert research._target_univ() == UNIVERSITY


def test_r7_13_target_univ_설정값_우선(bare_session_state):
    bare_session_state["_target_university"] = "순천향대학교"
    assert research._target_univ() == "순천향대학교"


def test_r7_13_target_region_기본값은_충청권(bare_session_state):
    # 이 기본값이 V03 의 뿌리다: _target_region 이 미설정이어도
    # 라벨은 '충청권' 으로 표시되는 반면 _calc_stats 는 None 을 전달한다.
    assert research._target_region() == "충청권"


def test_r7_13_target_region_설정값_우선(bare_session_state):
    bare_session_state["_target_region"] = "제주권"
    assert research._target_region() == "제주권"


# ---------------------------------------------------------------------------
# _go — 백업/복원 계약
# ---------------------------------------------------------------------------

def test_r7_13_go_는_현재_서술을_saved_키에_백업한다(bare_session_state):
    bare_session_state["step"] = 4
    bare_session_state["narrative_trend"] = "abc"
    research._go(5)
    assert bare_session_state["_saved_narrative_trend"] == "abc"
    assert bare_session_state["step"] == 5


def test_r7_13_go_4단계_복귀시_백업값을_위젯키에_복원한다(bare_session_state):
    """비렌더 모드의 4->5->4 왕복.

    bare 모드에는 위젯 생명주기가 없어 narrative_* 키가 살아남으므로
    백업-복원이 정상 동작한다. 실제 앱에서 이 왕복이 깨지는 이유(위젯 키 제거)는
    tests/apptest/test_research_flow.py 의 R7-01 이 잠근다.
    """
    bare_session_state["step"] = 4
    for k in NARRATIVE_KEYS:
        bare_session_state[k] = f"typed-{k}"

    research._go(5)
    for k in NARRATIVE_KEYS:
        assert bare_session_state[f"_saved_{k}"] == f"typed-{k}"

    research._go(4)
    for k in NARRATIVE_KEYS:
        assert bare_session_state[k] == f"typed-{k}"
    assert bare_session_state["step"] == 4


def test_r7_13_go_는_4단계_아닌_목적지에서는_복원하지_않는다(bare_session_state):
    bare_session_state["_saved_narrative_trend"] = "saved"
    research._go(2)
    assert "narrative_trend" not in bare_session_state
    assert bare_session_state["step"] == 2


def test_r7_13_go_는_4단계가_아닐_때_백업을_파괴하지_않아야_한다(bare_session_state):
    """수정 후 기대: 백업은 '현재 단계가 4일 때'만 수행한다."""
    bare_session_state["step"] = 3
    bare_session_state["_saved_narrative_trend"] = "사용자가 입력한 서술"
    research._go(4)
    assert bare_session_state["narrative_trend"] == "사용자가 입력한 서술"
    assert bare_session_state["_saved_narrative_trend"] == "사용자가 입력한 서술"


# ---------------------------------------------------------------------------
# _calc_stats — data_loader 5함수 키워드 전달 계약
# ---------------------------------------------------------------------------

@pytest.fixture()
def _stub_dl(monkeypatch):
    """data_loader 5개 함수를 MagicMock 으로 교체하고 딕셔너리로 돌려준다."""
    mocks = {}
    for name in (
        "get_hoseo_trend",
        "get_averages",
        "get_rank_changes",
        "get_yoy_changes",
        "get_compare_group_data",
    ):
        m = MagicMock(return_value={})
        monkeypatch.setattr(research.dl, name, m)
        mocks[name] = m
    return mocks


def _seed_state(ss, **over):
    ss["national_df"] = "NAT"
    ss["regional_df"] = "REG"
    ss["selected_year"] = 2025
    for k, v in over.items():
        ss[k] = v


def test_r7_13_calc_stats_는_5함수를_각각_한번씩_호출한다(bare_session_state, _stub_dl):
    _seed_state(bare_session_state)
    research._calc_stats()
    for name, m in _stub_dl.items():
        assert m.call_count == 1, name


def test_r7_13_calc_stats_는_대상대학과_권역을_키워드로_전달한다(bare_session_state, _stub_dl):
    _seed_state(
        bare_session_state,
        _target_university="순천향대학교",
        _target_region="충청권",
        _custom_compare_group=["A", "B"],
    )
    research._calc_stats()

    for name in ("get_hoseo_trend", "get_rank_changes", "get_yoy_changes"):
        assert _stub_dl[name].call_args.kwargs["university"] == "순천향대학교", name
    for name in ("get_averages", "get_compare_group_data"):
        assert _stub_dl[name].call_args.kwargs["compare_group"] == ["A", "B"], name
    for name, m in _stub_dl.items():
        assert m.call_args.kwargs["region_name"] == "충청권", name


def test_r7_13_calc_stats_는_라벨과_같은_권역을_계산해야_한다(bare_session_state, _stub_dl):
    """수정 후 기대(해석 중립): 계산에 쓰는 권역 == 화면이 표시하는 권역."""
    _seed_state(bare_session_state)
    research._calc_stats()
    expected = research._target_region()
    for name, m in _stub_dl.items():
        assert m.call_args.kwargs["region_name"] == expected, name
