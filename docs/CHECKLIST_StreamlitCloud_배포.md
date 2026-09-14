# Streamlit Cloud 배포 체크리스트

**프로젝트:** 호서대학교 IR센터 연구실적 분석 포털
**목표:** Streamlit Community Cloud 배포
**예상 소요:** 약 4~5시간

---

## Phase 1: 사전 준비 (30분)

### 환경 설정 파일 생성

- [ ] **[P0]** `packages.txt` 생성 (프로젝트 루트) — 5분
  ```
  fonts-nanum
  fonts-nanum-coding
  fonts-nanum-extra
  ```

- [ ] **[P0]** `.streamlit/secrets.toml` 생성 (로컬 테스트용) — 5분
  ```toml
  # app.py 는 평면 키를 읽는다. [openai] 테이블로 넣으면
  # Streamlit 이 환경변수로 내보내지 않아 폴백까지 실패한다.
  OPENAI_API_KEY = "sk-실제키값"
  ```

- [ ] **[P0]** `.gitignore` 업데이트 — 5분
  - `.streamlit/secrets.toml` 추가
  - `Raw data/` 확인
  - `output/` 확인

- [ ] **[P0]** `requirements.txt` 검토 — 5분
  - 현재 의존성 Debian Linux 호환 확인
  - `python-dotenv` 유지 (로컬 호환성)

---

## Phase 2: 코드 수정 (3시간)

### P0 - 배포 필수 (이것 없으면 앱이 안 돌아감)

- [ ] **[P0]** `report_app/config.py` — 경로 설정 변경 (15분)
  - Line 30: `Path.cwd()` -> `Path(__file__).parent.parent`로 변경
  - 클라우드에서 CWD가 보장되지 않는 문제 해결

- [ ] **[P0]** `report_app/chart_generator.py` — 폰트 캐시 갱신 (15분)
  - Line 33 부근 Linux 분기에 폰트 캐시 리빌드 코드 추가:
    ```python
    _fm._load_fontmanager(try_read_cache=False)
    ```
  - 이 코드 없으면 NanumGothic 설치되어도 인식 못함

- [ ] **[P0]** `report_app/app.py` — API Key 로드 방식 전환 (30분)
  - Line 50-55: `load_dotenv()` 유지하되, `st.secrets` 우선 조회 로직 추가
  - API Key 로드 우선순위:
    1. `st.session_state["api_key"]` (세션 입력)
    2. `st.secrets["OPENAI_API_KEY"]` (배포 환경, 평면 키)
    3. `os.getenv("OPENAI_API_KEY")` (로컬 .env 폴백)
  - Line 582-583: `.env` 저장 로직을 클라우드에서는 비활성화
    ```python
    IS_CLOUD = os.getenv("STREAMLIT_SHARING_MODE") is not None
    ```

### P1 - 기능 장애 방지

- [ ] **[P1]** `report_app/app.py` — 1단계 탭 구조 수정 (45분)
  - "기존 output/ 폴더 사용" 탭: 클라우드에서 비활성화 또는 제거
  - "원시 데이터 전처리" 탭: 디스크 저장 제거, 메모리 내 처리로 전환
    - Line 756: `_RAW_DIR` 디렉토리 생성 -> session_state BytesIO 저장
    - Line 769: `_RAW_DIR.mkdir()` 제거
  - 전처리 결과를 `session_state`에 직접 DataFrame으로 보관

- [ ] **[P1]** `전임교원_연구실적_전처리.py` — 인메모리 전처리 함수 추가 (45분)
  - 기존 `main()` 유지 (로컬 CLI 호환)
  - 신규 함수 추가:
    ```python
    def process_in_memory(
        uploaded_files: dict[str, BytesIO],
        config_dir: Path
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """디스크 저장 없이 메모리에서 전처리"""
    ```

- [ ] **[P1]** `report_app/data_loader.py` — 유연한 입력 지원 (15분)
  - `load_all_data()` 함수에 DataFrame 직접 수신 옵션 추가
  - 또는 클라우드에서는 이 함수를 우회하고 직접 업로드된 DataFrame 사용

- [ ] **[P1]** `report_app/app.py` — Word 보고서 저장 경로 (10분)
  - Line 1271: `REPORT_DIR.mkdir()` → try/except 또는 조건 분기
  - `build_report()`는 이미 BytesIO 반환하므로 디스크 저장 불필요

### P2 - UX 개선

- [ ] **[P2]** `report_app/app.py` — CSS 폰트 폴백 (5분)
  - Line 103: `font-family: 'Malgun Gothic'`
  - 변경: `font-family: 'Malgun Gothic', 'NanumGothic', sans-serif`

