"""report_app/pages/research.py 워크플로우 AppTest (FLT-01a/01b, R7-01~R7-12, R-RS-03).

이 파일은 실제 Streamlit 스크립트를 AppTest 로 구동해 5단계 워크플로우
(소스 선택 → 필터 → 통계 → 차트 → GPT 서술 → 보고서)를 관측 경계에서 검증한다.

잠근 결함
    V02(업로드 경로 미변환) · V03(로드 직후 권역 미설정) · V04(사이드바 리셋) ·
    V05(리셋 후 1단계 크래시) · V06(리셋 후 단계 잠금) · V07(서술 유실) ·
    V09(순위 부호 이중 반전) · V17(재로드 시 이전 상태 잔존) ·
    R-RS-01(권역평균 모집단이 필터에 잘림) · R-RS-03(증감 안내 연도 역순).
    현행 동작 기록: FLT-02(다중 권역 기본값) · R7-09b(R-RS-06 / V19).

테스트 방향 규칙
    - 확정 결함은 ``@pytest.mark.xfail(strict=True, raises=AssertionError)`` 로
      **고쳐진 뒤의 기대 동작**을 단언한다. ``xfail_strict = true`` 이므로 오늘
      통과하면(XPASS) 실패로 잡힌다. ``raises=`` 를 못박아 두면 렌더 크래시가
      XFAIL 로 흡수되지 않고 FAILED 로 드러난다.
    - 현재(결함 포함) 동작을 기록만 하는 테스트는 ``@pytest.mark.characterization``
      으로 오늘 통과해야 하며 결함 수정 시 함께 삭제한다.

하네스 전제 (tests/conftest.py 참조)
    - 모듈 레벨에서 cwd 가 SANDBOX 로 옮겨져 있고 output/*.csv 가 복사되어 있다.
    - AppTest.from_file 은 반드시 **절대경로**를 받아야 한다.
    - matplotlib 백엔드는 Agg 로 고정되어 있다.

측정된 하네스 사실
    - ``at.session_state`` 에는 ``.get()`` 이 없다 → ``_sget()`` 헬퍼를 쓴다.
    - 사이드바 단계 버튼 키는 **0-based** (``sidebar_step_0`` = 1단계)이며
      현재 단계의 버튼은 렌더되지 않는다.
    - "분석 시작" 계열 버튼에는 key 가 없다 → 라벨로 찾는다(``_btn``).
"""

from __future__ import annotations

import ast
from io import BytesIO

import pandas as pd
import pytest
from docx import Document
from streamlit.testing.v1 import AppTest

import report_app.chart_generator as cg
import report_app.data_loader as dl
import report_app.gpt_reporter as gpt_reporter
import report_app.pages.research as research
from tests.conftest import PROJECT_ROOT, REALDATA_AVAILABLE, SANDBOX
from tests.fixtures.tiny_png import fake_charts, small_png_buf

# 실데이터(output/*.csv)가 없으면 이 파일 전체가 의미를 잃는다.
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(
        not REALDATA_AVAILABLE,
        reason="output/전체_대학_데이터.csv · 권역별_순위.csv 가 없다",
    ),
]

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

#: 4단계 API Key 게이트를 통과시키기 위한 더미 값.
#: 저장소 위생 검사(INF-04)의 ``sk-[A-Za-z0-9_-]{20,}`` 패턴에 걸리지 않는 문자열이다.
_DUMMY_API_KEY = "dummy-apptest-key"

#: 기본 분석 대상(config.UNIVERSITY)과 그 권역.
_DEFAULT_UNIV = "호서대학교"
_DEFAULT_REGION = "충청권"

#: 4단계 text_area 위젯 키.
_NARRATIVE_KEYS = (
    "narrative_trend",
    "narrative_comparison",
    "narrative_regional",
    "narrative_yoy",
)

#: 리셋 이후 남아 있으면 안 되는 분석 상태 키 (R7-12).
#: research.py / app.py 를 직접 읽어 열거했다. 위젯 키(``_filter_*_widget``,
#: ``_univ_selector``, ``year_sel_*``, ``upload_*``)는 Streamlit 이 렌더 여부로
#: 스스로 관리하므로 감사 대상에서 뺀다.
_MUST_CLEAR_KEYS = (
    # app.py _DEFAULTS 에 포함된 분석 상태
    "national_df",
    "regional_df",
    "selected_year",
    "hoseo_trend",
    "averages",
    "rank_changes",
    "yoy_changes",
    "compare_data",
    "charts",
    "narrative_trend",
    "narrative_comparison",
    "narrative_regional",
    "narrative_yoy",
    "report_buf",
    "data_source",
    # _DEFAULTS 바깥에서 research.py 가 만드는 상태
    "data_loaded",
    "_raw_national_df",
    "_raw_regional_df",
    "_filter_years",
    "_filter_compare",
    "_filter_selected_univs",
    "_filter_compare_group",
    "_custom_compare_group",
    "_target_university",
    "_target_region",
    "_saved_narrative_trend",
    "_saved_narrative_comparison",
    "_saved_narrative_regional",
    "_saved_narrative_yoy",
    "_chart_dialog_title",
    "_chart_dialog_buf",
    "_chart_dialog_df",
)


# ---------------------------------------------------------------------------
# session_state / 위젯 접근 헬퍼
# ---------------------------------------------------------------------------

_MISSING = object()


def _sget(at: AppTest, key: str, default=None):
    """``at.session_state`` 는 ``.get()`` 을 제공하지 않으므로 직접 감싼다."""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def _btn(at: AppTest, label: str):
    """라벨로 버튼을 찾는다(키가 없는 버튼이 많다)."""
    matches = [b for b in at.button if b.label == label]
    assert matches, (
        f"라벨 '{label}' 버튼을 찾지 못했다. 현재 버튼: {[b.label for b in at.button]}"
    )
    return matches[0]


