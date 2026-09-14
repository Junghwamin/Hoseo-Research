"""INF-04 / INF-05 — 저장소 위생(repository hygiene)과 인스톨러 번들 계약.

담당 테스트 ID
    - INF-04 : .gitignore, 추적 파일 내 API 키 유출, 개발 의존성 핀,
               배포 문서의 secrets 형식, 문서에 남은 옛 경로,
               Python 버전 선언 일관성.
    - INF-05 : Windows 인스톨러가 번들하는 CSV 목록과,
               앱이 "파일 없음" 을 경고할 때 지목하는 파일명.

안전 규칙
    API 키 스캔은 매치된 **내용을 절대 출력하지 않는다.** 실패 메시지에는
    파일 경로와 줄 번호만 담는다.

실행 규칙
    INF-05 는 정적 AST 분석만 한다. 인스톨러 빌드(build_windows.py)를
    실행하지 않으며, report_app.pages.research 를 import 하지도 않는다
    (import 만으로 streamlit 부작용이 발생하기 때문).
"""

from __future__ import annotations

import ast
import re
import subprocess
import textwrap
import tomllib

import pytest

from tests.conftest import PROJECT_ROOT

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

#: OpenAI 스타일 시크릿 리터럴. 매치되면 파일:줄만 보고한다.
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")

#: 텍스트로 읽지 않을 확장자(바이너리).
_BINARY_SUFFIXES = {
    ".xlsx", ".xls", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
    ".zip", ".exe", ".dll", ".pyc", ".woff", ".woff2", ".ttf", ".docx",
}

#: 문서에 남으면 안 되는 옛 경로 문자열 (저장소 이름이 Hoseo-Research 로 바뀜).
_STALE_PATH_TOKENS = ("Hoseo-IR-", "C--Users-----Desktop-IR---MCP")

#: 옛 경로를 검사할 추적 문서.
_TRACKED_DOCS = ["README.md", "CLAUDE.md"]

_CHECKLIST = PROJECT_ROOT / "docs" / "CHECKLIST_StreamlitCloud_배포.md"
_BUILD_WINDOWS = PROJECT_ROOT / "installer" / "windows" / "build_windows.py"
_RESEARCH_PAGE = PROJECT_ROOT / "report_app" / "pages" / "research.py"

_PY_VERSION_RE = re.compile(r"(\d+)\.(\d+)")


# ---------------------------------------------------------------------------
# 로컬 헬퍼
# ---------------------------------------------------------------------------

def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def _git_tracked_files() -> list[str]:
    """git 이 추적 중인 파일 경로 목록(저장소 루트 기준 상대 경로).

    conftest 가 cwd 를 샌드박스로 옮겨 두었으므로 cwd 를 명시해야 한다.
    core.quotepath=false 로 한글 파일명이 이스케이프되지 않게 한다.
    """
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, FileNotFoundError) as exc:  # pragma: no cover - 환경 의존
        pytest.skip(f"git 실행 불가: {exc}")
    if completed.returncode != 0:
        pytest.skip("git ls-files 실패 — git 저장소가 아니거나 git 이 없다")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _tracked_text_files() -> list:
    """추적 파일 중 텍스트로 읽을 수 있는 것만 (경로, 내용) 으로 돌려준다."""
    result = []
    for relative in _git_tracked_files():
        path = PROJECT_ROOT / relative
        if not path.is_file() or path.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            head = path.read_bytes()[:8192]
        except OSError:
            continue
        if b"\x00" in head:  # NUL 이 있으면 바이너리로 간주
            continue
        try:
            result.append((relative, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return result


def _toml_code_fences(markdown: str) -> list[str]:
    """마크다운의 ```toml 코드펜스 본문 목록을 들여쓰기 제거 후 돌려준다."""
    blocks: list[str] = []
    current: list[str] | None = None
    for line in markdown.splitlines():
        stripped = line.strip()
        if current is None:
            if stripped.startswith("```toml"):
                current = []
            continue
        if stripped == "```":
            blocks.append(textwrap.dedent("\n".join(current)))
            current = None
        else:
            current.append(line)
    return blocks


def _declared_python_versions() -> dict[str, str]:
    """버전을 선언하는 3개 파일에서 major.minor 를 뽑는다."""
    declared: dict[str, str] = {}

    py_version = PROJECT_ROOT / ".python-version"
    if py_version.exists():
        match = _PY_VERSION_RE.search(_read(py_version))
        if match:
            declared[".python-version"] = f"{match.group(1)}.{match.group(2)}"

    runtime = PROJECT_ROOT / "runtime.txt"
    if runtime.exists():
        match = _PY_VERSION_RE.search(_read(runtime))
        if match:
            declared["runtime.txt"] = f"{match.group(1)}.{match.group(2)}"

    workflow = PROJECT_ROOT / ".github" / "workflows" / "build-installer.yml"
    if workflow.exists():
        found = re.findall(r"python-version:\s*['\"]?(\d+\.\d+)", _read(workflow))
        for index, value in enumerate(found):
            key = "build-installer.yml" if index == 0 else f"build-installer.yml#{index}"
            declared[key] = value

    return declared


def _missing_append_args() -> list[ast.expr]:
    """research.py `_render_source_existing` 안의 missing.append(...) 인자 노드."""
    source = _read(_RESEARCH_PAGE)
    tree = ast.parse(source)
    targets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_render_source_existing"
    ]
    assert targets, "_render_source_existing 함수를 찾지 못했다"
    args: list[ast.expr] = []
    for node in ast.walk(targets[0]):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "missing"
        ):
            args.extend(node.args)
    assert args, "missing.append(...) 호출을 찾지 못했다"
    return args


