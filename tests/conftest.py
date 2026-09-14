"""QA 테스트 하네스 공통 설정 (conftest).

중요: 이 파일의 모듈 레벨 코드는 pytest 수집(collection) 단계에서
테스트 모듈이 report_app 을 import 하기 전에 실행되어야 한다.
report_app.config 는 import 시점에 Path.cwd() 를 1회 평가하므로
(config.py:80 `_PROJECT_ROOT = Path.cwd()`), chdir 이 늦으면
NATIONAL_CSV 등 경로 상수가 실제 프로젝트 루트로 고정된다.
세션 픽스처(session fixture)는 수집보다 늦게 실행되므로 쓸 수 없다.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 리포트 출력 인코딩
# ---------------------------------------------------------------------------
# Windows 콘솔 기본 코드페이지는 cp949 라서, xfail reason 이나 실패 메시지에
# 한글이 들어가면 pytest 요약 줄이 깨져 읽을 수 없다. 단언 메시지에 이모지가
# 섞이면 리포팅 자체가 UnicodeEncodeError 로 죽어 실패 원인을 못 보기도 한다.
# 결함 번호를 훑는 요약 줄이 읽히지 않으면 스위트의 가치가 크게 떨어진다.
#
# sys.stdout 을 모듈 레벨에서 재설정해도 소용없다. pytest 의 캡처 매니저가
# 이미 원본 스트림을 따로 붙들고 있기 때문이다. 터미널 리포터가 실제로 쓰는
# 파일 객체를 pytest_configure 시점에 바꿔야 한다.
def _force_utf8(stream) -> None:
    if stream is not None and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass


def pytest_sessionstart(session):  # noqa: D103
    # terminalreporter 는 pytest_configure 시점에 아직 없을 수 있으므로
    # sessionstart 에서 건드린다. 원본 스트림도 함께 바꾼다.
    _force_utf8(sys.__stdout__)
    _force_utf8(sys.__stderr__)
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        _force_utf8(getattr(getattr(reporter, "_tw", None), "_file", None))


# ===========================================================================
# 모듈 레벨 부트스트랩 (순서가 곧 계약이다)
# ===========================================================================

# 0. 프로젝트 루트 = <root>/tests/conftest.py 의 부모의 부모
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 1. matplotlib: 첫 import 이전에 백엔드와 캐시 디렉터리를 고정한다.
#    chart_generator.py 는 import 만으로 pyplot/font_manager 를 로드하고
#    rcParams 를 전역 변경하므로, 여기서 먼저 잡아야 한다.
os.environ["MPLBACKEND"] = "Agg"
MPL_CONFIG_DIR = tempfile.mkdtemp(prefix="hoseo_mpl_")  # ASCII 접두어 (한글 경로 회피)
os.environ["MPLCONFIGDIR"] = MPL_CONFIG_DIR

# 2. 환경 격리: 실제 API 키/클라우드 플래그가 테스트로 새어들지 않게 한다.
for _key in ("OPENAI_API_KEY", "STREAMLIT_SHARING_MODE", "IS_CLOUD"):
    os.environ.pop(_key, None)

# 3. 세션 샌드박스 생성 + 실데이터 복사
SANDBOX = Path(tempfile.mkdtemp(prefix="hoseo_qa_"))
(SANDBOX / "output").mkdir(parents=True, exist_ok=True)

_REAL_OUTPUT = PROJECT_ROOT / "output"
_CSV_NAMES = ("전체_대학_데이터.csv", "권역별_순위.csv", "충청권_순위.csv")
REALDATA_AVAILABLE = (_REAL_OUTPUT / "전체_대학_데이터.csv").exists() and (
    _REAL_OUTPUT / "권역별_순위.csv"
).exists()
for _name in _CSV_NAMES:
    _src = _REAL_OUTPUT / _name
    if _src.exists():
        shutil.copy2(_src, SANDBOX / "output" / _name)

RAW_DIR = PROJECT_ROOT / "Raw data"
RAW_AVAILABLE = RAW_DIR.exists() and len(list(RAW_DIR.glob("*.xlsx"))) > 0

PREPROCESS_PATH = PROJECT_ROOT / "전임교원_연구실적_전처리.py"

# 4. import 경로에 프로젝트 루트 추가 후 cwd 를 샌드박스로 이동
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(SANDBOX)

# 5. 경로 상수 바인딩을 이 시점에 확정시킨다(순서 의존을 없애기 위해 명시 import).
#    chart_generator 를 미리 import 해 폰트 캐시 생성 비용을
#    AppTest run 타임아웃 바깥으로 빼는 효과도 있다.
import report_app.config as _cfg  # noqa: E402
import report_app.data_loader as _dl  # noqa: E402
import report_app.chart_generator as _cg  # noqa: E402

import matplotlib  # noqa: E402
import matplotlib.pyplot as _plt  # noqa: E402

_RCPARAMS_SNAPSHOT = dict(matplotlib.rcParams)


# ===========================================================================
# 마커 등록 (pytest.ini 와 중복 등록해도 무해)
# ===========================================================================
def pytest_configure(config: pytest.Config) -> None:
    for line in (
        "realdata: git 에 추적된 실제 Raw/output 데이터를 사용",
        "slow: 수 초 이상 걸리는 테스트",
        "live: 실제 외부 API 호출 (기본 제외)",
        "characterization: 현재(결함 포함) 동작을 기록만 하는 테스트. 수정 시 함께 갱신",
        "needs_refactor: 프로덕션 코드 추출 없이는 단위 테스트가 불가해 관측 경계에서 잠근 테스트",
    ):
        config.addinivalue_line("markers", line)


# ===========================================================================
# 경로/모듈 픽스처
# ===========================================================================
@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def sandbox() -> Path:
    return SANDBOX


@pytest.fixture(scope="session")
def pp_module():
    """한글 파일명인 전처리 스크립트를 importlib 으로 로드한다.

    일반 import 가 불가하므로 spec_from_file_location 을 쓴다.
    스크립트의 config 경로는 __file__ 기준(전처리.py:667, :781)이라
    cwd 와 무관하게 실제 config/ 를 읽는다.
    """
    if not PREPROCESS_PATH.exists():
        pytest.skip(f"전처리 스크립트 없음: {PREPROCESS_PATH}")
    spec = importlib.util.spec_from_file_location("preprocessor_under_test", str(PREPROCESS_PATH))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def app_script() -> Path:
    """AppTest.from_file 에 넘길 절대경로.

    상대경로를 쓰면 샌드박스 cwd 기준으로 해석돼 FileNotFoundError 가 난다
    (streamlit/testing/v1/app_test.py:304-314).
    """
    return PROJECT_ROOT / "report_app" / "app.py"


# ===========================================================================
# 격리 픽스처 (autouse)
# ===========================================================================
@pytest.fixture(autouse=True)
def _isolate_env_and_dotenv():
    """테스트마다 API 키 환경변수와 샌드박스 .env 를 지운다.

    app.py:58 의 load_dotenv 는 매 run 마다 재실행되어 .env 값을
    os.environ 으로 주입하므로, delenv 만으로는 누수를 막지 못한다.
    """
    for key in ("OPENAI_API_KEY", "STREAMLIT_SHARING_MODE", "IS_CLOUD"):
        os.environ.pop(key, None)
    dotenv_path = SANDBOX / ".env"
    if dotenv_path.exists():
        dotenv_path.unlink()
    yield
    for key in ("OPENAI_API_KEY", "STREAMLIT_SHARING_MODE", "IS_CLOUD"):
        os.environ.pop(key, None)
    if dotenv_path.exists():
        dotenv_path.unlink()


@pytest.fixture(autouse=True)
def _reset_streamlit_pages_manager():
    """AppTest 파일 간 오염을 막는다.

    `PagesManager.uses_pages_directory` 는 **클래스 전역**이고, 최초
    PagesManager 생성 시 `<main_script_parent>/pages` 존재 여부로 한 번만
    결정된 뒤 리셋되지 않는다(pages_manager.py:35, :58-61).

    `report_app/app.py` 옆에는 `report_app/pages/` 가 있으므로
    `AppTest.from_file(app.py)` 를 한 번이라도 돌리면 이 플래그가 True 로 굳는다.
    그 뒤의 모든 `AppTest.from_function` 은 script_runner.py:668 에서
    `_mpa_v1()` 경로로 빠지는데, from_function 이 만드는 임시 파일 이름은
    확장자 없는 md5 해시라 `page_icon_and_name()` 이 ''를 돌려주고
    "The title of the page cannot be empty" 예외로 전부 실패한다.

    단독 실행에서는 통과하고 전체 실행에서만 깨지므로, 반드시 격리해야 한다.
    """
    from streamlit.runtime.pages_manager import PagesManager

    saved = PagesManager.uses_pages_directory
    PagesManager.uses_pages_directory = None
    try:
        yield
    finally:
        PagesManager.uses_pages_directory = saved if saved is None else None


@pytest.fixture(autouse=True)
def _matplotlib_cleanup():
    """Figure 누수가 다음 테스트로 번지지 않게 한다.

    누수 여부 자체의 단언은 teardown 이 아니라 테스트 본문에서 한다
    (teardown 실패는 xfail 이 흡수하지 못해 ERROR 가 되기 때문).
    """
    yield
    _plt.close("all")
    matplotlib.rcParams.update(_RCPARAMS_SNAPSHOT)


@pytest.fixture
def bare_session_state():
    """ScriptRunContext 없는 비렌더 모드(bare mode) session_state.

    streamlit 은 전역 _mock_session_state 를 지연 생성 후 영구 보관하므로
    (session_state_proxy.py:52-64) 테스트 간 상태가 누수된다.
    """
    import streamlit as st
    from streamlit.runtime.state import session_state_proxy as _proxy

    _proxy._mock_session_state = None
    try:
        yield st.session_state
    finally:
        _proxy._mock_session_state = None
