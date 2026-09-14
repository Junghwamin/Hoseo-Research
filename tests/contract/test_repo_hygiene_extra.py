"""Phase 3.5 리뷰에서 추가된 결함의 잠금 테스트 (정적/설정 계약).

기존 `test_repo_hygiene.py` 는 다른 에이전트가 작성했으므로 건드리지 않고
새 파일에 추가한다.

- V21  : Streamlit 이 `report_app/pages/` 를 멀티페이지 v1 디렉터리로 인식
- R-RS-05 : `_render_source_existing` 이 `pd.read_csv` 를 직접 호출해
            `_ensure_new_format` 과 레거시 폴백을 모두 우회
"""

import ast
import tomllib
from pathlib import Path

import pytest

from tests.conftest import PROJECT_ROOT


# ---------------------------------------------------------------------------
# V21 — 멀티페이지 v1 자동 네비게이션
# ---------------------------------------------------------------------------
# 배경: streamlit.runtime.pages_manager.PagesManager 는 최초 생성 시
#   `<메인 스크립트 부모>/pages` 존재 여부로 `uses_pages_directory` 를 정한다.
#   True 면 script_runner.py:668 이 `_mpa_v1()` 을 타고, 메인 스크립트 + pages/*.py
#   전부를 StreamlitPage 로 만들어 사이드바에 자동 네비게이션을 붙인다
#   (`client.showSidebarNavigation` 기본값 True).
#   `report_app/pages/` 에는 home.py·research.py·settings.py 가 있고 셋 다
#   함수 정의만 있어 진입점 호출이 없다 → 클릭하면 빈 화면.
#
# AppTest 는 샌드박스 cwd 에서 돌아 `.streamlit/` 이 없으므로 이 결함은
# 런타임 관측이 아니라 **설정 파일 계약**으로 잠근다.

_APP_ENTRY = PROJECT_ROOT / "report_app" / "app.py"
_PAGES_DIR = PROJECT_ROOT / "report_app" / "pages"
_ST_CONFIG = PROJECT_ROOT / ".streamlit" / "config.toml"


def test_v21_배경_pages_디렉터리와_진입점이_나란히_있다():
    """전제 확인 — 이 구조가 아니면 V21 은 성립하지 않는다."""
    assert _APP_ENTRY.exists()
    assert _PAGES_DIR.is_dir()
    page_scripts = sorted(
        p.name for p in _PAGES_DIR.glob("*.py") if p.name != "__init__.py"
    )
    assert page_scripts == ["home.py", "research.py", "settings.py"]


@pytest.mark.characterization
def test_v21_페이지_스크립트에_렌더_진입점_호출이_없다():
    """[수정 후에도 유지 가능] 자동 네비로 열면 빈 화면이 되는 이유.

    모듈 최상단에 렌더 함수 호출이 없다 = 단독 실행 시 아무것도 그리지 않는다.
    """
    for name in ("home.py", "research.py", "settings.py"):
        tree = ast.parse((_PAGES_DIR / name).read_text(encoding="utf-8"))
        top_calls = [
            n
            for n in tree.body
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        ]
        assert top_calls == [], f"{name} 에 최상단 호출이 생겼다 — 전제 재확인 필요"


def test_v21_자동_사이드바_네비게이션이_꺼져_있어야_한다():
    """수정 후 기대 — 둘 중 하나를 만족한다.

    (a) `.streamlit/config.toml` 에 `client.showSidebarNavigation = false`, 또는
    (b) `report_app/pages/` 가 더 이상 존재하지 않는다(디렉터리 개명).

    (a) 는 네비만 숨길 뿐 `_mpa_v1()` 실행과 /home·/research·/settings URL 자체는
    남는다. 잔여 위험은 보고서에 기재한다.
    """
    if not _PAGES_DIR.is_dir():
        return  # (b) 로 해소됨

    assert _ST_CONFIG.exists(), ".streamlit/config.toml 이 없다"
    cfg = tomllib.loads(_ST_CONFIG.read_text(encoding="utf-8"))
    value = cfg.get("client", {}).get("showSidebarNavigation")
    assert value is False, (
        "client.showSidebarNavigation 이 false 가 아니다 "
        f"(현재: {value!r}) — Streamlit 이 app/home/research/settings 4개를 "
        "사이드바 네비게이션에 자동 주입한다"
    )


# ---------------------------------------------------------------------------
# R-RS-05 — 기존 output/ 소스가 read_csv 를 직접 호출
# ---------------------------------------------------------------------------
_RESEARCH = PROJECT_ROOT / "report_app" / "pages" / "research.py"


