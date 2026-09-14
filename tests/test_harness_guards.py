"""테스트 하네스 자체를 지키는 가드.

여기가 깨지면 다른 모든 테스트의 결과를 신뢰할 수 없다.
(CONF-01/02, TST-02, MPL-01)
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
import pytest

from tests.conftest import MPL_CONFIG_DIR, PROJECT_ROOT, SANDBOX


class TestSandboxBinding:
    """CONF-01: cwd 고정이 report_app import 보다 먼저 일어났는가."""

    def test_config_project_root_is_sandbox(self):
        """config.py:80 의 Path.cwd() 가 샌드박스로 평가됐어야 한다."""
        import report_app.config as cfg

        assert cfg._PROJECT_ROOT == SANDBOX, (
            "report_app.config 가 샌드박스 chdir 이전에 import 됐다. "
            "conftest.py 모듈 레벨 순서를 확인하라."
        )

    def test_bound_csv_paths_point_into_sandbox(self):
        """값으로 바인딩된 경로 상수 3곳이 모두 샌드박스를 가리켜야 한다."""
        import report_app.config as cfg
        import report_app.data_loader as dl
        import report_app.pages.research as research

        expected = SANDBOX / "output"
        assert cfg.NATIONAL_CSV.parent == expected
        assert dl.NATIONAL_CSV.parent == expected
        assert dl.REGIONAL_CSV.parent == expected
        assert dl.REGIONAL_CSV_LEGACY.parent == expected
        assert research.NATIONAL_CSV.parent == expected
        assert research.REGIONAL_CSV.parent == expected
        assert research.REPORT_DIR == expected / "reports"

    def test_cwd_is_sandbox(self):
        assert Path.cwd() == SANDBOX

    def test_project_root_is_repo(self):
        assert (PROJECT_ROOT / "report_app" / "app.py").exists()
        assert (PROJECT_ROOT / "전임교원_연구실적_전처리.py").exists()


class TestEnvIsolation:
    """CONF-02: API 키와 .env 가 테스트 사이로 새지 않는가."""

    def test_no_api_key_in_env(self):
        assert "OPENAI_API_KEY" not in os.environ
        assert "IS_CLOUD" not in os.environ
        assert "STREAMLIT_SHARING_MODE" not in os.environ

    def test_sandbox_dotenv_absent(self):
        assert not (SANDBOX / ".env").exists()

    def test_dotenv_written_by_one_test_is_cleaned(self, tmp_path):
        """앞선 테스트가 샌드박스에 .env 를 남겨도 다음 테스트에서 지워진다."""
        (SANDBOX / ".env").write_text("OPENAI_API_KEY=sk-dummy\n", encoding="utf-8")
        assert (SANDBOX / ".env").exists()
        # teardown 의 _isolate_env_and_dotenv 가 지운다.


class TestMatplotlibHarness:
    """MPL-01: 헤드리스 백엔드와 tmp 캐시가 첫 import 이전에 잡혔는가."""

    def test_backend_is_agg(self):
        assert matplotlib.get_backend().lower() == "agg"

    def test_configdir_is_tmp(self):
        assert Path(matplotlib.get_configdir()) == Path(MPL_CONFIG_DIR)

    def test_chart_generator_preimported(self):
        """폰트 캐시 생성 비용이 AppTest run 밖에서 끝났는지 확인."""
        import sys

        assert "report_app.chart_generator" in sys.modules

    def test_no_leaked_figures_at_start(self):
        import matplotlib.pyplot as plt

        assert plt.get_fignums() == []


class TestAppTestWrapperSources:
    """TST-02: from_function 래퍼 소스가 ASCII 인가.

    Windows(cp949)에서 AppTest 는 래퍼 소스를 encoding 인자 없이
    write_text 로 기록하고(app_test.py:219-221) 실행기는 UTF-8 로 읽으므로
    (source_util.py:50-56), 본문에 한글이 있으면 SyntaxError 가 난다.
    한글 인자는 kwargs= 로 주입해야 한다.
    """

    def test_apptest_module_sources_are_ascii(self):
        apptest_dir = PROJECT_ROOT / "tests" / "apptest"
        offenders = []
        for path in sorted(apptest_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            in_wrapper = False
            for lineno, line in enumerate(text.splitlines(), start=1):
                if line.startswith("def _wrapper") or line.startswith("def wrapper"):
                    in_wrapper = True
                    continue
                if in_wrapper:
                    if line and not line[0].isspace():
                        in_wrapper = False
                        continue
                    if not line.isascii():
                        offenders.append(f"{path.name}:{lineno}")
        assert not offenders, (
            "from_function 래퍼 본문에 비ASCII 문자가 있다 "
            f"(kwargs 로 주입할 것): {offenders}"
        )
