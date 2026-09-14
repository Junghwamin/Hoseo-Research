"""UI-01 — CSS 계약(CSS contract) 정적 분석 테스트.

Streamlit 을 렌더하지 않고 소스 문자열만 읽어 검사한다. 앱은 CSS 를
`st.markdown(get_css(), unsafe_allow_html=True)` 로 한 번 주입하고,
컴포넌트는 `class="ir-..."` 문자열로 그 CSS 를 참조한다. 둘 사이에는
타입 검사도 린터도 없으므로, "쓰는 클래스"와 "정의된 셀렉터"가 어긋나도
앱은 조용히 스타일 없이 렌더된다. 그 조용한 어긋남을 여기서 잠근다.

고정 대상
    - get_css() 반환 문자열의 구조(<style> 래핑, 중괄호 균형)
    - 컴포넌트가 쓰는 ir- 클래스 중 어디에도 정의되지 않은 것이 0개 (D10)
    - 컴포넌트 인라인 <style> 셀렉터와 styles.py 셀렉터의 충돌이 0개 (D09)

D10 / D09 는 확정 결함이므로 xfail(strict) 로 "고쳐진 뒤의 정답" 을 단언한다.
오늘은 반드시 실패한다.
"""

from __future__ import annotations

import re

import pytest

from report_app.components.styles import get_css
from tests.conftest import PROJECT_ROOT

# ---------------------------------------------------------------------------
# 검사 대상 소스 파일
# ---------------------------------------------------------------------------

STYLES_PATH = PROJECT_ROOT / "report_app" / "components" / "styles.py"

COMPONENT_PATHS = [
    PROJECT_ROOT / "report_app" / "components" / "toolbar.py",
    PROJECT_ROOT / "report_app" / "components" / "metric_card.py",
    PROJECT_ROOT / "report_app" / "components" / "chart_card.py",
    PROJECT_ROOT / "report_app" / "components" / "gpt_section.py",
    PROJECT_ROOT / "report_app" / "components" / "sidebar.py",
    PROJECT_ROOT / "report_app" / "pages" / "home.py",
    PROJECT_ROOT / "report_app" / "pages" / "research.py",
    PROJECT_ROOT / "report_app" / "pages" / "settings.py",
]

#: class="a b c" / class='a b c' 양쪽 따옴표를 모두 잡는다.
_CLASS_ATTR_RE = re.compile(r"""class=["']([^"']*)["']""")
#: CSS 안의 .ir-xxx 셀렉터 조각.
_IR_SELECTOR_RE = re.compile(r"\.(ir-[A-Za-z0-9_-]+)")
#: 인라인 <style> ... </style> 블록.
_INLINE_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
#: CSS 주석.
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


# ---------------------------------------------------------------------------
# 로컬 헬퍼 (픽스처 모듈에 CSS 유틸이 없어 여기 정의한다)
# ---------------------------------------------------------------------------

def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def _rule_selectors(css_text: str) -> set[str]:
    """CSS 텍스트에서 규칙(rule) 셀렉터 문자열 집합을 뽑는다.

    '{' 앞의 셀렉터 목록을 쉼표로 쪼개고 공백을 정규화한다.
    @media/@import 등 at-rule 프렐류드는 제외한다.
    """
    text = _CSS_COMMENT_RE.sub("", css_text)
    found: set[str] = set()
    for match in re.finditer(r"([^{}@;]+)\{", text):
        for part in match.group(1).split(","):
            selector = " ".join(part.split())
            if selector and not selector.startswith("@"):
                found.add(selector)
    return found


def _inline_style_blocks(source: str) -> list[str]:
    """파이썬 소스 안의 인라인 <style> 블록 본문을 뽑는다.

    f-string 안에서는 CSS 중괄호가 `{{` / `}}` 로 이스케이프되어 있으므로
    되돌린 뒤 반환한다.
    """
    return [
        block.replace("{{", "{").replace("}}", "}")
        for block in _INLINE_STYLE_RE.findall(source)
    ]


def _used_ir_classes() -> dict[str, set[str]]:
    """컴포넌트 소스가 HTML 로 내보내는 ir- 클래스 → 사용 파일 집합."""
    used: dict[str, set[str]] = {}
    for path in COMPONENT_PATHS:
        source = _read(path)
        for attr_value in _CLASS_ATTR_RE.findall(source):
            for token in attr_value.split():
                # f-string 치환자({cls} 등)는 실제 클래스명이 아니다.
                if not token.startswith("ir-") or "{" in token or "}" in token:
                    continue
                used.setdefault(token, set()).add(path.name)
    return used


def _defined_ir_classes() -> set[str]:
    """styles.py + 모든 컴포넌트 인라인 <style> 에 정의된 ir- 클래스."""
    defined = set(_IR_SELECTOR_RE.findall(_read(STYLES_PATH)))
    for path in COMPONENT_PATHS:
        for block in _inline_style_blocks(_read(path)):
            defined |= set(_IR_SELECTOR_RE.findall(block))
    return defined


def _undefined_ir_classes() -> dict[str, set[str]]:
    defined = _defined_ir_classes()
    return {name: files for name, files in _used_ir_classes().items() if name not in defined}