def _has_btn(at: AppTest, label: str) -> bool:
    return any(b.label == label for b in at.button)


def _btn_by_key(at: AppTest, key: str):
    matches = [b for b in at.button if b.key == key]
    assert matches, f"key '{key}' 버튼을 찾지 못했다. 현재 키: {[b.key for b in at.button]}"
    return matches[0]


def _has_key_btn(at: AppTest, key: str) -> bool:
    return any(b.key == key for b in at.button)


def _no_exception(at: AppTest) -> None:
    """앱이 조용히 죽는 것을 막는다. AppTest 는 예외를 at.exception 으로 삼킨다."""
    assert len(at.exception) == 0, f"앱 예외 발생: {[e.value for e in at.exception]}"


# ---------------------------------------------------------------------------
# 앱 구동 헬퍼
# ---------------------------------------------------------------------------

def _boot(app_script) -> AppTest:
    at = AppTest.from_file(str(app_script), default_timeout=60)
    at.run()
    _no_exception(at)
    return at


def _load_existing(at: AppTest) -> AppTest:
    """홈 → 연구실적 → 기존 output/ 선택 → 분석 시작.

    반환 시점의 상태: step=2, data_loaded=True, max_step=2.
    (``_render_source_existing`` 이 ``_go(2)`` 를 호출하기 때문)
    """
    at.button(key="home_research").click().run()
    at.button(key="src_existing").click().run()
    _btn(at, "✅ 기존 파일로 분석 시작").click().run()
    _no_exception(at)
    return at


def _back_to_step1(at: AppTest) -> AppTest:
    """2단계의 '← 1단계로' 버튼으로 1단계(필터 화면)로 되돌아간다."""
    _btn(at, "← 1단계로").click().run()
    _no_exception(at)
    return at


def _apply_filter(at: AppTest) -> AppTest:
    at.button(key="apply_filter").click().run()
    _no_exception(at)
    return at


def _seed_step(at: AppTest, step: int, *, with_charts: bool = True, api_key: bool = False):
    """데이터가 올라간 상태에서 특정 단계로 직접 점프한다.

    3단계 실제 차트 렌더(수 초)를 건너뛰기 위해 charts 를 시드한다.
    """
    if with_charts:
        at.session_state["charts"] = fake_charts()
    if api_key:
        at.session_state["api_key"] = _DUMMY_API_KEY
    at.session_state["max_step"] = 5
    at.session_state["step"] = step
    at.run()
    _no_exception(at)
    return at


# ---------------------------------------------------------------------------
# 실데이터 헬퍼
# ---------------------------------------------------------------------------

_raw_cache: dict[str, pd.DataFrame] = {}


def _raw_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """샌드박스에 복사된 실제 CSV 원본 (기대값 계산용)."""
    if not _raw_cache:
        _raw_cache["nat"] = pd.read_csv(
            SANDBOX / "output" / "전체_대학_데이터.csv", encoding="utf-8-sig"
        )
        _raw_cache["reg"] = pd.read_csv(
            SANDBOX / "output" / "권역별_순위.csv", encoding="utf-8-sig"
        )
    return _raw_cache["nat"], _raw_cache["reg"]


def _region_schools(region: str) -> set[str]:
    """원본 권역 CSV 기준 해당 권역 소속 학교명 집합."""
    _, reg = _raw_frames()
    return set(reg[reg["권역명"] == region]["학교명"].unique().tolist())


def _true_region_mean(year: int, region: str = _DEFAULT_REGION) -> float:
    """**원본 CSV** 기준 해당 권역 전체(충청권 29개교)의 1인당논문수 평균.

    기대값의 기준은 반드시 필터 이전 원본이어야 한다.
    ``session_state["regional_df"]`` 는 필터에서 체크된 소수 대학으로 이미
    잘려 있어(R-RS-01), 그것을 기준으로 삼으면 단언이 항상 참이 되어 버린다.
    반올림 자릿수는 ``data_loader.get_averages`` 와 맞춘다.
    """
    _, reg = _raw_frames()
    sub = reg[(reg["연도"] == year) & (reg["권역명"] == region)]
    assert not sub.empty, f"원본 CSV 에 {year}년 {region} 데이터가 없다"
    return round(float(sub["1인당논문수"].mean()), 4)


def _yoy_school_names(yoy: dict) -> list[str]:
    return [r["학교명"] for r in yoy.get("상위", [])] + [
        r["학교명"] for r in yoy.get("하위", [])
    ]


def _docx_text(buf: BytesIO) -> str:
    """생성된 docx 의 문단 + 표 셀 텍스트를 모두 이어붙인다."""
    buf.seek(0)
    doc = Document(BytesIO(buf.getvalue()))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


# ===========================================================================
# FLT-01a  필터 적용의 양성 계약 (오늘 통과해야 한다)
# ===========================================================================

