"""APP-00..APP-05: report_app/app.py 앱 셸(부팅·라우팅·API 키·설정·클라우드).

관측 경계는 AppTest 하나뿐이다. app.py 는 모듈이 아니라 스크립트라
(import 시 st.set_page_config 가 실행된다) 단위 테스트가 불가능하고,
_get_api_key / _save_api_key / _api_key_dialog 는 스크립트 지역 함수라
직접 호출할 수 없다. 따라서 전부 AppTest 로 관측한다.

주의사항(하네스 계약):
  - AppTest.from_file 은 절대경로여야 한다 (conftest 의 app_script 픽스처).
  - at.session_state 에는 .get() 이 없다 → 아래 sget() 헬퍼를 쓴다.
  - at.secrets 가 비어 있으면 streamlit 이 실제 secrets.toml 을 읽는다.
    _boot() 이 항상 "_dummy" 를 심어 빈 dict Secrets 를 강제한다.
  - 이 파일에는 AppTest.from_function 래퍼가 없다(전부 from_file).
    ASCII 전용 제약(TST-02)은 래퍼 본문에만 적용되므로 무관하다.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import report_app.config as config_mod
import report_app.pages.research as research_mod

# ---------------------------------------------------------------------------
# 테스트용 가짜 키 (실제 키 아님 — 절대 실키를 넣지 말 것)
# ---------------------------------------------------------------------------
FAKE_KEY_A = "sk-test-0000aaaaaaaaaaaaaaaaaaaaaaaa"   # 34자 (>20, >15)
FAKE_KEY_B = "sk-test-0000bbbbbbbbbbbbbbbbbbbbbbbb"
PLACEHOLDER_KEY = "sk-여기에_실제_키를_입력하세요"       # app.py:84 의 거부 대상


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def sget(at: AppTest, key: str, default=None):
    """AppTest.session_state 에는 .get() 이 없다(SafeSessionState)."""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def _boot(app_script: Path, secrets: dict | None = None,
          session_state: dict | None = None) -> AppTest:
    """AppTest 인스턴스를 만든다(아직 run 하지 않는다).

    secrets 를 항상 비우는 것이 핵심이다. AppTest 는 secrets dict 가
    비어 있으면 오버라이드하지 않고 실제 secrets.toml 로 폴백하므로,
    개발 머신에 실키가 있으면 테스트가 조용히 오염된다.
    """
    at = AppTest.from_file(str(app_script), default_timeout=60)
    at.secrets["_dummy"] = "x"          # 빈 dict Secrets 강제
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    for k, v in (session_state or {}).items():
        at.session_state[k] = v
    return at


def _assert_api_key_empty(at: AppTest) -> None:
    """api_key 가 빈 문자열임을 단언한다(실패 메시지에 값을 노출하지 않는다)."""
    key = sget(at, "api_key")
    is_empty = key == ""
    assert is_empty, f"api_key 가 비어 있지 않다 (type={type(key).__name__}, len={len(key or '')})"


def _set_cloud(monkeypatch, value: bool) -> None:
    """IS_CLOUD 분기를 켜고 끈다.

    app.py 는 매 run 마다 `from report_app.config import IS_CLOUD` 를 다시
    실행하므로 config 패치만으로 충분하지만, research.py 는 import 시점에
    값으로 바인딩되어(research.py:42) sys.modules 캐시에 남아 있으므로
    두 곳을 모두 패치해야 한다. 서브프로세스는 쓰지 않는다.
    """
    monkeypatch.setattr(config_mod, "IS_CLOUD", value)
    monkeypatch.setattr(research_mod, "IS_CLOUD", value)


def _button_keys(at: AppTest) -> set[str]:
    return {b.key for b in at.button if b.key}


def _buttons_by_label(at: AppTest, needle: str) -> list:
    return [b for b in at.button if needle in (b.label or "")]


def _safe(obj) -> str:
    """실패 메시지용 ASCII 안전 문자열.

    UI 문자열에는 이모지가 섞여 있는데, Windows 콘솔(cp949)로 그대로
    내보내면 pytest 리포팅 자체가 UnicodeEncodeError 로 죽어
    정작 무엇이 실패했는지 볼 수 없게 된다.
    """
    return repr(obj).encode("ascii", "backslashreplace").decode("ascii")


def _exc_summary(at: AppTest) -> str:
    return _safe([f"{type(e.value).__name__}: {e.value}" for e in at.exception])


# ===========================================================================
# APP-00: 부팅 스모크
# ===========================================================================
class TestAppBoot:
    """APP-00: 빈 상태에서 앱이 예외 없이 뜨고 기본값이 맞는가."""

    def test_boots_without_exception_and_lands_on_home(self, app_script):
        at = _boot(app_script)
        t0 = time.perf_counter()
        at.run()
        elapsed = time.perf_counter() - t0

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "module") == "home"
        assert sget(at, "step") == 1
        assert sget(at, "max_step") == 1
        _assert_api_key_empty(at)

        # 측정값은 정보용 — 단언은 타임아웃 미만인지만 본다.
        print(f"\n[APP-00] 첫 run() 벽시계 시간: {elapsed:.3f}s")
        assert elapsed < 60, f"부팅이 타임아웃(60s)에 근접한다: {elapsed:.2f}s"

    def test_home_renders_only_research_card_enabled(self, app_script):
        """홈 카드 3장 중 연구실적만 활성(나머지는 '준비 중')."""
        at = _boot(app_script)
        at.run()

        assert at.button(key="home_research").disabled is False
        assert at.button(key="home_edu").disabled is True
        assert at.button(key="home_emp").disabled is True


# ===========================================================================
# APP-01: 라우팅
# ===========================================================================
class TestRouting:
    """APP-01: 모듈 전환, 단계 게이팅, max_step 단조 증가."""

    def test_home_card_click_routes_to_research_step1(self, app_script):
        at = _boot(app_script)
        at.run()
        assert sget(at, "module") == "home"

        at.button(key="home_research").click().run()

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "module") == "research"
        assert sget(at, "step") == 1

    def test_sidebar_module_button_routes_to_research(self, app_script):
        """사이드바 모듈 버튼 경로(app.py:193-199).

        홈 카드 경로(app.py:236-241)와 별개의 분기다. 활성 모듈 버튼은
        트리에 아예 없으므로(sidebar.py:248) home 에 있을 때만 research
        버튼을 누를 수 있다.
        """
        at = _boot(app_script)
        at.run()
        assert "sidebar_mod_research" in _button_keys(at)

        at.button(key="sidebar_mod_research").click().run()

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "module") == "research"
        assert sget(at, "step") == 1

    def test_sidebar_module_button_absent_for_active_module(self, app_script):
        """활성 모듈은 버튼이 아니라 HTML div 로 렌더된다(sidebar.py:248)."""
        at = _boot(app_script)
        at.run()

        keys = _button_keys(at)
        assert "sidebar_mod_home" not in keys       # home 이 활성
        assert "sidebar_mod_research" in keys
        assert at.button(key="sidebar_mod_education_cost").disabled is True
        assert at.button(key="sidebar_mod_employment").disabled is True

    def test_step_buttons_enabled_only_up_to_max_step(self, app_script):
        """max_step=3 이면 2·3단계만 클릭 가능, 4·5단계는 disabled.

        sidebar_step_* 키는 0-based 인덱스다(sidebar.py:380/389).
        현재 단계(step 1 → index 0)는 버튼이 아예 렌더되지 않는다.
        """
        at = _boot(app_script, session_state={
            "module": "research", "step": 1, "max_step": 3,
        })
        at.run()

        assert at.exception == [], _exc_summary(at)
        keys = _button_keys(at)
        assert "sidebar_step_0" not in keys, "현재 단계 버튼은 트리에 없어야 한다"
        assert at.button(key="sidebar_step_1").disabled is False   # 2단계
        assert at.button(key="sidebar_step_2").disabled is False   # 3단계
        assert at.button(key="sidebar_step_3").disabled is True    # 4단계
        assert at.button(key="sidebar_step_4").disabled is True    # 5단계

    def test_seeded_step_advances_max_step(self, app_script):
        """step 을 5로 심어두면 max_step 이 5로 올라간다(app.py:246-247).

        빈 데이터로 끝까지 렌더되는 단계가 5단계뿐이라 5를 쓴다. 측정 결과:
          - 2단계: TypeError (`year in hoseo`, 둘 다 None) → research.py:820
          - 3단계: AttributeError ('NoneType' has no attribute 'keys')
          - 4단계: 예외는 없지만 st.stop() 으로 중단 (research.py:1155)
        """
        at = _boot(app_script, session_state={"module": "research", "step": 5})
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "max_step") == 5


    def test_max_step_survives_step_short_circuit(self, app_script):
        """[V19] 단계가 st.stop() 으로 끊겨도 max_step 이 step 이상으로 유지되어야 한다.

        수정 후 기대 동작을 단언한다 → 오늘은 반드시 실패한다(XFAIL).
        API Key 없이 4단계에 들어가면 _render_step4 가 st.stop() 으로
        스크립트를 끊는데, max_step 갱신이 render_research() **다음 줄**에
        있어 영영 실행되지 않는다. 그 결과 step=4 인데 max_step=1 이 되어
        사이드바에서 4단계로 되돌아올 수 없다.

        raises=AssertionError 를 고정한 이유: 컴포넌트가 TypeError 등으로
        크래시하면 XFAIL 로 흡수되지 않고 FAILED 로 드러나게 하기 위해서다.
        """
        at = _boot(app_script, session_state={"module": "research", "step": 4})
        at.run()

        # 전제 — 여기서 깨지면 AssertionError 가 아니라 설정 문제이므로 먼저 확인한다.
        assert at.exception == [], _exc_summary(at)
        assert sget(at, "step") == 4
        assert any("API Key" in (e.value or "") for e in at.error)

        # 본 단언(수정 후 기대): 끊겨도 max_step 은 step 아래로 내려가지 않는다.
        step, max_step = sget(at, "step"), sget(at, "max_step")
        assert max_step >= step, (
            f"max_step={max_step} < step={step} — 사이드바에서 {step}단계로 되돌아올 수 없다"
        )

    def test_max_step_never_decreases_when_going_back(self, app_script):
        """max_step 은 되돌아가도 줄지 않는다(app.py:246 은 > 일 때만 갱신)."""
        at = _boot(app_script, session_state={
            "module": "research", "step": 5, "max_step": 5,
        })
        at.run()
        assert sget(at, "max_step") == 5

        at.button(key="sidebar_step_0").click().run()   # 1단계로 복귀

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "step") == 1
        assert sget(at, "max_step") == 5, "되돌아갔는데 max_step 이 줄었다"


# ===========================================================================
# APP-02: _get_api_key 우선순위 (app.py:80-91, 122-123)
# ===========================================================================
class TestApiKeyResolution:
    """APP-02: secrets > .env/환경변수 > 빈 문자열."""

    @pytest.mark.parametrize(
        "secrets, env_value, expected",
        [
            pytest.param({"OPENAI_API_KEY": FAKE_KEY_A}, None, FAKE_KEY_A,
                         id="flat-secrets-key-used"),
            pytest.param(None, FAKE_KEY_B, FAKE_KEY_B,
                         id="env-var-used-when-no-secrets"),
            pytest.param({"OPENAI_API_KEY": FAKE_KEY_A}, FAKE_KEY_B, FAKE_KEY_A,
                         id="secrets-beats-env"),
            pytest.param({"OPENAI_API_KEY": PLACEHOLDER_KEY}, None, "",
                         id="placeholder-rejected"),
            pytest.param({"OPENAI_API_KEY": "not-a-key"}, FAKE_KEY_B, FAKE_KEY_B,
                         id="invalid-secrets-falls-back-to-env"),
            pytest.param(None, None, "", id="nothing-set-yields-empty"),
        ],
    )
    def test_api_key_priority(self, app_script, monkeypatch, secrets, env_value, expected):
        if env_value is not None:
            monkeypatch.setenv("OPENAI_API_KEY", env_value)

        at = _boot(app_script, secrets=secrets)
        at.run()

        assert at.exception == [], _exc_summary(at)
        if expected == "":
            _assert_api_key_empty(at)
        else:
            assert sget(at, "api_key") == expected

    @pytest.mark.characterization
    def test_nested_secrets_form_is_ignored(self, app_script):
        """[V16] 문서가 안내하는 중첩 secrets 형식을 코드가 읽지 못한다.

        README/배포 안내는 `[openai] api_key = "sk-..."` 중첩 형식을 쓰라고
        하지만 app.py:83 은 평면 키 st.secrets["OPENAI_API_KEY"] 만 본다.
        따라서 중첩 형식으로 넣으면 KeyError 로 폴백해 api_key 가 ''이 된다.
        # 수정 후 삭제 (V16 수정 시 이 테스트는 XPASS 가 되므로 함께 갱신할 것)
        """
        at = _boot(app_script, secrets={"openai": {"api_key": FAKE_KEY_A}})
        at.run()

        assert at.exception == [], _exc_summary(at)
        _assert_api_key_empty(at)


# ===========================================================================
# APP-03: API Key 변경 다이얼로그 (app.py:140-163, 129-134)
# ===========================================================================
class TestApiKeyDialog:
    """APP-03: 다이얼로그 저장이 session_state 와 .env 에 반영되는가.

    sidebar_api_change 플래그는 app.py:181 에서 pop 되므로
    **매 run 직전마다** 다시 심어야 다이얼로그가 계속 렌더된다.
    """

    def test_dialog_renders_when_flag_set(self, app_script):
        at = _boot(app_script)
        at.session_state["sidebar_api_change"] = True
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert at.text_input(key="_dialog_api_key") is not None
        assert len(_buttons_by_label(at, "저장")) == 1

    def test_sidebar_change_button_sets_flag(self, app_script):
        """사이드바 [변경] 클릭이 다이얼로그를 띄운다(sidebar.py:434)."""
        at = _boot(app_script)
        at.run()
        at.button(key="sidebar_api_change_btn").click().run()

        assert at.exception == [], _exc_summary(at)
        assert at.text_input(key="_dialog_api_key") is not None

    def test_save_updates_session_state_and_writes_dotenv(
        self, app_script, monkeypatch, tmp_path
    ):
        """로컬 모드: 저장하면 session_state 와 cwd/.env 양쪽에 반영된다."""
        monkeypatch.chdir(tmp_path)          # 실제 프로젝트/샌드박스에 쓰지 않는다
        _set_cloud(monkeypatch, False)

        at = _boot(app_script)
        at.session_state["sidebar_api_change"] = True
        at.run()

        at.text_input(key="_dialog_api_key").set_value(FAKE_KEY_A)
        _buttons_by_label(at, "저장")[0].click()
        at.session_state["sidebar_api_change"] = True   # pop 되었으므로 재설정
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "api_key") == FAKE_KEY_A

        env_path = tmp_path / ".env"
        assert env_path.exists(), ".env 가 생성되지 않았다"
        lines = env_path.read_text(encoding="utf-8").splitlines()
        assert any(line.startswith("OPENAI_API_KEY=") for line in lines), (
            "OPENAI_API_KEY= 로 시작하는 줄이 없다 "
            f"(줄 수={len(lines)})"   # 값 자체는 출력하지 않는다
        )

    def test_save_skips_dotenv_in_cloud(self, app_script, monkeypatch, tmp_path):
        """클라우드 모드: session_state 만 갱신하고 .env 는 쓰지 않는다(app.py:131)."""
        monkeypatch.chdir(tmp_path)
        _set_cloud(monkeypatch, True)

        at = _boot(app_script)
        at.session_state["sidebar_api_change"] = True
        at.run()

        at.text_input(key="_dialog_api_key").set_value(FAKE_KEY_A)
        _buttons_by_label(at, "저장")[0].click()
        at.session_state["sidebar_api_change"] = True
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "api_key") == FAKE_KEY_A
        assert not (tmp_path / ".env").exists(), "클라우드인데 .env 를 썼다"

    def test_short_key_is_rejected_without_saving(self, app_script, monkeypatch, tmp_path):
        """20자 이하 키는 저장되지 않고 에러만 표시된다(app.py:156)."""
        monkeypatch.chdir(tmp_path)
        _set_cloud(monkeypatch, False)

        at = _boot(app_script)
        at.session_state["sidebar_api_change"] = True
        at.run()

        at.text_input(key="_dialog_api_key").set_value("sk-tooshort")   # 11자
        _buttons_by_label(at, "저장")[0].click()
        at.session_state["sidebar_api_change"] = True
        at.run()

        assert at.exception == [], _exc_summary(at)
        _assert_api_key_empty(at)
        assert not (tmp_path / ".env").exists()
        assert any("올바른 키" in (e.value or "") for e in at.error)


# ===========================================================================
# APP-04: 설정 페이지 (app.py:249-250, settings.py)
# ===========================================================================
class TestSettingsPage:
    """APP-04: settings 라우트.

    주의: 이 라우트는 사이드바/홈 어디에서도 도달할 수 없다.
    _MODULES(sidebar.py:30-35)와 home.py 의 카드 어디에도 "settings" 가 없고
    render_home() 도 "settings" 를 반환하지 않는다.
    즉 app.py:249-250 은 session_state 를 직접 조작해야만 닿는 죽은 코드다.
    여기서는 session_state 를 강제로 심어 렌더 자체를 검증한다.
    """

    def test_settings_renders_without_exception(self, app_script):
        at = _boot(app_script, session_state={"module": "settings"})
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert sget(at, "module") == "settings"
        # API 키 미설정 경고
        assert any("API Key" in (w.value or "") for w in at.warning)

    def test_settings_masks_api_key(self, app_script):
        """키는 앞 7자 + '...' + 뒤 4자로 마스킹된다(settings.py:90)."""
        at = _boot(app_script, session_state={
            "module": "settings", "api_key": FAKE_KEY_A,
        })
        at.run()

        assert at.exception == [], _exc_summary(at)
        expected_mask = FAKE_KEY_A[:7] + "..." + FAKE_KEY_A[-4:]
        successes = [s.value or "" for s in at.success]
        assert any(expected_mask in s for s in successes), (
            f"마스킹된 키가 표시되지 않았다: {_safe(successes)}"
        )
        # 전체 키가 그대로 노출되지는 않아야 한다.
        assert not any(FAKE_KEY_A in s for s in successes)


# ===========================================================================
# APP-05: IS_CLOUD 분기 (config.py:46 / research.py:243, 584, 603, 613, 1329)
# ===========================================================================
class TestCloudBranch:
    """APP-05: 클라우드 모드에서 파일시스템을 건드리지 않는가.

    각 단언마다 IS_CLOUD=False 대조군을 함께 돌린다.
    대조군이 없으면 셋업이 잘못돼 아무 일도 일어나지 않은 경우에도
    "클라우드라서 안 만들어졌다"로 조용히 통과한다.
    """

    @pytest.mark.parametrize("is_cloud, expect_disabled", [(False, False), (True, True)])
    def test_existing_source_card_disabled_only_in_cloud(
        self, app_script, monkeypatch, is_cloud, expect_disabled
    ):
        _set_cloud(monkeypatch, is_cloud)
        at = _boot(app_script, session_state={"module": "research", "step": 1})
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert at.button(key="src_existing").disabled is expect_disabled
        # raw/csv 카드는 두 모드 모두 활성이어야 한다(대조).
        assert at.button(key="src_raw").disabled is False
        assert at.button(key="src_csv").disabled is False

    @pytest.mark.parametrize("is_cloud, expect_dir", [(False, True), (True, False)])
    def test_raw_dir_created_only_in_local(
        self, app_script, monkeypatch, tmp_path, is_cloud, expect_dir
    ):
        """research.py:576 의 `Path.cwd() / "Raw data"` 를 mkdir 하는가."""
        monkeypatch.chdir(tmp_path)
        _set_cloud(monkeypatch, is_cloud)

        at = _boot(app_script, session_state={
            "module": "research", "step": 1, "data_source": "raw",
        })
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert (tmp_path / "Raw data").exists() is expect_dir

    def test_cloud_raw_source_shows_upload_warning(self, app_script, monkeypatch, tmp_path):
        """클라우드 분기를 실제로 탔다는 양성 신호(research.py:613-615)."""
        monkeypatch.chdir(tmp_path)
        _set_cloud(monkeypatch, True)

        at = _boot(app_script, session_state={
            "module": "research", "step": 1, "data_source": "raw",
        })
        at.run()

        assert at.exception == [], _exc_summary(at)
        assert any("Raw Excel" in (w.value or "") for w in at.warning)

    def test_cloud_has_no_raw_save_button(self, app_script, monkeypatch, tmp_path):
        """클라우드에는 [Raw data/ 에 저장] 버튼이 없다(research.py:603).

        주의: 이 버튼은 `uploaded_raws` 가 truthy 일 때만 렌더되는데
        AppTest 는 st.file_uploader 를 구동할 수 없다. 따라서 로컬에서도
        이 버튼은 없다 — 이 단언은 분기를 구별하지 못하며(non-discriminating)
        회귀 방지용 기록으로만 둔다. 실제 분기 신호는 위 warning 테스트다.
        """
        monkeypatch.chdir(tmp_path)
        _set_cloud(monkeypatch, True)

        at = _boot(app_script, session_state={
            "module": "research", "step": 1, "data_source": "raw",
        })
        at.run()

        # 렌더가 중간에 죽어도 키가 없어 "통과"하므로 예외부터 막는다.
        assert at.exception == [], _exc_summary(at)
        assert "src_raw" in _button_keys(at), "1단계가 끝까지 렌더되지 않았다"
        assert "save_raw" not in _button_keys(at)

    @pytest.mark.parametrize("is_cloud, expect_dir", [(False, True), (True, False)])
    def test_report_dir_created_only_in_local(
        self, app_script, monkeypatch, tmp_path, is_cloud, expect_dir
    ):
        """5단계 보고서 생성 시 REPORT_DIR mkdir 여부(research.py:1329-1330).

        REPORT_DIR 은 research 모듈에 값으로 바인딩돼 있어 chdir 로는
        옮겨지지 않는다 → 모듈 속성을 직접 tmp_path 로 패치한다.
        데이터가 없어 build_report 는 예외를 던지지만 research.py:1345 가
        잡아 st.error 로 처리하므로 at.exception 은 비어 있다.
        """
        report_dir = tmp_path / "output" / "reports"
        monkeypatch.setattr(research_mod, "REPORT_DIR", report_dir)
        _set_cloud(monkeypatch, is_cloud)

        at = _boot(app_script, session_state={"module": "research", "step": 5})
        at.run()
        assert at.exception == [], _exc_summary(at)

        gen_buttons = _buttons_by_label(at, "Word 보고서 생성")
        assert len(gen_buttons) == 1, f"생성 버튼을 찾지 못했다 (버튼 {len(at.button)}개, keys={_safe(sorted(_button_keys(at)))})"
        gen_buttons[0].click().run()

        assert at.exception == [], _exc_summary(at)
        assert report_dir.exists() is expect_dir
