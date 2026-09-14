# 호서대학교 정화민 - 연구실적 분석 포털

## 프로젝트 개요

전임교원 연구실적 데이터(대학알리미)를 자동으로 분석하고
GPT-4o + matplotlib + python-docx를 사용하여 Word 보고서를 자동 생성하는 Streamlit 앱.
정화민 (Junghwamin) 개인 프로젝트.

---

## 실행 방법

```bash
# 의존성 설치 (최초 1회)
pip install -r requirements.txt

# Streamlit 앱 실행 (프로젝트 루트에서 실행 필수)
cd "C:\Users\정화민\Desktop\Hoseo Reasearch\Hoseo-Research"
streamlit run report_app/app.py
```

브라우저에서 http://localhost:8501 접속.

---

## 테스트 (코드 수정 시 필수 준수)

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                       # 전체 (live 마커 제외)
```

**프로덕션 코드를 고쳤으면 반드시 `pytest -q` 를 돌리고 결과를 근거로 제시한다.
"고쳤습니다" 라는 보고만으로는 부족하다.**

### 이 스위트를 다룰 때 반드시 알아야 할 것

1. **`xfail_strict = true`** — 결함 잠금 테스트가 예상외로 통과하면 실행이
   FAILED 로 떨어진다. 버그가 아니라 설계다. 어떤 수정이 의도한 범위를 넘었다는
   신호이므로, 테스트를 고쳐서 통과시키지 말고 수정 범위를 다시 본다.
2. **테스트를 고쳐서 green 을 만드는 것은 실패다.** 잠금 테스트는 "고쳐진 뒤의
   올바른 동작" 을 단언한다. 지금 실패하는 것이 정상이다.
3. **완료 기준은 `failed 0` 이 아니다.** 결함을 고치면 그 결함의
   `@pytest.mark.characterization` 테스트는 반드시 깨진다. 올바른 기준은
   "모든 실패가 strict XPASS 아니면 낡은 characterization 이고, 그 밖은 0건".
4. `tests/conftest.py`, `pytest.ini`, `tests/fixtures/` 는 하네스다. 테스트를
   통과시키려고 이 파일들을 건드리면 스위트 전체가 거짓 통과한다.
   `tests/test_harness_guards.py` 가 이를 감시한다.
5. `report_app/config.py` 는 import 시 `Path.cwd()` 를 **1회** 평가한다. 그래서
   conftest 는 모듈 최상단에서 chdir 한다. 이 순서를 바꾸면 테스트가 실제
   `output/` 을 덮어쓴다.

### 알려진 함정

- `streamlit` 로거는 전부 `propagate=False` 라 pytest `caplog` 으로 잡히지 않는다.
  방출 지점 로거에 `caplog.handler` 를 직접 붙여야 한다.
- `xfail` 에 `raises=` 가 없으면 렌더 크래시가 XFAIL 로 흡수되어 결함 잠금이
  거짓으로 성립한다. 항상 `raises=` 를 명시한다.
- `scripts/smoke_test.py` 는 PostToolUse **훅**이다. stdin 으로 JSON 을 받아야
  실제로 동작하고, 그냥 실행하면 조용히 exit 0 한다(통과로 착각하기 쉽다).

검증 결과와 미해결 항목은 `docs/QA_REVIEW_REPORT.md` 에 있다.

---

## 전체 워크플로우 (앱 내 5단계)

```
1단계: 전처리·데이터 설정
  [🔧 원시 데이터 전처리] 탭
    → 대학알리미 xlsx 업로드 → Raw data/ 저장 → [⚙️ 전처리 실행]
    → output/CSV 자동 생성 후 데이터 로드
  [📂 전처리 결과 CSV 업로드] 탭
    → 이미 전처리된 CSV 2개 직접 업로드
  [📁 기존 output/ 폴더 사용] 탭
    → 기존 CSV 파일 바로 사용

2단계: 통계 확인
  → 요약 카드, 연도별 수치표, 비교군 표, 전년대비 증감 검토

3단계: 그래프 검토
  → 5종 차트 탭별 확인 (PNG 개별 저장 가능)

4단계: GPT 서술 생성 및 편집
  → 섹션별 [🤖 GPT 생성] 버튼 → text_area에서 직접 편집

5단계: 보고서 생성
  → [Word 보고서 생성] → [⬇️ 다운로드]