def test_flt_01a_filter_binds_region_and_compare_group(app_script):
    """FLT-01a: 필터를 적용하면 권역·대상대학·비교군·차트캐시가 일관되게 잡힌다.

    V03(권역 미설정) 의 정상 복구 경로다. 사용자가 1단계 필터를 실제로 적용하면
    ``_target_region`` 이 설정되고 차트 캐시가 무효화된다.

    평균값 자체의 정확성은 R-RS-01(FLT-01b) 이 별도로 잠근다.
    """
    at = _boot(app_script)
    _load_existing(at)
    _back_to_step1(at)
    _apply_filter(at)

    assert _sget(at, "_target_region") == _DEFAULT_REGION
    assert _sget(at, "_target_university") == _DEFAULT_UNIV

    compare = _sget(at, "_custom_compare_group")
    assert compare is not None, "필터 적용 후 비교군이 설정되어야 한다"
    assert _DEFAULT_UNIV in compare, f"대상 대학이 비교군에 포함되어야 한다: {compare}"

    # 통계가 실제로 재계산되었는지(빈 껍데기가 아닌지)만 확인한다.
    assert _sget(at, "averages"), "필터 적용 후 통계가 계산되어야 한다"
    assert _sget(at, "regional_df") is not None

    # 전년대비 증감 상/하위는 모두 대상 권역 소속이어야 한다.
    region_members = _region_schools(_DEFAULT_REGION)
    outsiders = [
        n for n in _yoy_school_names(_sget(at, "yoy_changes", {})) if n not in region_members
    ]
    assert not outsiders, f"{_DEFAULT_REGION} 밖 대학이 증감 표에 있다: {outsiders}"

    # 필터가 바뀌었으므로 차트 캐시는 비워져야 한다.
    assert _sget(at, "charts") == {}, "필터 적용 시 차트 캐시가 초기화되어야 한다"


# ===========================================================================
# FLT-01b  R-RS-01 — 필터가 권역평균의 모집단까지 잘라 버린다
# ===========================================================================

def test_flt_01b_region_average_uses_whole_region_population(app_script):
    """FLT-01b(R-RS-01): '권역평균' 은 권역 전체(충청권 29개교) 평균이어야 한다.

    비교군 선택은 '비교군평균' 에만 영향을 줘야 하며, 권역평균의 모집단을
    바꾸면 안 된다. 기대값은 반드시 **필터 이전 원본 CSV** 에서 계산한다
    (``session_state['regional_df']`` 는 이미 잘려 있어 기준이 될 수 없다).
    """
    at = _boot(app_script)
    _load_existing(at)
    _back_to_step1(at)
    _apply_filter(at)

    averages = _sget(at, "averages")
    base_year = _sget(at, "selected_year")
    assert averages and base_year in averages, "setup: 기준 연도 통계가 없다"

    stats = averages[base_year]
    expected = _true_region_mean(base_year, _DEFAULT_REGION)

    assert stats["권역평균"] == expected, (
        f"{base_year}년 권역평균이 {_DEFAULT_REGION} 전체 평균과 다르다: "
        f"{stats['권역평균']} != {expected}"
    )
    # 보조 단언: 오늘은 두 값이 완전히 같다(모집단이 같아져 버렸다).
    assert stats["권역평균"] != stats["비교군평균"], (
        "권역평균과 비교군평균의 모집단이 같아졌다 "
        f"(둘 다 {stats['권역평균']})"
    )


# ===========================================================================
# FLT-02  다중 권역 대학 (현행 동작 기록)
# ===========================================================================

def test_flt_02_multi_region_university_defaults_to_first_region(app_script):
    """FLT-02: 다중 권역 대학은 권역 선택 UI 가 뜨고, 기본값은 정렬상 첫 권역이다.

    단국대학교는 수도권·충청권 두 권역에 속한다. 기본 선택이 수도권이 되면
    천안·아산 비교군(전부 충청권)은 후보에서 사라진다. R-RS-02 수정 전에는
    이때 비교군이 대상 대학 1개만 남아 '비교군 평균' 이 대상 대학 자기 값과
    같아졌다. 지금은 권역순위 상위 대학으로 후보를 채우므로 비교군이 성립한다.
    """
    at = _boot(app_script)
    _load_existing(at)
    _back_to_step1(at)

    at.selectbox(key="_filter_target_univ").select("단국대학교").run()
    _no_exception(at)

    region_selects = [s for s in at.selectbox if s.key == "_filter_region_select"]
    assert region_selects, "다중 권역 대학에는 권역 선택 selectbox 가 떠야 한다"
    assert region_selects[0].options == ["수도권", "충청권"]
    assert region_selects[0].value == "수도권", "정렬상 첫 권역이 기본값"

    _apply_filter(at)

    assert _sget(at, "_target_university") == "단국대학교"
    assert _sget(at, "_target_region") == "수도권"

    # R-RS-02: 기본 비교군(전부 충청권)이 이 권역에 없어도 비교군이 성립해야 한다.
    compare_group = _sget(at, "_custom_compare_group") or []
    assert "단국대학교" in compare_group, "대상 대학은 항상 비교군에 포함된다"
    assert len(compare_group) >= 2, (
        f"비교군이 대상 대학 하나뿐이면 '비교군 평균' 이 자기 값과 같아진다: {compare_group}"
    )


# ===========================================================================
# R7-01  V07 — 단계 이동 시 GPT 서술 유실
# ===========================================================================

def _nav_button_5_then_4(at: AppTest) -> None:
    _btn(at, "다음: 보고서 생성 →").click().run()
    _btn(at, "← 4단계로").click().run()


def _nav_button_3_then_4(at: AppTest) -> None:
    _btn(at, "← 3단계로").click().run()
    _btn(at, "다음: GPT 서술 →").click().run()


def _nav_sidebar_5_then_word(at: AppTest) -> None:
    _btn_by_key(at, "sidebar_step_4").click().run()
    _btn(at, "📄 Word 보고서 생성").click().run()


_R7_01_PATHS = {
    "btn_step5_then_back": (_nav_button_5_then_4, 4),
    "btn_step3_then_forward": (_nav_button_3_then_4, 4),
    "sidebar_step5_then_word": (_nav_sidebar_5_then_word, 5),
}