- [ ] **[P2]** 세션 만료 경고 안내 추가 (10분)
  - 클라우드에서 세션 끊길 시 데이터 소실 안내 메시지
  - 전처리 직후 "CSV 다운로드" 버튼 제공

- [ ] **[P2]** Word 보고서 폰트 안내 (5분)
  - 다운로드 시 "맑은 고딕 폰트가 설치된 환경에서 열어야 정상 표시됩니다" 안내

---

## Phase 3: 로컬 테스트 (30분)

- [ ] `.streamlit/secrets.toml` 기반 API Key 로드 테스트
- [ ] `.env` 없이 앱 실행 → `st.secrets` 폴백 동작 확인
- [ ] CSV 업로드 → 통계 → 차트 → GPT → Word 전체 흐름 테스트
- [ ] "기존 output/ 폴더" 탭 제거/비활성화 확인
- [ ] `config.py` 경로 변경 후 로컬에서도 정상 동작 확인

---

## Phase 4: 배포 (15분)

- [ ] **GitHub 푸시**
  - `git add` 대상 파일 확인 (secrets.toml 제외!)
  - 커밋 메시지: `feat: Streamlit Cloud 배포 대응`
  - `git push origin main`

- [ ] **Streamlit Cloud 설정**
  1. [share.streamlit.io](https://share.streamlit.io) 접속
  2. GitHub 계정 연동 (Junghwamin)
  3. Repository: `Junghwamin/Hoseo-Research`
  4. Branch: `main`
  5. Main file path: `report_app/app.py`
  6. Python version: `3.11`

- [ ] **Secrets 설정** (Streamlit Cloud 대시보드)
  - Settings > Secrets
  ```toml
  OPENAI_API_KEY = "sk-실제키값"
  ```

---

## Phase 5: 배포 후 검증 (30분)

### 기능 테스트

- [ ] 앱 URL 접속 가능 확인
- [ ] Cold start 시간 확인 (30초 이내)
- [ ] **1단계**: CSV 파일 업로드 정상 동작
- [ ] **1단계**: Raw xlsx 업로드 + 전처리 정상 동작
- [ ] **2단계**: 통계 카드 및 수치표 정상 표시
- [ ] **3단계**: 5종 차트 한글 정상 렌더링
  - [ ] 추이 라인차트
  - [ ] 충청권 막대차트
  - [ ] 평균 비교 바차트
  - [ ] 순위 변화 차트
  - [ ] 비교군 막대차트
- [ ] **4단계**: GPT 서술 생성 (st.secrets API Key 사용)
- [ ] **4단계**: 서술 텍스트 편집 정상 동작
- [ ] **5단계**: Word 보고서 생성 및 다운로드
- [ ] 다운로드된 Word 파일 Windows에서 정상 열림

### 비기능 테스트

- [ ] 메모리 사용량 모니터링 (1GB 이내)
- [ ] GitHub main 브랜치 푸시 후 자동 재배포 확인
- [ ] HTTPS 접속 확인

---

## 기술 참고 사항

### API Key 로드 코드 패턴

```python
def _get_api_key():
    """우선순위: session_state > st.secrets > .env"""
    if st.session_state.get("api_key"):
        return st.session_state.api_key
    try:
        return st.secrets["OPENAI_API_KEY"]
    except (KeyError, FileNotFoundError):
        return os.getenv("OPENAI_API_KEY", "")
```

### 클라우드 환경 감지

```python
import os
IS_CLOUD = os.getenv("STREAMLIT_SHARING_MODE") is not None
```

### 폰트 캐시 갱신 (chart_generator.py)

```python
import platform as _platform
import matplotlib.font_manager as _fm

def _setup_korean_font():
    system = _platform.system()
    if system == "Windows":
        font_name = "Malgun Gothic"
    elif system == "Darwin":
        font_name = "Apple SD Gothic Neo"
    else:  # Linux (Streamlit Cloud)
        _fm._load_fontmanager(try_read_cache=False)  # 캐시 강제 재빌드
        font_name = "NanumGothic"
    matplotlib.rcParams["font.family"] = font_name
    matplotlib.rcParams["axes.unicode_minus"] = False
```

### secrets.toml 구조

```toml
# .streamlit/secrets.toml (로컬 개발용 - .gitignore에 추가!)
# 최상위 평면 키여야 한다. app.py 는 st.secrets["OPENAI_API_KEY"] 를 읽는다.
OPENAI_API_KEY = "sk-..."
```

### packages.txt

```
fonts-nanum
fonts-nanum-coding
fonts-nanum-extra
```