```

---

## 주요 파일 구조 및 역할

| 파일 | 역할 |
|------|------|
| `전임교원_연구실적_전처리.py` | Raw Excel → CSV 변환 (앱 내에서도 호출됨) |
| `report_app/config.py` | 대학명, 비교군, 경로, GPT 설정 상수 |
| `report_app/data_loader.py` | CSV 로드 + 통계 계산 6개 함수 |
| `report_app/chart_generator.py` | matplotlib 그래프 5종 → BytesIO 반환 |
| `report_app/gpt_reporter.py` | OpenAI API 호출, 섹션별 서술 4종 생성 |
| `report_app/report_builder.py` | python-docx Word 보고서 5개 섹션 조립 |
| `report_app/app.py` | Streamlit 메인 앱 (5단계 step-by-step) |
| `.env` | OPENAI_API_KEY 저장 (git 제외 대상) |
| `output/reports/` | 생성된 Word 파일 저장 위치 |
| `Raw data/` | 대학알리미 원본 xlsx 파일 저장 위치 |

---

## 데이터 구조

### `output/권역별_순위.csv` (현행 포맷)
```
연도, 학교명, 전임교원수, SCI/SCOPUS논문수, 1인당논문수, 권역명, 권역순위, 전국순위
```
6개 권역(수도권·강원권·충청권·호남권·영남권·제주권) 전체를 담는다.
다중 캠퍼스 대학은 권역마다 한 행씩 나타난다.

### `output/충청권_순위.csv` (레거시, 하위 호환용)
```
연도, 학교명, 전임교원수, SCI/SCOPUS논문수, 1인당논문수, 충청권순위, 전국순위
```
`data_loader._ensure_new_format()` 이 읽을 때 신형으로 변환한다.
새 코드는 권역별_순위.csv 를 쓸 것.

> **전국순위의 의미**: `config/universities.json` 에 등재된 대학만 순위에
> 참여한다. 2025년 기준 '대학교' 209개 중 134개교가 남고 이들은 전원 사립이다.
> 국립·공립·과기원은 제외된다. 따라서 '전국순위'는 **등재 사립 134개교 기준**이다.

### `output/전체_대학_데이터.csv`
```
연도, 학교명, 전임교원수, SCI/SCOPUS논문수, 1인당논문수, 전국순위
```

- 인코딩: UTF-8 with BOM (utf-8-sig)
- 연도 범위: 2023~2025 (전처리 실행 시 자동 갱신)
- Raw 파일명 규칙: 파일명에 연도 포함 필수 → `2024년_전임교원.xlsx`

---

## 비교 대학군 (config.py 에서 수정)

천안·아산 5개 대학:
- 순천향대학교, 선문대학교, 한서대학교, 나사렛대학교, **호서대학교**

---

## 환경 설정

### .env 파일 (사이드바에서 저장 가능)
```
OPENAI_API_KEY=sk-실제_API_키_입력
```
앱 사이드바에서 API Key 입력 후 [💾 저장] 클릭 시 .env에 자동 저장됨.

### GPT 설정 (config.py)
- 모델: GPT-4o (`GPT_MODEL`)
- max_tokens: 2000
- temperature: 0.4

---

## 생성 보고서 구조

| 섹션 | 내용 |
|------|------|
| 표지 | 대학명, 제목, 기준연도, 생성일 |
| 1. 연도별 추이 | GPT 서술 + 수치표 + 라인차트 |
| 2. 평균 비교 | GPT 서술 + 수평 바차트 |
| 3. 충청권 비교 | GPT 서술 + 막대차트 + 순위변화차트 |
| 4. 비교군 현황 | 5개교 비교표 + 막대차트 |
| 5. 전년대비 증감 | GPT 서술 + 증감 상위/하위 표 |

---

## 트러블슈팅

### 한글 폰트 깨짐 (matplotlib)
```python
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
```
Windows 기준. Linux 배포 시 `NanumGothic` 등으로 변경.

### CSV 인코딩 오류
- `pd.read_csv(..., encoding="utf-8-sig")` 사용 (BOM 처리)

### OpenAI API 오류
- GPT-4o 미사용 계정: `config.py`의 `GPT_MODEL = "gpt-4"` 로 변경

### Streamlit 실행 오류
- 반드시 프로젝트 루트(`Hoseo-Research/`)에서 실행해야 상대경로 정상 동작
  (`report_app/config.py:80` 이 import 시점에 `Path.cwd()` 를 1회 평가한다)

### CSS 적용 시 주의사항 (v3.0)
- Streamlit CSS 우선순위 때문에 `!important` 필수
- 사이드바 색상: `[data-testid="stSidebar"] *` 로 하위 전체 타겟
- 메트릭 카드: `[data-testid="stMetric"]`, `[data-testid="stMetricValue"]` 사용
- 버튼 종류 구분: `button[kind="primary"]` vs `:not([kind="primary"])`
- 탭 패널: `[data-baseweb="tab-panel"]` 로 탭 내용 배경색 변경 가능

### Streamlit text_area + GPT 버튼 연동 (중요)
- `key=`가 있는 text_area에 `value=`를 함께 쓰면 GPT 결과가 화면에 반영 안 됨
- 해결: text_area에 `key="narrative_*"` 만 사용, GPT 결과 저장 후 `st.rerun()` 호출
- narrative 키가 곧 text_area 위젯 키 → session_state 하나로 통합 관리

### 전처리 스크립트 앱 내 호출
- `importlib.util.spec_from_file_location` 으로 한글 파일명 동적 임포트
- `contextlib.redirect_stdout` 으로 전처리 로그를 앱 화면에 표시

---

## 메모리 시스템 (필수 준수)

이 프로젝트는 **컴포넌트별 메모리 파일 시스템**을 사용한다. 모든 작업에서 아래 규칙을 따를 것.

### 메모리 파일 위치
`~/.claude/projects/C--Users-----Desktop-Hoseo-Reasearch/memory/`

### 메모리 파일 목록
| 파일 | 내용 | 참조 시점 |
|------|------|-----------|
| `MEMORY.md` | 인덱스 + 전체 요약 | 항상 |
| `architecture.md` | 8-Layer 구조, 흐름도, 라우팅 | 구조 변경 시 |
| `components.md` | UI 컴포넌트 6개 상세 | UI 수정 시 |
| `data-pipeline.md` | 전처리→CSV→통계 흐름 | 데이터 수정 시 |
| `session-state.md` | session_state 키 전체 | 상태 버그 수정 시 |
| `design-patterns.md` | 패턴 7종 + anti-pattern | 리팩토링 시 |
| `modification-guide.md` | 안전/위험 수정 포인트 | **모든 수정 전 필독** |
| `gpt-prompts.md` | GPT 프롬프트 구조 | 서술 개선 시 |

### 작업 전 (필수)
1. `modification-guide.md`를 먼저 읽어 수정 영향 범위 파악
2. 수정 대상과 관련된 메모리 파일 읽기 (위 표 참조)
3. 기존 설계 패턴/컨벤션 확인 후 일관되게 구현

### 작업 후 (필수)
1. 수정한 파일과 관련된 메모리 파일 업데이트
2. `MEMORY.md`의 "최종 업데이트" 날짜 갱신
3. 새 파일 추가/구조 변경 시 → `architecture.md` 반드시 업데이트
4. 새 session_state 키 추가 시 → `session-state.md` 반드시 업데이트
5. 새 컴포넌트 추가 시 → `components.md` 반드시 업데이트

### 파일→메모리 매핑
```
app.py              → architecture.md, session-state.md
config.py           → architecture.md, data-pipeline.md, gpt-prompts.md
data_loader.py      → data-pipeline.md, session-state.md
chart_generator.py  → data-pipeline.md
gpt_reporter.py     → gpt-prompts.md
report_builder.py   → data-pipeline.md
components/*        → components.md
research.py         → architecture.md, session-state.md, design-patterns.md
home.py, settings.py → architecture.md
전처리 스크립트      → data-pipeline.md
```

### Stop 훅 자동 리마인더
작업 완료 시 `memory_update_reminder.py`가 자동 실행되어 업데이트 필요한 메모리 파일을 알려준다.
이 리마인더가 출력되면 반드시 해당 메모리 파일을 업데이트한 후 작업을 종료할 것.

---

## 향후 지표 추가 방법 (교육비환원율 등)

`report_app/indicators/` 폴더에 동일 인터페이스로 모듈 추가:
```python
# indicators/education_cost.py
def get_stats() -> dict: ...
def get_charts() -> dict[str, BytesIO]: ...
def get_narrative(client: OpenAI) -> dict[str, str]: ...
```
`app.py` 사이드바에 지표 선택 라디오버튼 추가 후 해당 모듈 호출.

---

## 작업 로그

| 날짜 | 내용 |
|------|------|
| 2026-02-23 | 초기 구현: report_app/ 전체 모듈 6개 파일 (config, data_loader, chart_generator, gpt_reporter, report_builder, app) |
| 2026-02-23 | app.py v2: 5단계 step-by-step 워크플로우로 전면 재설계, API Key .env 영구 저장, 데이터 파일 업로드 기능 |
| 2026-02-23 | 4단계 GPT 서술 버그 수정: text_area key 충돌 → st.rerun() 방식으로 변경 |
| 2026-02-23 | 1단계에 전처리 탭 추가: Raw xlsx 업로드 → 앱 내 전처리 실행 → CSV 자동 생성 |
| 2026-02-23 | 수정: `config.py` |
| 2026-02-23 | 신규 생성: `syntax_check.py` |
| 2026-02-23 | 신규 생성: `auto_pip_install.py` |
| 2026-02-23 | 신규 생성: `session_end_summary.py` |
| 2026-02-23 | 신규 생성: `import_check.py` |
| 2026-02-23 | 신규 생성: `dependency_check.py` |
| 2026-02-23 | 신규 생성: `smoke_test.py` |
| 2026-02-23 | 수정: `smoke_test.py` |
| 2026-02-23 | 신규 생성: `app.py` |
| 2026-02-23 | app.py v3.0: 전면 UI/UX 리디자인 — 딥블루 디자인 시스템, 헤더 배너, 원형 스텝 인디케이터, 사이드바 네이비 테마, 섹션 타이틀 카드, GPT 섹션 헤더+뱃지, 메트릭 카드 hover 효과 |
| 2026-02-23 | 신규 생성: `backup_on_edit.py` |
| 2026-02-23 | 수정: `log_change.py` |
| 2026-02-23 | 수정: `app.py` |
| 2026-03-02 | 수정: `전임교원_연구실적_전처리.py` |
| 2026-03-02 | 수정: `app.py` |
| 2026-03-02 | 수정: `chart_generator.py` |
| 2026-03-02 | 신규 생성: `build_windows.py` |
| 2026-03-02 | 신규 생성: `create_icon.py` |
| 2026-03-03 | 수정: `config.py` |
| 2026-03-03 | 수정: `app.py` |
| 2026-03-03 | 수정: `전임교원_연구실적_전처리.py` |
| 2026-03-04 | 수정: `build_windows.py` |
| 2026-03-07 | 수정: `config.py` |
| 2026-03-07 | 수정: `data_loader.py` |
| 2026-03-07 | 수정: `app.py` |
| 2026-03-07 | 수정: `전임교원_연구실적_전처리.py` |
| 2026-03-07 | 수정: `chart_generator.py` |
| 2026-03-07 | 신규 생성: `test_e2e.py` |
| 2026-03-08 | 신규 생성: `e2e_test_full.py` |
| 2026-03-08 | 수정: `chart_generator.py` |
| 2026-03-08 | 수정: `app.py` |
| 2026-03-08 | 신규 생성: `__init__.py` |
| 2026-03-08 | 신규 생성: `toolbar.py` |
| 2026-03-08 | 신규 생성: `metric_card.py` |
| 2026-03-08 | 신규 생성: `styles.py` |
| 2026-03-08 | 신규 생성: `chart_card.py` |
| 2026-03-08 | 신규 생성: `sidebar.py` |
| 2026-03-08 | 신규 생성: `gpt_section.py` |
| 2026-03-08 | 신규 생성: `home.py` |
| 2026-03-08 | 신규 생성: `settings.py` |
| 2026-03-08 | 신규 생성: `research.py` |
| 2026-03-08 | 신규 생성: `app.py` |
| 2026-03-08 | 수정: `sidebar.py` |
| 2026-03-08 | 수정: `research.py` |
| 2026-03-08 | 수정: `data_loader.py` |
| 2026-03-08 | 수정: `report_builder.py` |
| 2026-03-08 | 신규 생성: `gpt_reporter.py` |
| 2026-03-08 | 수정: `gpt_section.py` |
| 2026-03-09 | 수정: `styles.py` |
| 2026-03-09 | 수정: `sidebar.py` |
| 2026-03-09 | 수정: `toolbar.py` |
| 2026-03-09 | 수정: `home.py` |
| 2026-03-09 | 수정: `config.py` |
| 2026-03-09 | 수정: `전임교원_연구실적_전처리.py` |
| 2026-03-09 | 신규 생성: `data_loader.py` |
| 2026-03-09 | 수정: `chart_generator.py` |
| 2026-03-09 | 수정: `gpt_reporter.py` |
| 2026-03-09 | 수정: `report_builder.py` |
| 2026-03-09 | 수정: `research.py` |
| 2026-03-10 | 신규 생성: `memory_update_reminder.py` |