@pytest.mark.parametrize("path_id", sorted(_R7_01_PATHS))
def test_r7_01_typed_narratives_survive_step_navigation(app_script, tmp_path, monkeypatch, path_id):
    """R7-01(V07): 4단계에서 직접 타이핑한 서술이 단계 이동 후에도 살아 있어야 한다.

    세 경로 모두를 잠근다.
        - btn_step5_then_back    : 4 → 5 → 4 (하단 버튼)
        - btn_step3_then_forward : 4 → 3 → 4 (하단 버튼)
        - sidebar_step5_then_word: 4 → 5 (사이드바) → Word 생성

    주의: session_state 에 값을 심는 것만으로는 결함이 재현되지 않는다.
    위젯에 실제로 입력해야 키가 위젯에 바인딩되어 삭제 대상이 된다.
    """
    monkeypatch.chdir(tmp_path)
    navigate, expected_step = _R7_01_PATHS[path_id]
    typed = {k: f"타이핑된 서술 {i}" for i, k in enumerate(_NARRATIVE_KEYS, start=1)}

    at = _boot(app_script)
    _load_existing(at)
    _seed_step(at, 4, api_key=True)

    # --- 타이핑 (setup 가드: 여기서 실패하면 결함이 아니라 준비 단계 문제다) ---
    for key, text in typed.items():
        at.text_area(key=key).input(text).run()
    _no_exception(at)
    for key, text in typed.items():
        assert at.text_area(key=key).value == text, "setup: 타이핑이 반영되지 않았다"

    # --- 단계 이동 ---
    navigate(at)
    _no_exception(at)
    assert _sget(at, "step") == expected_step

    # --- 수정 후 기대: 백업 키에 그대로 남아 있어야 한다 ---
    for key, text in typed.items():
        assert _sget(at, f"_saved_{key}") == text, f"_saved_{key} 유실"

    if expected_step == 4:
        # 4단계로 돌아왔다면 위젯에도 복원되어야 한다.
        for key, text in typed.items():
            assert at.text_area(key=key).value == text, f"{key} text_area 유실"
    else:
        # 5단계에서 만든 Word 보고서에 서술이 들어가야 한다.
        buf = _sget(at, "report_buf")
        assert buf is not None, "Word 보고서가 생성되지 않았다"
        text_in_docx = _docx_text(buf)
        for key, text in typed.items():
            assert text in text_in_docx, f"{key} 서술이 docx 에 없다"


# ===========================================================================
# R7-02  V04 — 사이드바 '처음부터 다시' 가 상태를 지우지 않는다
# ===========================================================================

def test_r7_02_sidebar_reset_clears_analysis_state(app_script):
    """R7-02(V04): 사이드바 '처음부터 다시' 는 분석 상태를 모두 초기화해야 한다."""
    at = _boot(app_script)
    _load_existing(at)
    at.session_state["narrative_trend"] = "리셋 대상 서술"
    _seed_step(at, 3)

    # setup 가드 — 지울 대상이 실제로 있어야 의미가 있다.
    assert _sget(at, "national_df") is not None
    assert _sget(at, "charts"), "setup: 차트 캐시가 채워져 있어야 한다"

    _btn_by_key(at, "sidebar_reset_btn").click().run()
    _no_exception(at)

    assert _sget(at, "national_df") is None, "national_df 가 남아 있다"
    assert _sget(at, "max_step") == 1, "max_step 이 1로 돌아가야 한다"
    assert _sget(at, "charts") == {}, "차트 캐시가 남아 있다"
    assert _sget(at, "narrative_trend") == "", "서술이 남아 있다"


# ===========================================================================
# R7-03  V05 — 리셋 후 재로드 시 1단계가 터진다
# ===========================================================================

def test_r7_03_step1_renders_after_reset_and_reload(app_script):
    """R7-03(V05): 5단계 리셋 → 재로드 → 1단계 복귀가 예외 없이 렌더되어야 한다."""
    at = _boot(app_script)
    _load_existing(at)
    _seed_step(at, 5)

    _btn(at, "🔄 처음부터").click().run()
    _no_exception(at)
    assert _sget(at, "step") == 1

    # 같은 소스로 다시 로드
    at.button(key="src_existing").click().run()
    _btn(at, "✅ 기존 파일로 분석 시작").click().run()
    _no_exception(at)

    # 1단계(필터 화면) 복귀 — 여기서 오늘은 TypeError 가 난다.
    _btn(at, "← 1단계로").click().run()

    assert len(at.exception) == 0, (
        f"1단계 복귀에서 예외: {[e.value for e in at.exception]}"
    )
    year_widgets = [m for m in at.multiselect if m.key == "_filter_years_widget"]
    assert year_widgets, "연도 선택 UI 가 렌더되어야 한다"
    raw_nat = _sget(at, "_raw_national_df")
    assert isinstance(raw_nat, pd.DataFrame) and not raw_nat.empty, (
        "1단계 렌더 후 원본 보관 프레임이 유효해야 한다"
    )


# ===========================================================================
# R7-04  V06 — 리셋 후에도 완료 단계 배지가 남는다
# ===========================================================================

def test_r7_04_step5_reset_locks_later_steps(app_script):
    """R7-04(V06): '처음부터' 이후 2~5단계는 다시 잠겨야 한다(max_step=1)."""
    at = _boot(app_script)
    _load_existing(at)
    _seed_step(at, 5)
    assert _sget(at, "max_step") == 5, "setup: 5단계까지 열려 있어야 한다"

    _btn(at, "🔄 처음부터").click().run()
    _no_exception(at)

    assert _sget(at, "max_step") == 1, "max_step 이 1로 돌아가야 한다"

    # 사이드바 단계 키는 0-based: sidebar_step_1~4 = 2~5단계.
    # 1단계(sidebar_step_0)는 현재 단계라 트리에 아예 없다(= disabled 가 아니라 부재).
    # 잠김 판정도 '부재 또는 disabled' 로 둬야 수정 방식에 중립적이다.
    unlocked = []
    for index in range(1, 5):
        key = f"sidebar_step_{index}"
        buttons = [b for b in at.button if b.key == key]
        if buttons and not buttons[0].disabled:
            unlocked.append(f"{key}({index + 1}단계)")
    assert not unlocked, f"리셋 후에도 클릭 가능한 단계가 있다: {unlocked}"


