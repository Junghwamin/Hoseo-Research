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
호서대학교 정화민 - 연구실적 분석 포털 v5.0

Amplitude-Inspired 디자인 시스템.
메인탭 구조로 향후 다른 분석 모듈(교육비환원율, 취업률 등) 확장 가능.

실행 방법:
    streamlit run report_app/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Streamlit Cloud에서 report_app 패키지를 찾을 수 있도록 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dotenv import load_dotenv, set_key

from report_app.config import UNIVERSITY, IS_CLOUD

# 컴포넌트
from report_app.components.styles import get_css
from report_app.components.sidebar import render_sidebar
from report_app.components.toolbar import render_toolbar

# 페이지
from report_app.pages.home import render_home
from report_app.pages.research import _go, render_research, reset_analysis_state
from report_app.pages.settings import render_settings


# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------
_ENV_PATH = Path.cwd() / ".env"

# ---------------------------------------------------------------------------
# .env 로드
# ---------------------------------------------------------------------------
load_dotenv(_ENV_PATH)


# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"{UNIVERSITY} IR 분석 포털",
    page_icon="📊",
    layout="wide",
)


# ---------------------------------------------------------------------------
# CSS 디자인 시스템 적용
# ---------------------------------------------------------------------------
st.markdown(get_css(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# API Key 탐색 (secrets > .env > 빈 문자열)
# ---------------------------------------------------------------------------
def _get_api_key() -> str:
    """API Key를 우선순위에 따라 탐색한다: secrets > .env > 빈 문자열."""
    try:
        key = st.secrets["OPENAI_API_KEY"]
        if key and key.startswith("sk-") and "여기에" not in key:
            return key
    except (FileNotFoundError, KeyError):
        pass
    key = os.getenv("OPENAI_API_KEY", "")
    if key and key.startswith("sk-") and "여기에" not in key:
        return key
    return ""


# ---------------------------------------------------------------------------
# Session State 초기화
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "module": "home",
    "step": 1,
    "max_step": 1,
    "national_df": None,
    "regional_df": None,
    "selected_year": None,
    "hoseo_trend": None,
    "averages": None,
    "rank_changes": None,
    "yoy_changes": None,
    "compare_data": None,
    "charts": {},
    "narrative_trend": "",
    "narrative_comparison": "",
    "narrative_regional": "",
    "narrative_yoy": "",
    "api_key": _get_api_key(),
    "report_buf": None,
    "data_source": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.api_key.startswith("sk-여기에"):
    st.session_state.api_key = ""


# ---------------------------------------------------------------------------
# 헬퍼: API Key 저장
# ---------------------------------------------------------------------------
def _save_api_key(key: str):
    """API Key를 session_state에 저장하고, 로컬 환경이면 .env에도 영구 저장한다."""
    if not IS_CLOUD:
        _ENV_PATH.touch(exist_ok=True)
        set_key(str(_ENV_PATH), "OPENAI_API_KEY", key)
    st.session_state.api_key = key


# ---------------------------------------------------------------------------
# API Key 변경 다이얼로그
# ---------------------------------------------------------------------------
@st.dialog("API Key 설정")
def _api_key_dialog():
    """API Key 입력/저장 모달 다이얼로그."""
    st.markdown("OpenAI API Key를 입력하세요.")

    key_input = st.text_input(
        "API Key",
        value=st.session_state.api_key,
        type="password",
        placeholder="sk-...",
        key="_dialog_api_key",
    )

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("저장", type="primary", use_container_width=True):
            if key_input.startswith("sk-") and len(key_input) > 20:
                _save_api_key(key_input)
                st.rerun()
            else:
                st.error("올바른 키를 입력하세요.")
    with col_cancel:
        if st.button("취소", use_container_width=True):
            st.rerun()


# ===========================================================================
# 사이드바 렌더링
# ===========================================================================
cur_module = st.session_state.module
cur_step = st.session_state.step
max_step = st.session_state.get("max_step", 1)

selected_module, selected_step = render_sidebar(
    current_module=cur_module,
    current_step=cur_step,
    max_step=max_step,
    api_key_set=bool(st.session_state.api_key),
)

# API Key 변경 요청 처리
if st.session_state.pop("sidebar_api_change", False):
    _api_key_dialog()

# 리셋 처리
# 사이드바는 플래그를 들여다보기만 하고, 소비와 실제 리셋은 여기서 한다.
if st.session_state.pop("sidebar_reset_clicked", False):
    reset_analysis_state()
    st.session_state.module = "home"
    st.session_state.step = 0
    st.rerun()

# 모듈 변경 처리
if selected_module != cur_module:
    st.session_state.module = selected_module
    if selected_module == "home":
        st.session_state.step = 0
    elif selected_module == "research":
        st.session_state.step = 1
    st.rerun()

# 단계 변경 처리
# research 모듈에서는 _go() 를 거친다. 직접 대입하면 4단계 text_area 의
# GPT 서술이 백업되지 않아 사이드바로 이동할 때마다 사라진다.
if selected_step is not None and selected_step != cur_step:
    if st.session_state.get("module") == "research":
        _go(selected_step)
    else:
        st.session_state.step = selected_step
    st.rerun()


# ===========================================================================
# 상단 툴바 렌더링
# ===========================================================================
_MODULE_NAMES = {
    "home": "홈",
    "research": "전임교원 연구실적 분석",
    "education_cost": "교육비환원율",
    "employment": "취업률",
    "settings": "설정",
}
_STEP_NAMES = {
    1: "1단계: 데이터 설정",
    2: "2단계: 통계 확인",
    3: "3단계: 그래프 검토",
    4: "4단계: GPT 서술",
    5: "5단계: 보고서 생성",
}

module_display = _MODULE_NAMES.get(st.session_state.module, "")
step_display = _STEP_NAMES.get(st.session_state.step) if st.session_state.module == "research" else None

render_toolbar(module_display, step_display)


# ===========================================================================
# 메인 콘텐츠 라우팅
# ===========================================================================
current_module = st.session_state.module

if current_module == "home":
    home_result = render_home()
    if home_result:
        st.session_state.module = home_result
        st.session_state.step = 1
        st.rerun()

elif current_module == "research":
    # max_step 갱신을 render 앞에 둔다. 뒤에 두면 4단계의 API 키 게이트가
    # st.stop() 으로 스크립트를 끊을 때 갱신이 통째로 건너뛰어져
    # step=4 인데 max_step=1 이 되고, 사이드바로 되돌아올 수 없게 된다.
    if st.session_state.step > st.session_state.get("max_step", 1):
        st.session_state.max_step = st.session_state.step
    render_research(st.session_state.step)

elif current_module == "settings":
    render_settings()

else:
    st.info("이 분석 모듈은 준비 중입니다.")


# ===========================================================================
# 푸터
# ===========================================================================
st.markdown(f"""
<div class="ir-footer">
  {UNIVERSITY} · 분석 포털 v5.0 &nbsp;|&nbsp;
  Powered by GPT-4o &amp; Streamlit
</div>
""", unsafe_allow_html=True)