def _func_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(_RESEARCH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수를 찾지 못했다 — 리팩터링됐는지 확인할 것")


def _calls(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                base = f.value.id if isinstance(f.value, ast.Name) else ""
                out.append(f"{base}.{f.attr}" if base else f.attr)
            elif isinstance(f, ast.Name):
                out.append(f.id)
    return out


def test_rrs05_기존output_소스는_load_all_data를_거쳐야_한다():
    """수정 후 기대 — 레거시 변환과 폴백이 한 곳에만 있어야 한다.

    `data_loader.load_all_data` 는 `REGIONAL_CSV_LEGACY` 폴백(:65)과
    `_ensure_new_format` 을 모두 갖고 있다. 소스 카드가 이를 우회하면
    레거시 CSV 만 있는 설치본에서 "파일 없음" 으로 오표기된다(V15 와 같은 뿌리).
    """
    calls = _calls(_func_node("_render_source_existing"))
    assert any(c.endswith("load_all_data") or c.endswith("_ensure_new_format") for c in calls), (
        f"load_all_data/_ensure_new_format 호출이 없다. 실제 호출: {sorted(set(calls))}"
    )


def test_rrs05_존재확인이_레거시_CSV도_인정해야_한다():
    """수정 후 기대 — 레거시 파일만 있어도 '없음' 으로 표시하지 않는다."""
    src = _RESEARCH.read_text(encoding="utf-8")
    node = _func_node("_render_source_existing")
    seg = ast.get_source_segment(src, node) or ""
    assert "REGIONAL_CSV_LEGACY" in seg, (
        "_render_source_existing 이 REGIONAL_CSV_LEGACY 를 전혀 참조하지 않는다"
    )


# ---------------------------------------------------------------------------
# V22 (보안) — 인스톨러가 .streamlit/ 을 통째로 복사한다
# ---------------------------------------------------------------------------
# `installer/windows/build_windows.py` 가 제외 필터 없이 copytree 를 한다.
# `.gitignore:40` 은 `.streamlit/secrets.toml` 을 git 에서만 막을 뿐
# 빌드 스크립트는 막지 않는다. 배포 문서는 Cloud 용으로 secrets 에 실제 키를
# 넣으라고 안내하므로, 유지보수자가 로컬에 secrets.toml 을 만든 뒤 인스톨러를
# 빌드하면 배포 산출물 안으로 실키가 들어간다.
#
# 실측: 현재 이 저장소의 `.streamlit/` 에는 config.toml 만 있고
# secrets.toml 은 없다. 유출된 키는 없고 경로만 열려 있다.
#
# 이 테스트는 어떤 키 값도 읽거나 출력하지 않는다. 복사 로직만 정적으로 본다.

_INSTALLER_DIR = PROJECT_ROOT / "installer"


def _installer_scripts() -> list[Path]:
    if not _INSTALLER_DIR.is_dir():
        return []
    return sorted(
        [p for p in _INSTALLER_DIR.rglob("*.py")]
        + [p for p in _INSTALLER_DIR.rglob("*.sh")]
    )


def _scripts_touching_streamlit_dir() -> list[Path]:
    out = []
    for path in _installer_scripts():
        text = path.read_text(encoding="utf-8", errors="replace")
        if ".streamlit" in text:
            out.append(path)
    return out


def test_v22_배경_인스톨러가_streamlit_디렉터리를_다룬다():
    """전제 확인 — 다루지 않는다면 V22 는 성립하지 않는다."""
    touching = _scripts_touching_streamlit_dir()
    assert touching, "인스톨러 스크립트가 .streamlit 을 전혀 언급하지 않는다"


@pytest.mark.characterization
def test_v22_현재_저장소에_커밋된_secrets_파일은_없다():
    """[유지] 지금 유출 중인 키가 없다는 사실을 고정한다.

    파일의 존재 여부만 본다. 내용은 절대 읽지 않는다.
    """
    assert not (PROJECT_ROOT / ".streamlit" / "secrets.toml").exists(), (
        ".streamlit/secrets.toml 이 작업 트리에 있다. "
        "인스톨러를 빌드하면 배포본에 포함된다 — 즉시 제거할 것."
    )


def test_v22_인스톨러는_secrets_파일을_번들에서_제외해야_한다():
    """수정 후 기대 (구현 중립).

    `.streamlit` 을 다루는 모든 인스톨러 스크립트가 둘 중 하나를 만족한다.
    (a) 복사에 제외 패턴을 건다 (`ignore=`, `--exclude`, `-x` 등에 secrets 언급), 또는
    (b) 디렉터리 통째가 아니라 `config.toml` 만 콕 집어 복사한다.
    """
    offenders = []
    for path in _scripts_touching_streamlit_dir():
        text = path.read_text(encoding="utf-8", errors="replace")
        excludes_secrets = "secrets" in text and any(
            token in text
            for token in (
                "ignore", "exclude", "--exclude", "ignore_patterns",
                "rm -f", "rm -rf", "unlink",  # 복사 후 즉시 삭제도 유효한 제외다
            )
        )
        copies_only_config = "config.toml" in text and "copytree" not in text
        if not (excludes_secrets or copies_only_config):
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert not offenders, (
        "다음 인스톨러 스크립트가 .streamlit/ 을 제외 필터 없이 번들한다: "
        f"{offenders} — 로컬 secrets.toml 이 배포 .exe/.dmg 안으로 들어갈 수 있다"
    )