# ===========================================================================
# R7-05  V03 — 기존 파일 로드 직후 권역 기준이 없다
# ===========================================================================

def test_r7_05_stats_are_scoped_to_target_region_after_load(app_script):
    """R7-05(V03): 데이터 로드 직후의 통계도 대상 대학의 권역 기준이어야 한다.

    이 테스트는 **필터를 거치지 않은** 경로를 잠근다. ``region_name=None``
    이라 권역평균이 전국 6개 권역 전체 평균(0.2264)이 되는 문제다.
    필터를 거친 경로에서 5개교 평균(0.1814)이 되는 문제는 FLT-01b(R-RS-01)
    가 따로 잠근다 — 경로도 값도 다르고, 정답은 양쪽 다 충청권 전체 평균이다.

    해석 중립: 수정이 (a) 로드 시 권역을 자동 설정하든 (b) 1단계 필터를
    강제하든, 사용자가 2단계에서 보는 통계는 대상 권역 기준이어야 한다.
    """
    at = _boot(app_script)
    _load_existing(at)

    # (b) 안: 1단계에 머무르게 하는 수정이라면 필터를 눌러서 진행한다.
    if _sget(at, "step") == 1 and _has_key_btn(at, "apply_filter"):
        _apply_filter(at)

    averages = _sget(at, "averages")
    assert _sget(at, "regional_df") is not None and averages, "통계가 계산되어 있어야 한다"

    for year, stats in averages.items():
        expected = _true_region_mean(year, _DEFAULT_REGION)
        assert stats["권역평균"] == expected, (
            f"{year}년 권역평균이 {_DEFAULT_REGION} 기준이 아니다: "
            f"{stats['권역평균']} != {expected}"
        )

    region_members = _region_schools(_DEFAULT_REGION)
    outsiders = [n for n in _yoy_school_names(_sget(at, "yoy_changes", {})) if n not in region_members]
    assert not outsiders, f"{_DEFAULT_REGION} 밖 대학이 증감 표에 있다: {outsiders}"


# ===========================================================================
# R7-06  V09 — 순위 변화 부호가 이중 반전된다
# ===========================================================================

@pytest.mark.needs_refactor
def test_r7_06_rank_improvement_renders_as_up(app_script):
    """R7-06(V09): 권역순위가 5계단 올랐으면 초록 ▲ 로 표시되어야 한다.

    ``권역순위_변화`` 는 (전년순위 - 올해순위) 이므로 양수 = 순위 상승이다.
    오늘은 'ir-metric-delta down' + '▼ +5계단' 이 렌더된다.

    _rank_delta_type 은 _render_step2 안의 중첩 함수라 단위 테스트가 불가능해
    렌더 결과(markdown)에서 잠근다.
    """
    at = _boot(app_script)
    _load_existing(at)

    year = _sget(at, "selected_year")
    ranks = dict(_sget(at, "rank_changes"))
    row = dict(ranks[year])
    row["권역순위_변화"] = 5
    ranks[year] = row
    at.session_state["rank_changes"] = ranks
    _seed_step(at, 2)

    # '+5계단' 을 담은 카드 블록만 골라낸다. 페이지 전체를 훑으면
    # 1인당논문수 카드의 'up' 클래스에 걸려 단언이 헐거워진다.
    cards = [m.value for m in at.markdown if "+5계단" in m.value]
    assert len(cards) == 1, f"setup: 순위 변화 카드가 정확히 하나여야 한다 ({len(cards)}개)"
    card = cards[0]

    assert "ir-metric-delta up" in card, f"순위 상승은 'up' 클래스여야 한다:\n{card}"
    assert "▲ +5계단" in card, f"순위 상승은 ▲ 로 표시되어야 한다:\n{card}"


# ===========================================================================
# R7-07  V02 — 업로드 경로가 레거시 포맷을 변환하지 않는다
# ===========================================================================

def _research_ast() -> ast.Module:
    source = (PROJECT_ROOT / "report_app" / "pages" / "research.py").read_text(encoding="utf-8")
    return ast.parse(source)


def _function_def(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수를 찾지 못했다")


def _cloud_branch(func: ast.FunctionDef) -> list[ast.stmt]:
    """``if IS_CLOUD: ... else: ...`` 의 클라우드 쪽 본문을 돌려준다.

    ``if not IS_CLOUD:`` (UnaryOp) 는 제외해야 로컬 분기를 잘못 집지 않는다.
    """
    for node in ast.walk(func):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "IS_CLOUD"
            and node.orelse
        ):
            return node.body
    raise AssertionError(f"{func.name} 에서 'if IS_CLOUD: ... else: ...' 분기를 찾지 못했다")


def _called_names(nodes) -> set[str]:
    """주어진 AST 노드들에서 호출되는 이름을 모은다."""
    names = set()
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name:
                    names.add(name)
    return names


#: 레거시 포맷을 신포맷으로 정규화하는 것으로 인정하는 호출.
_CONVERSION_NAMES = {"_ensure_new_format", "load_all_data"}