def _installer_csv_literals() -> set[str]:
    """build_windows.py 안의 '*.csv' 문자열 리터럴 집합 (AST 기반)."""
    tree = ast.parse(_read(_BUILD_WINDOWS))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(".csv")
    }


def _installer_bundled_csv_names() -> list[str]:
    """build_windows.py 의 `data_csv_names()` 를 실제로 실행해 결과를 얻는다.

    파일명을 리터럴로 두는 대신 `report_app/config.py` 에서 파생시키는 구현을
    인정하기 위한 것이다. 모듈 전체를 import 하면 빌드 부작용이 생기므로
    해당 함수 정의만 떼어 실행한다.
    """
    tree = ast.parse(_read(_BUILD_WINDOWS))
    funcs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "data_csv_names"
    ]
    if not funcs:
        return []
    namespace: dict = {"PROJECT_ROOT": PROJECT_ROOT}
    module = ast.Module(body=funcs, type_ignores=[])
    exec(compile(module, "<build_windows:data_csv_names>", "exec"), namespace)  # noqa: S102
    return list(namespace["data_csv_names"]())


# ---------------------------------------------------------------------------
# INF-04 케이스 구현 (표 주도 - table driven)
# ---------------------------------------------------------------------------

def _case_gitignore_env() -> None:
    content = _read(PROJECT_ROOT / ".gitignore")
    lines = {line.strip() for line in content.splitlines()}
    assert ".env" in lines, f".gitignore 에 '.env' 패턴이 없다: {sorted(lines)[:15]}"


def _case_gitignore_secrets_toml() -> None:
    content = _read(PROJECT_ROOT / ".gitignore")
    assert "secrets.toml" in content, (
        ".gitignore 에 secrets.toml 패턴이 없다 — Streamlit secrets 가 커밋될 수 있다"
    )


def _case_no_api_key_literal() -> None:
    """추적 텍스트 파일 전체에 API 키 리터럴이 없어야 한다.

    실패 메시지에는 파일:줄만 넣는다. 매치된 문자열은 절대 출력하지 않는다.
    """
    hits: list[str] = []
    for relative, text in _tracked_text_files():
        for number, line in enumerate(text.splitlines(), start=1):
            if _SECRET_RE.search(line):
                hits.append(f"{relative}:{number}")
    assert hits == [], (
        f"API 키로 보이는 리터럴이 추적 파일 {len(hits)}곳에 있다 "
        f"(내용은 표시하지 않는다): {hits}"
    )


