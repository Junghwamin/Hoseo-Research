# ============================================================================
# Copyright (c) 2026 정화민 (Junghwamin)
# All rights reserved.
#
# This file is part of a personal research analysis portal by 정화민 (Junghwamin).
# Licensed under the PolyForm Noncommercial License 1.0.0.
# See the LICENSE file in the project root, or visit:
#     https://polyformproject.org/licenses/noncommercial/1.0.0
#
# Commercial use is strictly prohibited without prior written consent.
# Repository: https://github.com/Junghwamin/Hoseo-Research
# HOSEO-RESEARCH-FINGERPRINT: do not remove this line (used for provenance tracking)
# ============================================================================

"""
사이드바 컴포넌트 — Amplitude 스타일 좌측 네비게이션

앱 전체 모듈 선택 및 워크플로우 단계 이동을 담당한다.
app.py의 session_state 변경은 이 함수의 반환값을 통해 위임 처리한다.
"""

from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# 내부 상수
# ---------------------------------------------------------------------------
_MODULES: list[tuple[str, str, str, bool]] = [
    ("🏠", "홈", "home", False),
    ("📊", "연구실적", "research", False),
    ("📈", "교육비환원율", "education_cost", True),
    ("💼", "취업률", "employment", True),
]

_STEPS: list[str] = [
    "데이터 설정",
    "통계 확인",
    "그래프 검토",
    "GPT 서술",
    "보고서 생성",
]


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def render_sidebar(
    current_module: str,
    current_step: int,
    max_step: int,
    api_key_set: bool,
) -> tuple[str, int | None]:
    """사이드바를 렌더링하고 사용자 선택 결과를 반환한다.

    Amplitude 스타일 좌측 네비게이션을 구현한다.
    모듈 클릭 또는 단계 클릭 시 해당 값을 반환하여
    app.py에서 session_state를 업데이트할 수 있도록 한다.

    Args:
        current_module: 현재 선택된 모듈
            ("home", "research", "education_cost", "employment")
        current_step: 현재 워크플로우 단계 (1~5, home이면 0, 1-indexed)
        max_step: 완료된 최대 단계 — 이 값 이하의 단계만 클릭 허용 (1-indexed)
        api_key_set: OpenAI API Key 설정 여부

    Returns:
        (selected_module, selected_step) 튜플.
        - selected_module: 사용자가 클릭한 모듈 문자열 (변경 없으면 current_module)
        - selected_step: 사용자가 클릭한 단계 번호 (1-indexed).
            변경 없으면 None.

    Note:
        - disabled 모듈(준비 중)은 st.button(disabled=True)로 클릭 차단
        - 단계 버튼은 i+1 <= max_step 일 때만 활성화 (i는 0-indexed)
        - CSS 스타일은 app.py의 전역 CSS에서 처리; 여기선 data-* 클래스만 삽입
    """
    selected_module: str = current_module
    selected_step: int | None = None

    with st.sidebar:
        # ── 1. 앱 로고 + 이름 ───────────────────────────────────────────────
        st.markdown(
            """
            <div class="sidebar-logo">
                <div class="sidebar-logo-icon">📊</div>
                <div class="sidebar-logo-text">
                    <div class="sidebar-app-name">IR 분석 포털</div>
                    <div class="sidebar-app-sub">정화민 (Junghwamin)</div>
                </div>
            </div>
            <style>
            .sidebar-logo {
                display: flex;
                align-items: center;
                gap: 0.625rem;
                padding: 0.75rem 0 1rem 0;
                margin-bottom: 0.25rem;
            }
            .sidebar-logo-icon {
                font-size: 1.5rem;
                line-height: 1;
            }
            .sidebar-logo-text {
                display: flex;
                flex-direction: column;
            }
            .sidebar-app-name {
                font-size: 0.9375rem;
                font-weight: 700;
                color: #1a56db !important;
                letter-spacing: -0.02em;
                line-height: 1.2;
            }
            .sidebar-app-sub {
                font-size: 0.6875rem;
                color: #71717A !important;
                margin-top: 0.125rem;
                letter-spacing: -0.01em;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            '<hr style="margin:0 0 1rem 0; border:none; border-top:1px solid #E4E4E7;">',
            unsafe_allow_html=True,
        )

        # ── 2. 모듈 네비게이션 ──────────────────────────────────────────────
        st.markdown(
            '<div class="sidebar-section-label">분석 모듈</div>'
            '<style>'
            '.sidebar-section-label {'
            '  font-size: 0.6875rem;'
            '  font-weight: 600;'
            '  color: #A1A1AA !important;'
            '  text-transform: uppercase;'
            '  letter-spacing: 0.06em;'
            '  margin-bottom: 0.375rem;'
            '  padding-left: 0.125rem;'
            '}'
            '</style>',
            unsafe_allow_html=True,
        )

        for icon, label, module_id, is_disabled in _MODULES:
            is_active = (module_id == current_module)
            _render_module_item(
                icon=icon,
                label=label,
                module_id=module_id,
                is_active=is_active,
                is_disabled=is_disabled,
            )

        # 클릭 감지: on_click 콜백이 설정한 플래그 확인
        clicked_mod = st.session_state.pop("_nav_module_clicked", None)
        if clicked_mod and clicked_mod != current_module:
            selected_module = clicked_mod

        # ── 3. 워크플로우 단계 (home 모듈이 아닐 때만 표시) ────────────────
        if current_module != "home":
            st.markdown(
                '<hr style="margin:0.75rem 0; border:none; border-top:1px solid #E4E4E7;">'
                '<div class="sidebar-section-label">워크플로우</div>',
                unsafe_allow_html=True,
            )
            for i, step_label in enumerate(_STEPS):
                step_num = i + 1  # 1-indexed
                is_current = (step_num == current_step)
                is_done = (step_num < current_step)
                is_clickable = (step_num <= max_step)

                _render_step_item(
                    index=i,
                    label=step_label,
                    is_current=is_current,
                    is_done=is_done,
                    is_clickable=is_clickable,
                )

            # 단계 클릭 감지
            clicked_step = st.session_state.pop("_nav_step_clicked", None)
            if clicked_step is not None and clicked_step != current_step:
                selected_step = clicked_step

        # ── 4. API Key 상태 + 설정 영역 ────────────────────────────────────
        st.markdown(
            '<hr style="margin:0.75rem 0 0.5rem 0; border:none; border-top:1px solid #E4E4E7;">',
            unsafe_allow_html=True,
        )
        _render_api_key_section(api_key_set=api_key_set)

        # ── 5. 하단 영역 ────────────────────────────────────────────────────
        st.markdown(
            '<hr style="margin:0.5rem 0; border:none; border-top:1px solid #E4E4E7;">',
            unsafe_allow_html=True,
        )
        _render_footer()
        # 플래그를 소비하지 않고 들여다보기만 한다.
        # 여기서 pop 하면 같은 run 안에서 app.py 의 리셋 블록이 항상 False 를
        # 받아 죽은 코드가 된다(리셋 버튼이 홈 이동만 하던 원인).
        # 소비는 app.py 가 한다.
        if st.session_state.get("sidebar_reset_clicked", False):
            selected_module = "home"
            selected_step = None

    return selected_module, selected_step


# ---------------------------------------------------------------------------
# 내부 헬퍼 함수
# ---------------------------------------------------------------------------

def _render_module_item(
    icon: str,
    label: str,
    module_id: str,
    is_active: bool,
    is_disabled: bool,
) -> None:
    """모듈 네비게이션 항목 한 줄을 렌더링한다.

    활성 모듈은 HTML 강조 배경으로 표시하고,
    비활성(disabled) 모듈은 "준비 중" 뱃지와 함께 클릭 불가 버튼으로 표시한다.

    Args:
        icon: 유니코드 이모지 아이콘
        label: 사용자에게 보일 모듈명 (한국어)
        module_id: 내부 모듈 식별자 문자열
        is_active: 현재 선택된 모듈인지 여부
        is_disabled: 아직 구현되지 않은 준비 중 모듈인지 여부

    Note:
        - is_active=True 이면 HTML div로 하이라이트 렌더링 (버튼 없음)
        - is_disabled=True 이면 st.button(disabled=True) + "준비 중" 뱃지
        - 클릭 감지는 session_state 키 f"sidebar_mod_{module_id}" 로 처리
    """
    badge_html = (
        '<span style="'
        "font-size:0.6rem; font-weight:600; color:#D97706 !important;"
        "background:#FFFBEB; border:1px solid #FDE68A; border-radius:9999px;"
        'padding:1px 6px; margin-left:6px; vertical-align:middle;'
        '">준비 중</span>'
        if is_disabled
        else ""
    )

    if is_active:
        # 활성: HTML div 강조 (버튼 없음 — 클릭 의미 없음)
        st.markdown(
            f"""
            <div class="sidebar-nav-active">
                <span class="sidebar-nav-icon">{icon}</span>
                <span class="sidebar-nav-label">{label}</span>
                {badge_html}
            </div>
            <style>
            .sidebar-nav-active {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.4rem 0.5rem;
                border-radius: 0.375rem;
                background: #e8f0fe;
                margin-bottom: 0.125rem;
                font-size: 0.875rem;
                font-weight: 600;
                color: #1a56db !important;
                cursor: default;
            }}
            .sidebar-nav-icon {{ font-size: 0.9rem; }}
            .sidebar-nav-label {{ color: #1a56db !important; }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    elif is_disabled:
        # 비활성(준비 중): 버튼 disabled=True
        col_btn, col_badge = st.columns([3, 1], gap="small")
        with col_btn:
            st.button(
                f"{icon}  {label}",
                key=f"sidebar_mod_{module_id}",
                disabled=True,
                use_container_width=True,
            )
        with col_badge:
            st.markdown(
                '<div style="padding-top:0.45rem;">'
                '<span style="'
                "font-size:0.625rem; font-weight:600;"
                "color:#D97706 !important;"
                "background:#FFFBEB; border:1px solid #FDE68A;"
                "border-radius:9999px; padding:2px 6px;"
                '">준비 중</span></div>',
                unsafe_allow_html=True,
            )
    else:
        # 일반 클릭 가능 모듈 — on_click 콜백으로 안전하게 클릭 감지
        st.button(
            f"{icon}  {label}",
            key=f"sidebar_mod_{module_id}",
            use_container_width=True,
            on_click=lambda mid=module_id: st.session_state.__setitem__(
                "_nav_module_clicked", mid
            ),
        )


def _render_step_item(
    index: int,
    label: str,
    is_current: bool,
    is_done: bool,
    is_clickable: bool,
) -> bool:
    """워크플로우 단계 항목 한 줄을 렌더링하고 클릭 여부를 반환한다.

    단계 상태에 따라 세 가지 시각 스타일을 적용한다:
      - done (완료): ✓ 아이콘, zinc-500 텍스트, 클릭 가능
      - active (현재): ▶ 아이콘, zinc-950 볼드 텍스트
      - future (미래): 숫자 아이콘, zinc-400 텍스트, 클릭 불가

    Args:
        index: 단계의 0-based 인덱스
        label: 단계 이름 (한국어)
        is_current: 현재 진행 중인 단계인지 여부
        is_done: 이미 완료한 단계인지 여부
        is_clickable: 클릭 허용 여부 (max_step 이하 단계)

    Returns:
        True이면 이 단계 버튼이 클릭됨, False이면 클릭 없음

    Note:
        - is_done=True and is_clickable=True → 완료된 단계로 돌아가기 허용
        - is_current=True → 클릭 불필요 (현재 위치이므로 반환 False)
        - is_done/is_current 모두 False (미래) → disabled 버튼
    """
    step_num = index + 1  # 표시용 1-indexed 번호

    if is_done:
        icon_html = (
            '<span style="color:#71717A !important; font-size:0.75rem;">✓</span>'
        )
        label_style = "color:#71717A !important; font-size:0.8125rem;"
    elif is_current:
        icon_html = (
            '<span style="color:#1a56db !important; font-size:0.75rem;">▶</span>'
        )
        label_style = "color:#1a56db !important; font-weight:700; font-size:0.8125rem;"
    else:
        icon_html = (
            f'<span style="color:#A1A1AA !important; font-size:0.75rem;">'
            f"{step_num}"
            f"</span>"
        )
        label_style = "color:#A1A1AA !important; font-size:0.8125rem;"

    if is_current:
        # 현재 단계: HTML로만 표시 (버튼 불필요)
        st.markdown(
            f"""
            <div style="
                display:flex; align-items:center; gap:0.5rem;
                padding:0.35rem 0.5rem; border-radius:0.375rem;
                background:#e8f0fe; margin-bottom:0.125rem;
            ">
                {icon_html}
                <span style="{label_style}">{label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return False

    if not is_clickable:
        # 미래 단계: disabled 버튼
        st.button(
            f"  {step_num}  {label}",
            key=f"sidebar_step_{index}",
            disabled=True,
            use_container_width=True,
        )
        return False

    # 완료 단계 (클릭 가능): on_click 콜백으로 안전하게 클릭 감지
    st.button(
        f"  ✓  {label}",
        key=f"sidebar_step_{index}",
        use_container_width=True,
        on_click=lambda sn=step_num: st.session_state.__setitem__(
            "_nav_step_clicked", sn
        ),
    )
    return False  # 콜백이 플래그 설정, 반환값 사용 안 함


def _render_api_key_section(api_key_set: bool) -> None:
    """API Key 상태 표시 및 [변경] 버튼을 렌더링한다.

    API Key 설정 여부에 따라 상태 뱃지 색상을 달리 표시한다.
    [변경] 버튼 클릭 시 session_state["sidebar_api_change"] = True 를 설정하여
    app.py에서 API Key 입력 다이얼로그를 열 수 있도록 한다.

    Args:
        api_key_set: True이면 API Key가 이미 설정됨, False이면 미설정
    """
    if api_key_set:
        status_html = (
            '<span style="'
            "font-size:0.75rem; color:#16A34A !important;"
            'font-weight:600;">✅ 설정됨</span>'
        )
    else:
        status_html = (
            '<span style="'
            "font-size:0.75rem; color:#D97706 !important;"
            'font-weight:600;">⚠ 미설정</span>'
        )

    st.markdown(
        f"""
        <div style="
            display:flex; align-items:center; justify-content:space-between;
            padding:0.375rem 0.25rem; margin-bottom:0.25rem;
        ">
            <span style="font-size:0.8125rem; color:#3F3F46 !important;">
                🔑 API Key &nbsp; {status_html}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("변경", key="sidebar_api_change_btn", use_container_width=False):
        st.session_state["sidebar_api_change"] = True


def _render_footer() -> None:
    """사이드바 하단 영역 — '처음부터 다시' 버튼과 버전 정보를 렌더링한다.

    '처음부터 다시' 버튼 클릭 시 session_state["sidebar_reset_clicked"] = True를
    설정하여 render_sidebar() 반환 시 selected_module = "home"으로 처리한다.

    Note:
        버전 문자열은 이 파일 내 상수로 고정한다.
        향후 config.py에 APP_VERSION 상수를 추가하면 그 값을 참조한다.
    """
    if st.button(
        "🔄  처음부터 다시",
        key="sidebar_reset_btn",
        use_container_width=True,
    ):
        st.session_state["sidebar_reset_clicked"] = True

    st.markdown(
        '<div style="'
        "text-align:center; margin-top:0.75rem;"
        "font-size:0.6875rem; color:#A1A1AA !important;"
        'letter-spacing:-0.01em;">'
        "v5.0 · GPT-4o"
        "</div>",
        unsafe_allow_html=True,
    )