def _calls_conversion(nodes) -> bool:
    """레거시 포맷 정규화를 거치는지 검사한다.

    직접 호출뿐 아니라 **공용 로더를 한 단계 경유하는 경우**도 인정한다.
    Phase 4 에서 4개 소스가 모두 ``load_dataframes()`` 를 거치도록 통합됐고,
    그 함수 본문이 ``_ensure_new_format`` 을 호출한다. 직접 호출만 인정하면
    올바른 리팩터링을 결함으로 오판하게 된다.

    간접 인정은 **한 단계까지만** 한다. 그 이상 따라가면 "어딘가에서
    언젠가 변환하겠지" 수준이 되어 잠금 구실을 못 한다.
    """
    direct = _called_names(nodes)
    if direct & _CONVERSION_NAMES:
        return True

    tree = _research_ast()
    for name in direct:
        try:
            helper = _function_def(tree, name)
        except AssertionError:
            continue  # research.py 안의 함수가 아니면 따라가지 않는다
        if _called_names([helper]) & _CONVERSION_NAMES:
            return True
    return False


@pytest.mark.parametrize("branch_id", ["render_source_csv", "render_source_raw_cloud"])
def test_r7_07_upload_paths_normalize_legacy_format(branch_id):
    """R7-07(V02): 업로드/클라우드 전처리 경로도 새 포맷으로 정규화해야 한다.

    ``st.file_uploader`` 는 AppTest 로 구동할 수 없으므로 정적 AST 로 잠근다.
    두 경로를 따로 파라미터화해, 한쪽만 고쳐도 나머지가 계속 결함으로 남는다.
    """
    tree = _research_ast()

    if branch_id == "render_source_csv":
        nodes = [_function_def(tree, "_render_source_csv")]
    else:
        nodes = _cloud_branch(_function_def(tree, "_render_source_raw"))

    assert _calls_conversion(nodes), (
        f"{branch_id}: _ensure_new_format 또는 load_all_data 를 거쳐야 한다"
    )


# ===========================================================================
# R7-08  해피 패스 end-to-end
# ===========================================================================

def test_r7_08_happy_path_produces_docx_with_narratives(app_script, tmp_path, monkeypatch):
    """R7-08: 로드 → 필터 → 통계 → 차트(실렌더) → GPT(스텁) → Word 까지 완주한다.

    차트는 실제 matplotlib 으로 1회 렌더한다(conftest 가 폰트 캐시를 미리
    데워 둬서 1.5초 남짓이라 slow 마커는 붙이지 않는다).
    이미지 개수는 단언하지 않는다 — fake_charts() 의 5개 버퍼는 바이트가
    같아 python-docx 가 관계를 1개로 합치기 때문이다. 목적은 서술 보존이다.
    """
    monkeypatch.chdir(tmp_path)

    counter = {"n": 0}

    def _fake_call_gpt(client, user_content):
        counter["n"] += 1
        return f"스텁 서술 본문 {counter['n']}"

    monkeypatch.setattr(gpt_reporter, "_call_gpt", _fake_call_gpt)

    at = _boot(app_script)
    _load_existing(at)
    _back_to_step1(at)
    _apply_filter(at)

    # 2단계
    _btn(at, "다음: 통계 확인 →").click().run()
    _no_exception(at)
    assert _sget(at, "step") == 2

    # 3단계 — 실제 matplotlib 렌더 1회
    _btn(at, "다음: 그래프 검토 →").click().run()
    _no_exception(at)
    charts = _sget(at, "charts")
    assert set(charts) == {"trend", "bar", "avg", "rank", "compare"}

    # 4단계 — GPT 일괄 생성 (스텁)
    at.session_state["api_key"] = _DUMMY_API_KEY
    _btn(at, "다음: GPT 서술 →").click().run()
    _no_exception(at)
    at.button(key="gen_all").click().run()
    _no_exception(at)

    narratives = {t.key: t.value for t in at.text_area}
    assert len(narratives) == 4
    assert all(narratives.values()), f"4개 섹션이 모두 채워져야 한다: {narratives}"
    assert len(set(narratives.values())) == 4, "섹션별 서술이 서로 달라야 검증이 의미 있다"

    # 5단계 — Word 생성
    _btn(at, "다음: 보고서 생성 →").click().run()
    _no_exception(at)
    _btn(at, "📄 Word 보고서 생성").click().run()
    _no_exception(at)

    buf = _sget(at, "report_buf")
    assert buf is not None, "report_buf 가 채워져야 한다"
    assert buf.getvalue()[:4] == b"PK\x03\x04", "docx 는 zip 시그니처로 시작한다"

    text_in_docx = _docx_text(buf)
    for key, value in narratives.items():
        assert value in text_in_docx, f"{key} 서술이 보고서에 없다"


# ===========================================================================
# R7-09  4단계 API Key 게이트
# ===========================================================================

def test_r7_09_step4_gates_on_api_key(app_script):
    """R7-09: API Key 유무에 따라 4단계 GPT UI 가 차단/허용된다."""
    at = _boot(app_script)
    _load_existing(at)
    at.session_state["api_key"] = ""
    _seed_step(at, 4)

    errors = [e.value for e in at.error]
    assert any("⛔" in e for e in errors), f"차단 안내가 있어야 한다: {errors}"
    assert not _has_key_btn(at, "gen_all"), "키 없이 일괄 생성 버튼이 뜨면 안 된다"
    assert len(at.text_area) == 0, "키 없이 서술 편집창이 뜨면 안 된다"

    # 키를 넣으면 정상 렌더
    at.session_state["api_key"] = _DUMMY_API_KEY
    at.run()
    _no_exception(at)
    assert not [e.value for e in at.error if "⛔" in e.value]
    assert _has_key_btn(at, "gen_all"), "일괄 생성 버튼이 나타나야 한다"
    assert sorted(t.key for t in at.text_area) == sorted(_NARRATIVE_KEYS)


# ===========================================================================
# R-RS-03  2단계 증감 안내의 연도 순서가 뒤집혀 있다
# ===========================================================================