def _case_pytest_timeout_pinned() -> None:
    """pytest.ini 가 --timeout 을 쓰므로 pytest-timeout 이 핀되어 있어야 한다."""
    addopts = _read(PROJECT_ROOT / "pytest.ini")
    assert "--timeout" in addopts, "pytest.ini 가 --timeout 을 쓰지 않는다 (전제 확인)"

    dev_requirements = _read(PROJECT_ROOT / "requirements-dev.txt")
    pinned = re.search(r"^pytest-timeout==\S+", dev_requirements, re.M)
    assert pinned, (
        "requirements-dev.txt 에 pytest-timeout 이 == 로 핀되어 있지 않다:\n"
        f"{dev_requirements}"
    )


def _case_docs_secrets_flat_key() -> None:
    """V16: 배포 문서의 secrets 예시가 코드가 읽는 형식과 같아야 한다.

    앱은 최상위 평면 키 OPENAI_API_KEY 를 읽는데, 문서는 [openai] 중첩
    테이블의 api_key 를 안내한다. 문서대로 하면 키가 인식되지 않는다.
    """
    if not _CHECKLIST.exists():
        pytest.skip("배포 체크리스트 문서가 없다")
    fences = _toml_code_fences(_read(_CHECKLIST))
    assert fences, "문서에 ```toml 코드펜스가 없다"

    parsed: list[dict] = []
    for block in fences:
        try:
            parsed.append(tomllib.loads(block))
        except tomllib.TOMLDecodeError:
            continue
    assert parsed, "파싱 가능한 toml 코드펜스가 없다"

    flat = [document for document in parsed if "OPENAI_API_KEY" in document]
    assert flat, (
        "배포 문서의 toml 예시에 최상위 평면 키 OPENAI_API_KEY 가 없다. "
        f"현재 최상위 키: {[sorted(d) for d in parsed]}"
    )


def _case_docs_no_stale_paths() -> None:
    """D15: 추적 문서에 옛 저장소명/옛 프로젝트 경로가 남아 있으면 안 된다."""
    documents = [PROJECT_ROOT / name for name in _TRACKED_DOCS]
    documents += sorted((PROJECT_ROOT / "docs").glob("*.md"))

    hits: list[str] = []
    for path in documents:
        if not path.exists():
            continue
        for number, line in enumerate(_read(path).splitlines(), start=1):
            for token in _STALE_PATH_TOKENS:
                if token in line:
                    hits.append(f"{path.relative_to(PROJECT_ROOT).as_posix()}:{number} ({token})")
    assert hits == [], f"문서에 옛 경로 문자열이 {len(hits)}곳 남아 있다: {hits}"


def _case_python_version_single() -> None:
    """Python 버전 선언이 세 파일에서 한 값으로 모여 있어야 한다."""
    declared = _declared_python_versions()
    assert len(declared) >= 3, f"버전 선언 파일을 충분히 찾지 못했다: {declared}"
    versions = set(declared.values())
    assert len(versions) == 1, (
        f"Python 버전 선언이 갈렸다 (major.minor {len(versions)}종): {declared}"
    )


_INF04_CASES = {
    "gitignore_env": _case_gitignore_env,
    "gitignore_secrets_toml": _case_gitignore_secrets_toml,
    "no_api_key_literal": _case_no_api_key_literal,
    "pytest_timeout_pinned": _case_pytest_timeout_pinned,
    "docs_secrets_flat_key": _case_docs_secrets_flat_key,
    "docs_no_stale_paths": _case_docs_no_stale_paths,
    "python_version_single": _case_python_version_single,
}


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("gitignore_env"),
        pytest.param("gitignore_secrets_toml"),
        pytest.param("no_api_key_literal"),
        pytest.param("pytest_timeout_pinned"),
        pytest.param("docs_secrets_flat_key"),
        pytest.param("docs_no_stale_paths"),
        pytest.param("python_version_single"),
    ],
)
def test_inf04_저장소_위생(case_id):
    """INF-04: 저장소 위생 규칙 7가지를 한 표(table)로 고정한다.

    Phase 4 에서 V16 / D15 / 버전 드리프트를 모두 해소해 7개 전부 통과 계약이다.
    (이전에는 뒤 3개가
    확정 결함이므로 "고쳐진 뒤의 정답" 을 단언하는 xfail(strict) 이다.
    """
    _INF04_CASES[case_id]()


