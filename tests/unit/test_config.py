"""report_app/config.py 설정 계약 테스트 (INF-03).

config.py 는 import 시점에 `Path.cwd()` 를 단 한 번 평가해 모든 경로 상수를
고정한다(config.py:80). 그래서 conftest 가 수집(collection) 전에 chdir 를 끝내야
하고, 이 파일의 경로 단언도 "지금의 cwd" 가 아니라 "import 시점의 cwd = SANDBOX"
를 기준으로 한다. 다른 테스트가 cwd 를 흘려도 이 단언은 흔들리지 않는다.

reload 를 쓰는 테스트는 반드시 _restore_config() 로 원상복구한다. importlib.reload
는 모듈 객체를 제자리에서 다시 실행할 뿐, 이미 `from config import X` 로 값을
복사해 간 다른 모듈(data_loader, gpt_reporter 등)의 바인딩은 바꾸지 않는다.
따라서 reload 직후의 값은 반드시 reload 가 돌려준 모듈 객체에서만 읽는다.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

import report_app.config as config
from tests.conftest import PROJECT_ROOT, SANDBOX

_CLOUD_ENV_KEYS = ("IS_CLOUD", "STREAMLIT_SHARING_MODE")


def _restore_config():
    """클라우드 감지 환경변수를 지우고 샌드박스 cwd 에서 config 를 재적재해 원상복구한다.

    reload 테스트마다 finally 에서 호출해, 이 모듈을 공유하는 다른 테스트가
    오염된 상수를 보지 않게 한다.
    """
    for key in _CLOUD_ENV_KEYS:
        os.environ.pop(key, None)
    os.chdir(SANDBOX)
    return importlib.reload(config)


# ===========================================================================
# INF-03 : IS_CLOUD 파싱 (특성화)
# ===========================================================================

@pytest.mark.characterization
@pytest.mark.parametrize("env_key", _CLOUD_ENV_KEYS)
@pytest.mark.parametrize("env_value", ["0", "false", "False", "no", "off"])
def test_inf03_is_cloud_true_for_any_nonempty_value(monkeypatch, env_key: str, env_value: str):
    """INF-03(특성화): IS_CLOUD 가 bool(os.environ.get(...)) 이라 "0"·"false" 같은 값도 True 가 된다."""
    try:
        monkeypatch.setenv(env_key, env_value)
        reloaded = importlib.reload(config)
        assert reloaded.IS_CLOUD is True, (
            f"{env_key}={env_value!r} 인데 IS_CLOUD 가 True 가 아니다. "
            "현재 구현은 문자열 내용을 보지 않고 비어있지 않기만 하면 참으로 친다(config.py:46)."
        )
    finally:
        restored = _restore_config()

    # 복구 실패를 다른 파일이 아니라 이 테스트에서 드러낸다.
    assert restored.IS_CLOUD is False
    assert restored.DATA_DIR == SANDBOX / "output"


@pytest.mark.characterization
@pytest.mark.parametrize("env_key", _CLOUD_ENV_KEYS)
def test_inf03_is_cloud_false_for_empty_string(monkeypatch, env_key: str):
    """INF-03(특성화): 값이 빈 문자열이면 bool("") 이 False 라 IS_CLOUD 도 False 다."""
    try:
        monkeypatch.setenv(env_key, "")
        reloaded = importlib.reload(config)
        assert reloaded.IS_CLOUD is False
    finally:
        restored = _restore_config()

    assert restored.IS_CLOUD is False


def test_inf03_is_cloud_false_when_env_absent():
    """INF-03: 두 환경변수가 모두 없으면 IS_CLOUD 는 False 이고 타입은 bool 이다."""
    for key in _CLOUD_ENV_KEYS:
        assert key not in os.environ, "conftest 의 autouse 격리가 환경변수를 지웠어야 한다"
    assert config.IS_CLOUD is False
    assert isinstance(config.IS_CLOUD, bool)


# ===========================================================================
# INF-03 : 경로 상수
# ===========================================================================

def test_inf03_path_constants_are_pinned_to_import_time_cwd():
    """INF-03: DATA_DIR/REPORT_DIR/CSV 경로가 import 시점 cwd(= 샌드박스) 기준으로 고정된다."""
    assert config.DATA_DIR == SANDBOX / "output", (
        "config 의 경로 상수는 import 시점 Path.cwd() 에 묶인다(config.py:80). "
        f"기대={SANDBOX / 'output'}, 실제={config.DATA_DIR}"
    )
    assert config.REPORT_DIR == config.DATA_DIR / "reports"
    assert config.NATIONAL_CSV == config.DATA_DIR / "전체_대학_데이터.csv"
    assert config.REGIONAL_CSV == config.DATA_DIR / "권역별_순위.csv"
    assert config.REGIONAL_CSV_LEGACY == config.DATA_DIR / "충청권_순위.csv"


def test_inf03_csv_filenames_are_the_contract():
    """INF-03: 세 CSV 상수의 파일명이 전처리 산출물 이름과 정확히 일치한다."""
    assert config.NATIONAL_CSV.name == "전체_대학_데이터.csv"
    assert config.REGIONAL_CSV.name == "권역별_순위.csv"
    assert config.REGIONAL_CSV_LEGACY.name == "충청권_순위.csv"
    # 새 포맷과 레거시 포맷은 서로 다른 파일이어야 폴백(data_loader.py:63-67)이 의미를 갖는다.
    assert config.REGIONAL_CSV != config.REGIONAL_CSV_LEGACY


def test_inf03_paths_are_reevaluated_on_reload(tmp_path):
    """INF-03: config 는 import/reload 시점의 Path.cwd() 를 재평가한다(경로가 cwd 를 따라간다)."""
    before = config.DATA_DIR
    try:
        os.chdir(tmp_path)
        expected_root = Path.cwd()
        reloaded = importlib.reload(config)

        assert reloaded.DATA_DIR == expected_root / "output"
        assert reloaded.REPORT_DIR == expected_root / "output" / "reports"
        assert reloaded.NATIONAL_CSV == expected_root / "output" / "전체_대학_데이터.csv"
        assert reloaded.DATA_DIR != before, "reload 가 cwd 를 재평가하지 않았다"
    finally:
        restored = _restore_config()

    assert restored.DATA_DIR == SANDBOX / "output"
    assert restored.DATA_DIR == before


# ===========================================================================
# INF-03 : 대학·비교군·GPT·보고서 설정
# ===========================================================================

def test_inf03_university_constant():
    """INF-03: 분석 대상 대학명이 '호서대학교' 로 고정된다."""
    assert config.UNIVERSITY == "호서대학교"


def test_inf03_compare_group_contract():
    """INF-03: 비교군이 중복 없는 5개 대학이고 대상 대학(호서대)을 포함한다."""
    assert config.COMPARE_GROUP == [
        "순천향대학교",
        "선문대학교",
        "한서대학교",
        "나사렛대학교",
        "호서대학교",
    ]
    assert len(config.COMPARE_GROUP) == 5
    assert len(set(config.COMPARE_GROUP)) == 5, "비교군에 중복 대학이 있다"
    assert config.UNIVERSITY in config.COMPARE_GROUP, "비교군은 대상 대학 자신을 포함해야 한다"
    assert config.COMPARE_GROUP_NAME == "천안·아산 5개 대학"


def test_inf03_gpt_settings():
    """INF-03: GPT 모델·토큰·온도 설정값을 계약으로 고정한다."""
    assert config.GPT_MODEL == "gpt-4o"
    assert config.GPT_MAX_TOKENS == 2000
    assert isinstance(config.GPT_MAX_TOKENS, int)
    assert config.GPT_TEMPERATURE == pytest.approx(0.4)
    assert 0.0 <= config.GPT_TEMPERATURE <= 2.0


def test_inf03_report_settings():
    """INF-03: 보고서 폰트·제목 문자열을 계약으로 고정한다."""
    assert config.REPORT_FONT == "맑은 고딕"
    assert config.REPORT_TITLE == "전임교원 연구실적 현황 분석 보고서"


# ===========================================================================
# INF-03 : REGION_MAP
# ===========================================================================

def test_inf03_region_map_contract():
    """INF-03: REGION_MAP 이 시도 17개 키를 6개 권역값으로 매핑한다."""
    assert len(config.REGION_MAP) == 17, f"시도 키 개수가 17이 아님: {len(config.REGION_MAP)}"
    assert set(config.REGION_MAP.values()) == {
        "수도권",
        "강원권",
        "충청권",
        "호남권",
        "영남권",
        "제주권",
    }
    assert len(set(config.REGION_MAP.values())) == 6

    # 충청권 4개 시도는 이 프로젝트의 기본 권역이라 개별로도 못 박는다.
    assert [k for k, v in config.REGION_MAP.items() if v == "충청권"] == [
        "대전",
        "세종",
        "충남",
        "충북",
    ]
    assert config.REGION_MAP["서울"] == "수도권"
    assert config.REGION_MAP["제주"] == "제주권"


@pytest.mark.characterization
def test_inf03_region_map_is_dead_duplicate_inside_report_app():
    """INF-03(특성화, D02): config.REGION_MAP 이 report_app 어디에서도 참조되지 않는 죽은 중복이다."""
    app_dir = PROJECT_ROOT / "report_app"
    hits = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in app_dir.rglob("*.py")
        if "REGION_MAP" in path.read_text(encoding="utf-8")
    )

    assert hits == ["report_app/config.py"], (
        "REGION_MAP 이 정의부(config.py) 말고 다른 곳에서도 등장한다. "
        f"실제 등장 파일: {hits}. 실제 권역 매핑은 전처리 스크립트가 자기 사본으로 수행한다"
        " (전임교원_연구실적_전처리.py:38, :414)."
    )


@pytest.mark.characterization
def test_inf03_region_map_duplicate_matches_preprocessor_copy(pp_module):
    """INF-03(특성화, D02): 전처리 스크립트의 REGION_MAP 사본이 config 쪽과 값까지 동일하다."""
    assert pp_module.REGION_MAP == config.REGION_MAP, (
        "두 사본의 값이 갈라졌다. 값이 같다는 전제가 깨지면 중복 제거 리팩터링의 난이도가 달라진다."
    )