def test_r_rs_03_step2_yoy_info_reads_previous_to_current(app_script):
    """R-RS-03: 2단계 전년대비 안내는 '이전 연도 → 기준 연도' 순이어야 한다.

    ``get_yoy_changes`` 의 dict 키 이름이 값과 어긋나 있다
    (``기준연도`` = 현재값, ``비교연도`` = 이전값). 화면은 그 이름을 그대로
    믿고 출력해 "0.1182 → 0.1245" 처럼 시간이 거꾸로 흐른다.
    """
    at = _boot(app_script)
    _load_existing(at)
    _seed_step(at, 2)

    yoy = _sget(at, "yoy_changes", {})
    hoseo = yoy.get("호서")
    assert hoseo, "setup: 대상 대학 증감 데이터가 있어야 한다"

    current = hoseo["기준연도"]  # 실제로는 기준(현재) 연도 값
    previous = hoseo["비교연도"]  # 실제로는 비교(이전) 연도 값
    assert current != previous, "setup: 두 해 수치가 같으면 순서를 검증할 수 없다"

    infos = [i.value for i in at.info]
    target = [t for t in infos if _DEFAULT_UNIV in t and "증감률" in t]
    assert target, f"setup: 증감 안내 문구를 찾지 못했다: {infos}"

    assert f"{previous:.4f} → {current:.4f}" in target[0], (
        f"'이전 → 현재' 순서여야 한다. 현재 출력: {target[0]!r}"
    )


# ===========================================================================
# R7-10  3단계 차트 캐시
# ===========================================================================

_CHART_FACTORIES = (
    "create_trend_chart",
    "create_comparison_bar",
    "create_avg_comparison",
    "create_rank_trend_chart",
    "create_compare_group_bar",
)


def _patch_chart_counters(monkeypatch) -> dict[str, int]:
    """chart_generator 의 5개 팩토리를 계수용 스텁으로 바꾼다."""
    calls: dict[str, int] = {name: 0 for name in _CHART_FACTORIES}

    def _make(name):
        def _stub(*args, **kwargs):
            calls[name] += 1
            return small_png_buf()

        return _stub

    for name in _CHART_FACTORIES:
        monkeypatch.setattr(cg, name, _make(name))
    return calls


def test_r7_10_step3_uses_chart_cache(app_script, monkeypatch):
    """R7-10: charts 가 이미 있으면 차트를 다시 만들지 않는다."""
    calls = _patch_chart_counters(monkeypatch)

    at = _boot(app_script)
    _load_existing(at)
    _seed_step(at, 3, with_charts=True)

    assert sum(calls.values()) == 0, f"캐시가 있으면 재생성하지 않아야 한다: {calls}"


def test_r7_10b_step3_generates_five_charts_when_cache_empty(app_script, monkeypatch):
    """R7-10: charts 가 비어 있으면 5종을 한 번씩 생성하고 확대 모달이 열린다."""
    calls = _patch_chart_counters(monkeypatch)

    at = _boot(app_script)
    _load_existing(at)
    at.session_state["charts"] = {}
    _seed_step(at, 3, with_charts=False)

    assert calls == {name: 1 for name in _CHART_FACTORIES}, f"5종 1회씩: {calls}"
    assert set(_sget(at, "charts")) == {"trend", "bar", "avg", "rank", "compare"}

    # 확대 버튼 → 모달(st.dialog) 이 예외 없이 열리고 해당 차트 정보가 실린다.
    before = len(at.dataframe)
    at.button(key="zoom_trend").click().run()
    _no_exception(at)
    assert _sget(at, "_chart_dialog_title") == "연도별 1인당논문수 추이"
    assert len(at.dataframe) == before + 1, "모달에 데이터 테이블이 하나 더 그려져야 한다"


# ===========================================================================
# R7-11  V17 — 두 번째 데이터 로드가 이전 분석 상태를 덮지 않는다
# ===========================================================================

def test_r7_11_reloading_data_resets_previous_filter_state(app_script, tmp_path, monkeypatch):
    """R7-11(V17): 데이터 B 를 새로 로드하면 A 의 필터/차트/대상대학이 초기화되어야 한다."""
    nat_raw, reg_raw = _raw_frames()

    # --- 데이터 B: 최초 연도를 뺀 복사본 (원본 CSV 는 건드리지 않는다) ---
    drop_year = int(min(nat_raw["연도"]))
    b_years = {int(y) for y in nat_raw["연도"].unique() if int(y) != drop_year}
    nat_b_path = tmp_path / "전체_대학_데이터.csv"
    reg_b_path = tmp_path / "권역별_순위.csv"
    nat_raw[nat_raw["연도"] != drop_year].to_csv(nat_b_path, index=False, encoding="utf-8-sig")
    reg_raw[reg_raw["연도"] != drop_year].to_csv(reg_b_path, index=False, encoding="utf-8-sig")

    # --- 데이터 A 로드 + 기본값이 아닌 대상 대학으로 필터 적용 ---
    at = _boot(app_script)
    _load_existing(at)
    _back_to_step1(at)
    at.selectbox(key="_filter_target_univ").select("순천향대학교").run()
    _apply_filter(at)
    assert _sget(at, "_target_university") == "순천향대학교", "setup: 대상 대학 변경 실패"

    at.session_state["charts"] = fake_charts()
    at.run()
    _no_exception(at)

    # --- 데이터 B 로드 ---
    # 경로 상수는 값으로 바인딩되므로 참조하는 모듈을 전부 패치해야 한다.
    # `_render_source_existing` 이 `dl.load_all_data()` 를 거치도록 통합된 뒤로는
    # data_loader 쪽 상수가 실제로 파일을 여는 주체다.
    monkeypatch.setattr(research, "NATIONAL_CSV", nat_b_path)
    monkeypatch.setattr(research, "REGIONAL_CSV", reg_b_path)
    monkeypatch.setattr(dl, "NATIONAL_CSV", nat_b_path)
    monkeypatch.setattr(dl, "REGIONAL_CSV", reg_b_path)
    at.button(key="src_existing").click().run()
    _btn(at, "✅ 기존 파일로 분석 시작").click().run()
    _no_exception(at)

    assert set(_sget(at, "national_df")["연도"].unique().astype(int)) == b_years, (
        "setup: 데이터 B 가 로드되지 않았다"
    )

    # --- 수정 후 기대 ---
    assert _sget(at, "charts") == {}, "재로드 시 차트 캐시가 비워져야 한다"
    assert _sget(at, "_target_university") in (None, _DEFAULT_UNIV), (
        "재로드 시 분석 대상 대학이 기본값으로 돌아가야 한다"
    )

    # 1단계로 돌아가면 원본 보관 프레임도 B 여야 한다
    # (키를 지우고 재복사하든, 즉시 덮어쓰든 동일하게 성립한다).
    _back_to_step1(at)
    raw_nat = _sget(at, "_raw_national_df")
    assert isinstance(raw_nat, pd.DataFrame), "원본 보관 프레임이 있어야 한다"
    assert set(raw_nat["연도"].unique().astype(int)) == b_years, (
        "원본 보관 프레임이 이전 데이터 A 그대로다"
    )