def test_inf04_핀_버전과_설치_버전을_정보성으로_비교한다():
    """INF-04(정보): requirements.txt 핀과 실제 설치 버전 차이를 출력만 한다.

    실패시키지 않는다. QA venv 가 핀과 어긋났는지 눈으로 확인하기 위한 기록이다.
    """
    from importlib.metadata import PackageNotFoundError, version

    report: list[str] = []
    for raw in _read(PROJECT_ROOT / "requirements.txt").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=)?\s*(\S+)?$", line)
        if not match:
            report.append(f"  (해석 불가) {line}")
            continue
        name, operator, pinned = match.group(1), match.group(2) or "", match.group(3) or ""
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = "(미설치)"
        flag = "" if (operator == "==" and installed == pinned) else "  <- 확인"
        report.append(f"  {name}: 핀 {operator}{pinned} / 설치 {installed}{flag}")

    print("requirements.txt 핀 vs 설치 버전")
    print("\n".join(report))
    assert report, "requirements.txt 가 비어 있다"


# ===========================================================================
# INF-05 — 인스톨러 번들과 누락 경고 (정적 AST, 빌드 실행 금지)
# ===========================================================================

def test_inf05_인스톨러가_권역별_순위_CSV_를_번들한다():
    """INF-05/V15: build_windows.py 가 복사하는 CSV 목록에 권역별_순위.csv 가 있어야 한다.

    앱은 권역별_순위.csv 를 우선 읽고 없을 때만 레거시 충청권_순위.csv 로
    떨어진다(data_loader.load_all_data). 인스톨러가 새 포맷을 빼면 설치본은
    영원히 레거시(충청권 1개 권역)로만 동작한다.
    """
    literals = _installer_csv_literals()
    if "권역별_순위.csv" in literals:
        return

    # 리터럴이 없어도 config 에서 파생시키면 인정한다 — 오히려 더 나은 구현이다.
    # `data_csv_names()` 를 실제로 실행해 결과 목록에 신형 CSV 가 있는지 본다.
    names = _installer_bundled_csv_names()
    assert "권역별_순위.csv" in names, (
        f"인스톨러가 번들하는 CSV: 리터럴 {sorted(literals)} / 파생 {names} "
        "— 권역별_순위.csv 가 없다"
    )


def test_inf05_누락경고가_REGIONAL_CSV_이름을_참조한다():
    """INF-05/V15: 누락 경고가 하드코딩 '충청권_순위.csv' 대신 REGIONAL_CSV.name 을 써야 한다.

    `_render_source_existing` 은 `REGIONAL_CSV.exists()`(= 권역별_순위.csv)로
    존재 여부를 판정해 놓고, 없을 때는 '충청권_순위.csv' 가 없다고 알린다.
    사용자는 존재하는 파일을 가리키며 없다는 경고를 보게 된다.
    """
    args = _missing_append_args()
    rendered = [ast.dump(node) for node in args]

    hardcoded = [
        sub.value
        for node in args
        for sub in ast.walk(node)
        if isinstance(sub, ast.Constant) and sub.value == "충청권_순위.csv"
    ]
    assert not hardcoded, (
        "missing.append 에 '충청권_순위.csv' 가 하드코딩되어 있다 "
        f"(인자 {len(args)}개): {rendered}"
    )

    # f-string 안에 들어간 참조도 인정해야 한다.
    # `f"{REGIONAL_CSV.name}(또는 {REGIONAL_CSV_LEGACY.name})"` 는 JoinedStr 이라
    # 인자 노드를 직접 비교하면 놓친다.
    def _refs_regional(node) -> bool:
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Attribute)
                and sub.attr == "name"
                and isinstance(sub.value, ast.Name)
                and sub.value.id == "REGIONAL_CSV"
            ):
                return True
        return False

    references_regional = any(_refs_regional(node) for node in args)
    assert references_regional, (
        f"missing.append 인자 중 REGIONAL_CSV.name 을 참조하는 것이 없다: {rendered}"
    )