def _inline_vs_styles_conflicts() -> dict[str, set[str]]:
    """인라인 <style> 셀렉터 중 styles.py 에도 정의된 것 → 정의 파일 집합."""
    global_selectors = _rule_selectors(_read(STYLES_PATH))
    conflicts: dict[str, set[str]] = {}
    for path in COMPONENT_PATHS:
        for block in _inline_style_blocks(_read(path)):
            for selector in _rule_selectors(block) & global_selectors:
                conflicts.setdefault(selector, set()).add(path.name)
    return conflicts


# ===========================================================================
# UI-01 (1) get_css() 구조 계약 — 오늘 통과해야 한다
# ===========================================================================

def test_ui01_get_css_가_style_태그로_감싸이고_중괄호가_균형이다():
    """UI-01: get_css() 반환이 <style> 래핑이고 중괄호(brace)가 균형임을 고정한다.

    Streamlit 은 이 문자열을 검증 없이 DOM 에 주입한다. 여는/닫는 중괄호가
    어긋나면 뒤쪽 규칙이 통째로 무시되는데 화면상으로는 조용히 깨진다.
    """
    css = get_css()
    assert isinstance(css, str) and css.strip(), "get_css() 가 빈 문자열을 반환했다"

    stripped = css.strip()
    assert stripped.startswith("<style>"), f"'<style>' 로 시작하지 않는다: {stripped[:30]!r}"
    assert stripped.endswith("</style>"), f"'</style>' 로 끝나지 않는다: {stripped[-30:]!r}"
    assert stripped.count("<style>") == 1, "<style> 태그가 중첩되어 있다"
    assert stripped.count("</style>") == 1, "</style> 태그가 중첩되어 있다"

    body = stripped[len("<style>"): -len("</style>")]
    opens, closes = body.count("{"), body.count("}")
    assert opens == closes, f"중괄호 불균형: '{{' {opens}개 vs '}}' {closes}개"

    # 중첩 깊이가 음수로 내려가면(닫기가 먼저 오면) 파서가 규칙을 버린다.
    depth = 0
    for index, char in enumerate(body):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            assert depth >= 0, f"{index}번째 문자에서 '}}' 가 먼저 닫혔다"
    assert depth == 0


def test_ui01_컴포넌트가_실제로_ir_클래스를_사용한다():
    """UI-01: 이 파일의 정적 분석이 실제 클래스를 잡고 있는지 자기 점검한다.

    추출 정규식이 조용히 0개를 잡으면 아래 D10/D09 테스트가 무의미해지므로
    최소 개수와 대표 클래스 존재를 함께 고정한다.
    """
    used = _used_ir_classes()
    assert len(used) >= 30, f"ir- 클래스 추출이 비정상적으로 적다: {len(used)}개"
    assert "ir-toolbar" in used, "ir-toolbar 를 찾지 못했다 — 추출 정규식을 확인하라"
    assert "ir-toolbar" in _defined_ir_classes(), "styles.py 에서 .ir-toolbar 를 찾지 못했다"

    assert len(_defined_ir_classes()) >= 20, "정의된 ir- 셀렉터 추출이 비정상적으로 적다"


# ===========================================================================
# UI-01 (2) D10 — 미정의 클래스 (확정 결함)
# ===========================================================================

@pytest.mark.xfail(
    strict=True, reason="D10: toolbar 하위 클래스 10개가 어디에도 정의되지 않음"
)
def test_ui01_사용하는_모든_ir_클래스가_어딘가에_정의되어_있다():
    """UI-01/D10: 컴포넌트가 쓰는 ir- 클래스 중 미정의가 0개여야 한다(정답 단언).

    현재 12개가 미정의다. 10개는 render_toolbar 가 내보내는 ir-toolbar-*
    하위 요소이고(styles.py 는 컨테이너 .ir-toolbar 만 정의한다),
    나머지 2개(ir-section-title, ir-stat-banner)는 research.py 가 쓰는데
    styles.py 에도 인라인 <style> 에도 없다. 모두 스타일 없이 렌더된다.
    """
    undefined = _undefined_ir_classes()
    detail = "\n".join(
        f"  - {name}  (사용: {', '.join(sorted(files))})"
        for name, files in sorted(undefined.items())
    )
    assert undefined == {}, (
        f"어디에도 정의되지 않은 ir- 클래스 {len(undefined)}개:\n{detail}"
    )


# ===========================================================================
# UI-01 (3) D09 — 인라인 CSS 충돌 (확정 결함)
# ===========================================================================

@pytest.mark.xfail(
    strict=True, reason="D09: gpt_section 인라인 CSS 가 styles.py 와 7개 충돌"
)
def test_ui01_인라인_style_셀렉터가_styles_py_와_충돌하지_않는다():
    """UI-01/D09: 인라인 <style> 셀렉터와 styles.py 셀렉터의 교집합이 공집합이어야 한다.

    같은 셀렉터가 두 곳에서 정의되면 최종 스타일이 주입 순서(st.markdown 호출
    순서)에 좌우된다. Streamlit 은 rerun 마다 DOM 을 다시 만들므로 이 순서가
    보장되지 않고, 결국 디자인이 실행 시점에 따라 달라진다.
    """
    conflicts = _inline_vs_styles_conflicts()
    detail = "\n".join(
        f"  - {selector}  (인라인 정의: {', '.join(sorted(files))})"
        for selector, files in sorted(conflicts.items())
    )
    assert conflicts == {}, (
        f"styles.py 와 중복 정의된 인라인 셀렉터 {len(conflicts)}개:\n{detail}"
    )