# ===========================================================================
# R7-12  리셋 잔여 상태 매트릭스 (V04/V05/V06/V17 통합)
# ===========================================================================

def _reset_via_sidebar(at: AppTest) -> None:
    _btn_by_key(at, "sidebar_reset_btn").click().run()


def _reset_via_step5(at: AppTest) -> None:
    at.session_state["step"] = 5
    at.run()
    _btn(at, "🔄 처음부터").click().run()


_RESET_PATHS = {
    "sidebar": _reset_via_sidebar,
    "step5": _reset_via_step5,
}


@pytest.mark.parametrize("reset_id", sorted(_RESET_PATHS))
def test_r7_12_reset_leaves_no_analysis_residue(app_script, reset_id):
    """R7-12: 어느 리셋 경로를 타든 분석 상태가 한 개도 남으면 안 된다.

    ``_MUST_CLEAR_KEYS`` 전체를 한 테스트에서 훑고 잔여물을 모아 보고한다.
    키마다 파라미터화하면 이미 올바르게 지워지는 키가 XPASS 를 만들어
    (xfail_strict=true) 러너 전체가 실패하므로 경로 단위로만 나눈다.
    """
    at = _boot(app_script)
    _load_existing(at)
    _back_to_step1(at)
    _apply_filter(at)
    at.session_state["charts"] = fake_charts()
    at.session_state["_chart_dialog_title"] = "잔여 확인용"
    at.session_state["_chart_dialog_buf"] = small_png_buf()
    at.session_state["_chart_dialog_df"] = pd.DataFrame({"a": [1]})
    for key in _NARRATIVE_KEYS:
        at.session_state[f"_saved_{key}"] = "잔여 확인용 서술"
    at.session_state["max_step"] = 5
    at.run()
    _no_exception(at)

    # setup 가드 — 지울 것이 실제로 있어야 한다.
    seeded = [k for k in _MUST_CLEAR_KEYS if not _is_empty(_sget(at, k, _MISSING))]
    assert len(seeded) >= 15, f"setup: 분석 상태가 충분히 쌓이지 않았다 ({len(seeded)}개)"

    _RESET_PATHS[reset_id](at)
    _no_exception(at)

    # 잔여물을 한 번에 모아 보고한다 — 개별 단언으로 끊으면
    # 첫 실패 뒤의 키들이 영영 관측되지 않는다.
    residue = [
        f"{key}={_short(_sget(at, key, _MISSING))}"
        for key in _MUST_CLEAR_KEYS
        if not _is_cleared(key, _sget(at, key, _MISSING))
    ]
    max_step = _sget(at, "max_step")
    if max_step != 1:
        residue.append(f"max_step={max_step}")

    assert residue == [], (
        f"[{reset_id}] 리셋 후 남은 분석 상태 {len(residue)}개: {residue}"
    )


#: 리셋이 '키 삭제' 대신 '기본값 복원' 으로 구현돼도 동등하게 인정할 키.
#: research.py 의 ``_target_univ()`` / ``_target_region()`` 이 이 값들로 폴백한다.
_RESET_DEFAULT_OK = {
    "_target_university": _DEFAULT_UNIV,
    "_target_region": _DEFAULT_REGION,
}


def _is_cleared(key: str, value) -> bool:
    """리셋 후 '지워진 것으로 인정' 할 값인지 판정한다.

    부재/None/''/{}/[]/False 이거나, 폴백 기본값과 같으면 지워진 것으로 본다.
    기본값 복원도 인정해야 수정 방식(키 삭제 vs 기본값 대입)에 중립적이다.
    """
    if _is_empty(value):
        return True
    return key in _RESET_DEFAULT_OK and value == _RESET_DEFAULT_OK[key]


def _is_empty(value) -> bool:
    """'비어 있음' 으로 인정할 값인지 판정한다 (부재/None/''/{}/[]/False)."""
    if value is _MISSING or value is None or value is False:
        return True
    if isinstance(value, pd.DataFrame):
        return value.empty
    if isinstance(value, (str, dict, list, tuple, set)):
        return len(value) == 0
    return False


def _short(value) -> str:
    if value is _MISSING:
        return "<absent>"
    if isinstance(value, pd.DataFrame):
        return f"DataFrame{value.shape}"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."
