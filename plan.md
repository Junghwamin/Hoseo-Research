# Hoseo-Research 연구실적 분석 포털: 코드 리뷰 + 컴포넌트 단위 검증(QA) 계획

## 0. 요약 (Executive Summary)

- **현황**: 자동 테스트 0개. 기존 `e2e_test_full.py`는 옛 API(`충청권평균`, `충청권순위`)를 단언해 항상 실패하고, `scripts/smoke_test.py`는 항상 NameError로 끝난다. CI에 테스트 job이 없다.
- **이번 세션에서 한 일(읽기 전용)**: 에이전트 9개로 8계층 컴포넌트 지도·세션 상태 키 40개·결함 후보 90여 건을 확보하고, 상위 16건을 재현/반박 2관점(에이전트 32개)으로 검증해 **15건 확정, 1건 부분 확정(V15)**. 초안을 3관점(완전성·실행가능성·의도)으로 비평받아 반영했다.
- **확정 결함의 뿌리 3개**: (1) ETL 입력 가정 오류(2017 포맷은 '남' 열만 집계, 등재 대학이 사립 134개교뿐) → 추적 중인 `output/*.csv` 자체가 부정확. (2) "권역 미설정 + 리셋 경로 불일치"라는 세션 상태 설계 결함 → 잘못된 라벨, 크래시, GPT 서술 소실. (3) 레거시 파일명·컬럼이 UI·인스톨러 문자열에 하드코딩.
- **만들 것**: `tests/`(pytest: 단위·계약·실데이터 골든·AppTest·수동 체크리스트, 약 120 케이스) + 파일별 코드 리뷰 보고서 `docs/QA_REVIEW_REPORT.md`. 확정 결함은 **결함 잠금 테스트(xfail strict)** 로 먼저 고정한다.
- **승인 시 생기는 것**: 승인 직후 이 문서를 `Hoseo-Research/plan.md`로 저장(사용자 요청). 이어서 `tests/`, `pytest.ini`, `requirements-dev.txt`, `.venv-qa/`(gitignore, 약 300MB 다운로드), `docs/QA_REVIEW_REPORT.md`, `tests/manual/CHECKLIST.md`. **프로덕션 코드·`output/`·git 이력은 바뀌지 않는다**(Phase 4 별도 승인).

### 결정 완료 (2026-09-14 사용자 확답)

| # | 질문 | **결정** | 실행에 미치는 영향 |
|---|---|---|---|
| 1 | Cloud Python 버전 | `.venv-qa`를 **3.11**로 생성(기본값 채택). Cloud 버전이 3.12로 확인되면 Phase 5에서 CI만 교체 | Phase 0 |
| 2 | **V14 전국순위 의미** | **현행 유지 + 라벨 명시**. `universities.json`·순위 계산식은 손대지 않고, 앱 화면·Word 보고서·README·GPT 프롬프트에 "등재 사립 134개교 기준"임을 표기하고 제외 대학 수를 화면에 노출 | 기존 보고서와 수치 호환 유지. ETL-I05(국공립 0건 xfail)는 **삭제**하고 ETL-I04 특성화 + 라벨 테스트로 대체 |
| 3 | V01 수정 후 `output/*.csv` 재생성 | **재생성**(2017 행이 실제로 틀렸으므로 불가피). 골든 기준값 갱신, 재생성 전후 diff를 보고서에 첨부 | Phase 4에서 ETL-C02·ETL-I03 기준값 재설정 |
| 4 | 수정 범위 | **High 8건 + Medium 8건 수정**(V01~V10, V12~V17). **V11(Low, 불릿 음수 부호)은 수정하지 않고** xfail + 보고서로 남김 | Phase 4 포함, 전 단계 실행 |

**최종 검토**: 모든 Phase 종료 후 advisor(Fable)에게 에이전트 산출물 전체(테스트 코드·수정 diff·리뷰 보고서)를 검토받는 Phase 6를 추가한다(§7).

## 1. Context

- 대상: `C:\Users\정화민\Desktop\Hoseo Reasearch\Hoseo-Research`. 대학알리미 Excel → 전처리(ETL) → 통계 → matplotlib 차트 → GPT-4o 서술 → python-docx Word 보고서를 만드는 Streamlit 앱(v5.0, 범위 내 약 8,000줄 Python, 중첩 사본 591줄 제외).
- 목표: (1) 모듈·컴포넌트별 **계약(contract)을 고정하는 pytest 스위트** 신설, (2) **체크리스트 기반 코드 리뷰**로 결함을 심각도별 보고, (3) 수정은 승인 후 별도 단계.

## 2. 전제·결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 러너·구조 | pytest + 신규 `tests/` + `requirements-dev.txt` = `pytest==9.0.2`, `pytest-timeout==2.4.0` (pillow는 matplotlib 의존성으로 이미 설치, 추가 안 함) | 기존 커스텀 러너는 회귀 신호 불가 |
| 실행 환경 | **1차 기준은 핀 고정 venv `.venv-qa`**(`requirements.txt`+dev: pandas 2.3.3, openai 2.14.0, python-docx 1.1.0 = 배포본과 동일). 시스템 Python(pandas 3.0.5, openai 2.37, python-docx 1.2, dotenv 1.2.2)은 참고용, 실패해도 승인 기준 아님 | 로컬 green이 배포본을 대변해야 함 |
| Python 버전 | 3.11 기본(결정 1에 따라 변경 가능). CI는 단일 job | 개인 프로젝트 규모 |
| pandas 호환 | dtype 단언 금지, 값 비교(`assert_frame_equal(check_dtype=False, atol=1e-4)`), 골든 비교는 파일 바이트가 아니라 DataFrame | 2.x/3.x 차이(str dtype, CoW), OS 줄바꿈 |
| GPT | 가짜 클라이언트(fake client)만. 실 API는 `@pytest.mark.live`로 기본 제외 | 비용·비결정성 |
| 실데이터 | git 추적 `Raw data/*.xlsx`(10개)·`output/*.csv`(3개)를 골든으로 사용, `@pytest.mark.realdata` 분리. 합성(synthetic) 소형 DataFrame이 기본 | 재현성 |
| **프로덕션 코드 무수정 규칙** | Phase 0~3.5 동안 `report_app/`·전처리 스크립트를 한 줄도 바꾸지 않는다. 단위 접합점(seam)이 없으면 가장 가까운 관측 경계(AppTest 렌더 결과)에서 잠그고 `@pytest.mark.needs_refactor`로 표시. 헬퍼 추출은 Phase 4에서 해당 결함 수정과 함께 | 결함 잠금의 의미 유지 |
| 수정 범위 | 이번 QA는 **검증 + 결함 보고**까지. 수정은 Phase 4(결정 4) | 사용자 요청은 "검증 계획" |
| 범위 제외 | 중첩 폴더 `전임교원_연구실적_학교별자료/`(구버전 ETL 사본, 참조 없음, 삭제 권고만 기재). `scripts/` 훅·인스톨러·`start_app.bat`은 정적 리뷰 + 최소 테스트 2개 | 비용 대비 가치 |
| 커밋 | 어떤 Phase에서도 사용자가 명시적으로 요청할 때만. 푸시 전 README/CLAUDE.md 동기화 | 전역 규칙 |

## 3. 프로젝트 지도 (검증 대상)

```
Layer 0  전임교원_연구실적_전처리.py (910줄)  12개 함수, main()/process_in_memory() 2진입점(로직 3중 복제)
Layer 1  report_app/config.py               상수 17개, _PROJECT_ROOT = Path.cwd() (import 시 1회 고정)
Layer 2  report_app/data_loader.py          공개 9 + 비공개 1, 순수 함수(DataFrame in/out)
Layer 3  report_app/chart_generator.py      create_* 5종 → BytesIO PNG (import 시 rcParams 전역 변경, 3.13+ deepcopy 전역 패치)
Layer 4  report_app/gpt_reporter.py         _call_gpt + generate_* 4종 (client 위치 인자 주입 → fake 가능)
Layer 5  report_app/report_builder.py       build_report → BytesIO docx (디스크 쓰기 없음)
Layer 6  report_app/components/ 6개         styles / sidebar / toolbar / metric_card / chart_card(@st.dialog) / gpt_section(@st.fragment)
Layer 7  report_app/pages/ 3개              research.py 1,410줄 거대 모듈(God Module: step1~5 + 필터 + 소스 3종), home, settings(도달 불가 라우트)
Layer 8  report_app/app.py (264줄)          엔트리포인트, _DEFAULTS 19키, 이벤트 pop, 라우팅
```

테스트로 고정할 데이터 계약:

| 계약 | 내용 |
|---|---|
| CSV | `전체_대학_데이터.csv` [연도, 학교명, 전임교원수, SCI/SCOPUS논문수, 1인당논문수, 전국순위] / `권역별_순위.csv` [..., 권역명, 권역순위, 전국순위] / 레거시 `충청권_순위.csv` [..., 충청권순위, 전국순위]. 모두 utf-8-sig |
| hoseo_trend | {연도: {논문수, 전임교원수, 1인당논문수, 권역순위, 전국순위}} |
| averages | {연도: {전국평균, 권역평균, 비교군평균}} |
| rank_changes | {연도: {권역순위, 전국순위, 권역순위_변화, 전국순위_변화}}, 변화 = 이전 - 현재(양수 = 개선) |
| yoy_changes | {상위: [..3], 하위: [..3], 호서: {...}} (키 이름은 '호서'지만 값은 대상 대학) |
| compare_data | [{학교명, 전임교원수, 논문수, 1인당논문수, 전국순위, 권역순위}] |
| charts / narratives | {trend, bar, avg, rank, compare} / {trend, comparison, regional, yoy} |
| session_state | 40개 키 = `_DEFAULTS` 19 + 비포함 21 (부록 A) |

## 4. 검증 매트릭스 (컴포넌트 × 계층)

계층: U 단위(합성 데이터) / C 계약(모듈 간 키·컬럼) / I 통합(실데이터·파일) / A AppTest(`streamlit.testing.v1`, 서버 없음) / M 수동. ★ = Phase 1 최소 QA(minimum viable QA) 부분집합(약 40건, 80%의 위험을 잡는 20%).

| 컴포넌트 | U | C | I | A | M | 테스트 ID |
|---|---|---|---|---|---|---|
| 전처리 find_columns | ★P0 | | P1 | | P2 | ETL-U01~U04, U12, ETL-M01 |
| 전처리 filter/merge/metrics/rankings | ★P0 | ★P1 | ★P0 | | | ETL-U05~U08, ETL-C01, ETL-I04/I05 |
| 전처리 scan/config/export/진입점 | P1 | ★P0 | ★P0 | | | ETL-U09~U11, ETL-C02, ETL-I01~I03 |
| config.py | P1 | | | | | INF-03 |
| data_loader 9함수 | ★P0 | ★P0 | | | | DL-U01~U12, DL-C01 |
| chart_generator 5종 | ★P0 | | P1 | | P2 | VIS-U01~U07, VIS-M01 |
| report_builder | ★P0 | P1 | P1 | | | DOC-U01~U09, INT-01 |
| gpt_reporter | ★P0 | ★P0 | | P2 | P2 | GPT-C01~C03, GPT-U01~U02, GPT-M01 |
| components/styles | | P1 | | | P2 | UI-01 |
| components/sidebar | | | | ★P0 | | UI-02~UI-05 |
| components/toolbar, metric_card | | | | P1 | | UI-06, UI-07 |
| components/chart_card, gpt_section | | | | P1 | P2 | UI-08, UI-09, UI-11~13 |
| pages/home, settings | | | | P1/P2 | | UI-10, APP-04 |
| pages/research step1(소스·필터) | | P1 | | ★P0 | P2 | FLT-01, FLT-02, R7-07, R7-M01 |
| pages/research _go/_calc_stats/리셋 | P1 | | | ★P0 | | R7-01~R7-05, R7-11~R7-13 |
| pages/research step2~5 | | | | P1 | | R7-06, R7-08~R7-10 |
| app.py(부팅·라우팅·API키·클라우드) | | | | ★P0 | | APP-00~APP-03, APP-05 |
| output/ CSV 데이터 | | ★P0 | | | | INF-01, INF-02 |
| 인프라(버전·핀·시크릿·문서·인스톨러) | P2 | P1 | | | P2 | INF-04~INF-07, INF-M01 |
| 테스트 하네스 자체 | P0 | | | | | CONF-01/02, TST-02, MPL-01 |

## 5. 확정 결함과 잠금 테스트

검증 상세(재현 명령·수치)는 실행 시 `docs/QA_REVIEW_REPORT.md` 부록으로 옮긴다. 심각도 기준: **High** = 화면·보고서 수치 오류, 또는 문서화된 경로에서 크래시·데이터 손실 / **Medium** = 라벨·표시 오류, 우회 가능한 기능 불능 / **Low** = 외관·문서.

| ID | 심각도 | 위치 | 확정된 증상 | 잠금 테스트 |
|---|---|---|---|---|
| V01 | High | 전처리 `find_columns` :242-257 | 2017 Raw만 SCI 그룹이 '남/여' 쌍(계 없음) → fallback이 '남' 열 채택. 분자 = 남성 논문수, 분모 = 전체 교원 → 2017년 128개교 전부 과소(합계 -17.6%, 116개교 순위 변동). 호서대 61.4167 → 정확값 77.3614 | ETL-U03(현행 특성화), **ETL-U04**(정답 오라클, xfail) |
| V02 | High | research.py :682-731 → data_loader :166/:247/:356 | CSV 업로드 경로에 `_ensure_new_format` 없음. 라벨(:699)·help(:702)가 안내하는 레거시 `충청권_순위.csv` 업로드 시 3함수 KeyError('권역순위') → "파일 읽기 오류"로 오표기, 진행 불가 | DL-U11(전제), **R7-07**(정적 AST, xfail), R7-M01 |
| V03 | High | research.py :139 vs :95; :722-729, :764-771 | csv/existing 소스는 필터 없이 `_go(2)` 직행 → `region_name=None` → '권역평균'이 6개 권역 전체 평균(2025: 0.2264, 실제 충청권 0.1781), YoY 상·하위가 전국 혼합. 라벨·범례·프롬프트·Word 제목은 '충청권' | **R7-05**(xfail), FLT-01(회복 경로 긍정 계약) |
| V04 | Medium | sidebar.py :203 vs app.py :185 | `sidebar_reset_clicked`를 sidebar가 같은 run에서 먼저 pop → app.py 리셋 블록 죽은 코드(dead code). '처음부터 다시'는 home 이동만, home에서는 무반응. 데이터·서술·max_step 잔존 | UI-04(전제), **R7-02**(xfail), R7-12 |
| V05 | High | research.py :1401-1403 → :320-340 | step-5 리셋이 `_raw_*_df`/`_filter_years`/`_filter_compare`를 삭제 대신 None 대입 → 재로드 후 `_render_data_filter` :338 TypeError(핸들러 없음). 로컬 Raw 경로는 같은 run 즉시, csv/existing은 1단계 복귀 시. 매 rerun 반복 | **R7-03**(xfail), R7-12 |
| V06 | Medium | research.py :1383-1407; app.py :246; sidebar.py :175 | 리셋이 `max_step` 미초기화 → 2~5단계가 '✓'로 클릭 가능 → 2단계 :820 TypeError, 3단계 chart_generator :114 AttributeError. 4·5단계는 "None년 / 0종" 오표시 | **R7-04**(xfail), R7-12 |
| V07 | High | research.py `_go` :108-117; app.py :202-204 | 4단계를 벗어난 run 종료 시 Streamlit이 text_area 위젯 상태 제거 → 이후 `_go` 콜백의 `get('narrative_*')`가 '' → `_saved_`가 ''로 덮임. **4→5→4, 4→3→4 등 모든 왕복에서 서술 4개 소실**. 사이드바 이동은 백업조차 없음(4→5 사이드바 직행 시 서술 없는 보고서). 4→5 버튼 직행만 정상 | **R7-01**(3경로 parametrize, xfail) |
| V08 | High | chart_generator :176; research.py :996, :1019-1021 | `create_comparison_bar`가 '연도'만 필터(`region_name`은 제목 전용). V03 경로에서 6개 권역 140행을 "충청권 대학 비교"로 그림. breakdown 표는 권역순위 1이 6행 | **VIS-U04**(xfail) |
| V09 | Medium | data_loader :253-254 vs research.py :826-830 | 부호 이중 반전: 개선(+N)이 빨간 `▼ +N계단`, 악화가 초록 `▲ -N계단`. 2단계 KPI 카드 2장에 국한 | DL-U05(규약 문서화), **R7-06**(xfail, needs_refactor) |
| V10 | Medium | data_loader :297, :163-166, :240-247 | 다중권역 대학 + `region_name=None`: YoY 단일키 merge로 cross-product(실데이터 2023 하위 3에 예원예술대 2회); trend/rank는 '마지막 행 승리'(docstring "첫 권역"과 불일치) | **DL-U10**(xfail + 특성화) |
| V11 | Low | report_builder :81 | `lstrip('•-· ')`가 줄 선두 음수 부호 제거('• -0.5편 감소' → '0.5편 감소'). 문장 중간·▼는 보존 | **DOC-U04**(xfail) |
| V12 | High | data_loader :298-317; research.py :440, :513-516 | (1) merge 6행 미만이면 head(3)/tail(3) 중복: **기본 경로(비교군 5개교, 2025)에서 호서대가 상위 3과 하위 1에 동시 출력**(제주권은 상위 = 하위). (2) 이전값 0 → "+0.0%"로 신규 실적이 무변화로 표기. UI·보고서·GPT 모두 미필터 | **DL-U09**(xfail) |
| V13 | Medium | scripts/smoke_test.py :40; e2e_test_full.py :225,237,483-484,565,577,670 | 스모크 SMOKE_CODE 첫 줄이 try 밖에서 `Path`/`__file__` 참조 → 항상 NameError 후 exit 0(미배선). e2e는 옛 키 단언·grep 대상 파일 오류·포트 8502 불일치로 매 실행 exit 1 | INF-06(xfail, P2), 부록 B 퇴역 목록 |
| V14 | High | 전처리 `merge_campuses` :389-404; config/universities.json | 2025 기준 '대학교' 209행 중 57행 제외 = 국립 29·국립대법인 2·과기원 5·특별법국립 1·공립 1·사립 19 → 남는 134개교는 **100% 사립**(전임교원 30.9% 누락). '전국순위/전국평균'은 등재 사립 내 수치(호서대 77/134위 vs 전체 113/188위). 하위 README에만 '제한사항' 언급 | ETL-I04(특성화), **ETL-I05**(오라클, xfail), 결정 2 |
| V15 | Medium | build_windows.py :197, :204; research.py :745, :777 | 번들이 `권역별_순위.csv` 누락(사실). 증상 정정: 폴백은 UI에서 도달 불가하고, 설치 직후 '기존 output/ 사용' 카드가 **"파일 없음: 충청권_순위.csv"**(존재하는 파일을 없다고 표시, :777 하드코딩). 동봉 CSV는 불필요 동봉물(dead weight), Raw data/ 빈 폴더 | **INF-05**(xfail) |
| V16 | Medium | docs/CHECKLIST :20-24 외 4곳 vs app.py :83 | 문서는 `[openai] api_key` 중첩 테이블, 코드는 `st.secrets["OPENAI_API_KEY"]` 평면 키. Streamlit은 테이블을 env로 내보내지 않아 폴백도 실패 → 키 ''. 사이드바 "⚠ 미설정"은 뜨나 원인 안내 없음 | **APP-02**(특성화), INF-04(문서 xfail) |
| V17 | Medium | research.py :320-322, :625-771 | (비평에서 추가) 4개 로드 경로 모두 `_raw_*`·`charts`·`narrative_*`·`_target_university`를 지우지 않음 → A 로드 후 B 재로드 시 필터에 A 원본, 3단계에 A 차트. V06×V07 연쇄: 리셋 후 사이드바로 5단계 직행 시 이전 데이터의 `_saved_narrative_*`가 새 보고서에 삽입 | **R7-11**(xfail), R7-12 |

**연쇄 관계**(수정 순서용): V03 → V08·V10·V12 도달 경로. V04·V05·V06·V17은 "리셋 경로 3개(사이드바·step5·재로드)가 서로 다른 키 집합을 초기화"하는 한 원인. V02·V15는 "레거시 파일명이 UI 문자열에 하드코딩"된 한 원인. V01·V14는 ETL 입력 가정 문제로 **기존 output CSV가 재생성 대상**(결정 3).

**정적 확인(드리프트 검증 15건)**: D01 거대 모듈 1,410줄 ✔ / D02 REGION_MAP 이중 정의(값 동일, config 쪽 미사용) ✔ / D03 `Path.cwd()` 6곳(config.py:80, app.py:53, research.py:56, :578, 전처리:783, :784) ✔ / D04 버전 하드코딩 4곳 ✔ / D05 리셋 갭(비포함 키 21개, step5 리셋은 23키만) ◐ / D06 이중 pop ✔ / D07 '호서' 하드코딩으로 데이터 손실 **반박**(키 이름만) / D08 `_call_gpt` 무방어 ✔ / D09 gpt_section 인라인 CSS 7개 충돌 ✔ / D10 toolbar 미정의 클래스 10개 ✔ / D11 chart_card 래핑 불완전 ✔ / D12 pytest 인프라 부재 ✔ / D13 함수 수(공개 9, 비공개 1; e2e hasattr 목록에 detect_region 등 누락) ◐ / D14 process_in_memory 3중 복제 ✔ / D15 CLAUDE.md/README 경로 드리프트 ✔.

**추가 후보(리뷰 보고서에서 triage, 테스트는 P2 또는 없음)**:
- 중첩 버튼 죽은 코드(research.py:671), `settings` 라우트 도달 불가, `get_region_universities` 호출자 없음, regions.json은 레거시 분기 전용
- 타 권역 대상 선택 시 비교군 = 자기 자신(research.py:488-500), YoY 데이터 없을 때 4단계 게이트 부재, "비교군 5개 대학" 프롬프트 하드코딩(gpt_reporter:128)
- HTML 미이스케이프 55곳(CSV 유래 대학명 → chart_card:106, gpt_section:108, metric_card:102, research.py:1354-1365), traceback 화면 노출(research.py:638, :679)
- `except Exception` 6곳(research.py:634, :675, :730, :1177, :1345; gpt_section.py:136)의 메시지 정확성
- `st.image/st.dataframe(use_container_width)` deprecation 경고, `_save_fig` 예외 경로 Figure 누수, docx eastAsia 폰트 미설정, 대학명 `[:-2]` 절단(chart_generator:133, :381)
- 동일 연도 파일 2개 무경고 덮어쓰기, 로컬/클라우드 연도 정규식 불일치, alias 누락으로 시계열 단절 6개교, 청운대·호원대(산업대학) 설정 충돌
- macOS 번들 arm64 전용, 인스톨러 버전 '3.0' 고정, `log_change.py`가 CLAUDE.md를 무한 성장, 훅 9개 미배선

## 6. 테스트 설계

### 6.0 규칙

1. **잠금 방향 일치**: §5의 결함은 반드시 `xfail(strict=True, reason="V##")`로 "정답"을 단언한다(오늘 실패해야 함). 현재 동작을 기록만 하는 테스트는 `@pytest.mark.characterization`을 달고 "오늘 통과, 수정 후 삭제"로 표기한다. 같은 동작을 한쪽에서 통과·다른 쪽에서 결함으로 분류하지 않는다.
2. xfail(strict)은 **결정적(deterministic)** 조건에만 쓴다(정렬 안정성·매 실행 다른 결과에 의존하는 단언 금지).
3. 프로덕션 코드 무수정(§2). 관측 경계에서 잠근 테스트는 `@pytest.mark.needs_refactor`.
4. 결정 2·3·4를 전제하는 단언은 **해석에 중립적으로** 쓴다. 예: R7-05는 "권역평균이 `_target_region()`이 가리키는 권역의 평균과 같다"(권역 자동 설정이든 필터 강제든 통과), DL-U09(2)는 "prev=0·cur>0 행이 prev=0·cur=0 행과 구분된다".

### 6.1 파일 구조

```
tests/
  conftest.py                  # 6.2. 모듈 최상단에서 샌드박스 생성 + os.chdir (어떤 report_app import보다 먼저)
  test_harness_guards.py       # CONF-01/02, TST-02, MPL-01
  fixtures/
    make_frames.py             # make_nat(rows)/make_reg(rows) 합성 DataFrame 팩토리
    make_raw_header.py         # find_columns용 헤더 11행 리터럴 (style="2016"|"2017"|"2018+", 실제 Raw 상위 11행 덤프)
    tiny_png.py                # 1x1 PNG 바이트 상수 (matplotlib 없이 charts 시드)
    fake_openai.py             # SimpleNamespace 기반 fake client, create(**kw) 기록 + 고정 응답(canned content)
  unit/
    test_preprocess_columns.py       ETL-U01~U04, U12
    test_preprocess_pipeline.py      ETL-U05~U11
    test_config.py                   INF-03
    test_data_loader.py              DL-U01~U12
    test_chart_generator.py          VIS-U01~U07
    test_report_builder.py           DOC-U01~U09
    test_gpt_reporter.py             GPT-C01~C03, GPT-U01~U02
    test_research_helpers.py         R7-13 (비렌더 모드(bare mode) session_state)
  contract/
    test_data_contracts.py           DL-C01, ETL-C01, INF-01, INF-02
    test_css_contract.py             UI-01
    test_repo_hygiene.py             INF-04 (table-driven 1개), INF-05
  integration/
    test_preprocess_golden.py        ETL-C02, ETL-I01~I05 (@realdata, @slow)
    test_pipeline_end_to_end.py      INT-01 (@realdata)
    test_infra_subprocess.py         INF-06, INF-07 (P2)
  apptest/
    test_components.py               UI-02~UI-13
    test_app_shell.py                APP-00~APP-05
    test_research_flow.py            FLT-01/02, R7-01~R7-12
  manual/CHECKLIST.md                UI-M01, R7-M01, ETL-M01, VIS-M01, GPT-M01, INF-M01
pytest.ini      markers: realdata, slow, live, characterization, needs_refactor; addopts = --timeout=300; filterwarnings = ignore::pandas.errors.SettingWithCopyWarning
requirements-dev.txt   pytest==9.0.2, pytest-timeout==2.4.0
```

### 6.2 conftest 필수 설계 (비평으로 확정된 결합 지점)

1. **cwd는 모듈 레벨에서 고정**: `report_app.config`가 import 시 `Path.cwd()`를 1회 평가하고 pytest는 수집 단계에서 테스트 모듈을 import하므로, 세션 픽스처는 너무 늦다. `conftest.py` 최상단(어떤 report_app import보다 앞)에서 `SANDBOX = Path(tempfile.mkdtemp(prefix="hoseo_qa_"))`를 만들고 `output/*.csv`를 복사한 뒤 `os.chdir(SANDBOX)`. `PROJECT_ROOT = Path(__file__).resolve().parents[1]` 상수를 둔다.
2. **2단 샌드박스**: (a) 세션 샌드박스 = import 시 고정되는 상수용, **읽기 전용**으로 취급. (b) 호출 시점에 `Path.cwd()`를 쓰는 코드(전처리 `main()` :783-784, `.env` app.py:53, `Raw data/` research.py:578, `output/reports/` :1330)는 테스트별 `monkeypatch.chdir(tmp_path)` + 필요 파일 복사. 경로 상수 패치가 필요하면 값으로 바인딩된 이름 3곳을 모두 패치: `report_app.config`, `report_app.data_loader`, `report_app.pages.research`의 `NATIONAL_CSV/REGIONAL_CSV/REGIONAL_CSV_LEGACY/REPORT_DIR`.
3. **matplotlib**: matplotlib 첫 import 전에 `MPLBACKEND=Agg`, `MPLCONFIGDIR=tempfile.mkdtemp(prefix="mpl")`(ASCII 접두어). 세션 시작 시 `import report_app.chart_generator`를 미리 수행해 폰트 캐시 생성을 AppTest 타임아웃 밖으로 뺀다. autouse teardown은 **`plt.close("all")`만**(누수 단언은 VIS-U01/U03 본문에서). `matplotlib.rc_context()`로 rcParams 복원.
4. **환경변수·`.env` 격리**: function-scope autouse로 시작·종료 시 `OPENAI_API_KEY`·`STREAMLIT_SHARING_MODE`·`IS_CLOUD` delenv + 샌드박스 `.env` 삭제(app.py:58 `load_dotenv`가 매 run 재주입하므로). `at.secrets["_dummy"]="x"`로 Secrets를 빈 dict로 강제.
5. **AppTest 규칙**: `AppTest.from_file(PROJECT_ROOT / "report_app" / "app.py", default_timeout=60)` **절대경로**(상대경로는 샌드박스 cwd에서 FileNotFoundError). `from_function` 래퍼는 모듈 레벨 def + 내부 import + **ASCII 전용 본문**(Windows cp949로 기록 후 UTF-8로 읽어 한글 포함 시 SyntaxError), 한글 인자는 `kwargs=`로 주입. 다이얼로그(`sidebar_api_change` pop 후 렌더)는 매 run 직전에 `at.session_state["sidebar_api_change"]=True` 재설정. 관측/조작 가능 표: `imgs`·`download_button`·`file_uploader`·`progress`는 `at.get(type)` 개수만, `data_editor`는 `at.dataframe` 읽기만, 업로드·편집·다운로드 저장은 수동.
6. **IS_CLOUD 분기**: subprocess 대신 `monkeypatch.setattr(report_app.config, "IS_CLOUD", True)` + `report_app.pages.research.IS_CLOUD`(AppTest는 매 run에 app.py의 `from report_app.config import IS_CLOUD`를 재실행). 분기 6곳: app.py:131, research.py:243, :584, :603, :613, :1329.
7. **비렌더 모드(bare mode)**: `test_research_helpers.py` 전용 autouse로 `streamlit.runtime.state.session_state_proxy._mock_session_state = None` 설정·해제(전역 mock 누출 방지).
8. **subprocess 규약**(INF-06/07): 리스트 인자, `env={**os.environ, "PYTHONUTF8":"1", "PYTHONIOENCODING":"utf-8"}`, `encoding="utf-8", errors="replace"`, 단언은 인코딩 무관 조건(returncode, 'NameError' 포함 여부).
9. **한글 파일명 모듈**: 전처리 스크립트는 `importlib.util.spec_from_file_location`로 로드하는 세션 픽스처 `pp_module`(config는 `__file__` 기준이라 복사 불필요).
10. **하네스 가드**: CONF-01 `report_app.config._PROJECT_ROOT == SANDBOX` 및 research/data_loader 바인딩 경로 부모 == SANDBOX/output; CONF-02 각 테스트 후 `.env` 부재·`OPENAI_API_KEY` 부재; TST-02 `tests/apptest/` 래퍼 소스 ASCII 검사; MPL-01 backend == agg, configdir == tmp.

### 6.3 컴포넌트별 테스트 카드 (긍정 계약 → 결함 잠금 순)

**전처리** (순수 함수, 합성 헤더/프레임, 실데이터는 @realdata)
- ETL-U01 신형(2018+): `make_raw_header("2018+")` → {학교명 5, 학교종류 1, 지역 3, 전임교원수 6, SCI논문수 24, data_start_row 8}. 줄바꿈 포함 헤더 탐지.
- ETL-U02 구형(2016): fallback이 c6/c12, data_start_row 7 (정확).
- ETL-U03 [특성화] 2017 스타일에서 SCI 열 == '남' 열 인덱스(19). 수정 후 삭제.
- **ETL-U04 [V01 xfail]** 2017 스타일 → SCI = 남+여 합(또는 명시적 오류). @realdata 짝: 실제 2017 파일 호서대 SCI == 77.3614 ± 1e-4.
- ETL-U05 calculate_metrics: `1인당 == round(SCI/교원, 4)`(내장 round, 0.11095 → 0.1109), 교원 0 → 0.0, 빈 df 무예외, 입력 불변.
- ETL-U06 calculate_rankings: [1,1,.5,.5,0] → [1,1,3,3,5](method='min', int); 다중권역 대학은 권역마다 1행, 전국순위 동일; 정렬 [권역명, 권역순위]; NaN → IntCastingNaNError 특성화.
- ETL-U07 merge_campuses: alias 합산(단국대 경기+충남 → 1행, `univ_region_map == {'단국대학교': ['수도권','충청권']}`), 미매핑 제외 + capsys '[경고]', '지역' 없으면 {}.
- ETL-U08 filter_universities [특성화]: '대학교'만, 'nan'/'' 제거, 청운대·호원대(산업대학) 제외.
- ETL-U09 scan_raw_files: 연도 추출·정렬, NFD 파일명 1케이스, `2022_c.xlsx` 거부(process_in_memory :676는 수용 → 불일치 특성화), 동일 연도 2개 → 마지막 채택 특성화.
- ETL-U10 load_config + config JSON 무결성: 136/164/27, alias 전체 유일, regions 이름이 모두 name에 존재, 도출 권역명 ⊆ REGION_MAP 값.
- ETL-U11 export_csv/excel: rename, 연도 0열, 정렬, 충청권 없으면 `충청권_순위.csv` 미생성.
- ETL-U12 find_columns 실패: '학교' 없음 → ValueError 메시지에 '컬럼 탐지 실패' + 헤더 덤프.
- ETL-C01 REGION_MAP 동일성(ast.literal_eval, config import 없이).
- ETL-C02 [특성화 골든] Raw 2024·2025 → process_in_memory 컬럼 정확 고정(national 6, regional 8), 2025 N == 134, 전국순위 1..128.
- ETL-I01 main() tmp cwd(Raw 2개 복사) → xlsx 1 + CSV 3 생성, `충청권_순위.csv` 컬럼 [..., 충청권순위, 전국순위].
- ETL-I02 main() ↔ process_in_memory 동치(DataFrame 비교, check_dtype=False).
- ETL-I03 [특성화 골든, @slow] Raw 10개 → process_in_memory == output CSV 3개(DataFrame 비교) + xlsx 두 시트 == CSV. **주의: V01·V14로 값이 부정확한 상태를 잠그는 것**이며 결정 3 이후 재설정.
- ETL-I04 [특성화] 2025 미매핑 57개교 집합 고정(충남대·KAIST·공주대·한밭대 포함) + 설립구분 분포(국립 29·국립대법인 2·과기원 5·특별법국립 1·공립 1·사립 19).
- **ETL-I05 [V14, 결정 2 반영]** 원래의 "국공립 0건" xfail은 **삭제**. 대신 라벨 계약을 잠근다: `merge_campuses`가 제외 대학 수를 반환값 또는 로그로 노출하고, `build_report`·2단계 화면·GPT 프롬프트 문자열에 "등재 사립 N개교 기준"이 포함된다(xfail, Phase 4에서 통과).
- ETL-M01 2016/2017 실제 파일 수동 대조(파일 내 1인당 값과 비교).

**data_loader** (합성 프레임, cwd 무관)
- DL-U01 `_ensure_new_format` 멱등·입력 불변·신포맷 동일 객체·두 컬럼 공존 시 무변환.
- DL-U02 `load_all_data` 3분기(신포맷/레거시 변환/없음 → FileNotFoundError, 두 파일명 포함). 경로 패치는 6.2-2.
- DL-U03 `get_hoseo_trend(university=, region_name=)`: 권역 필터, 대상 부재 → {}, regional 부재 → 권역순위 None, 정렬.
- DL-U04 `get_averages`: 권역/비교군 평균, `compare_group=[]` → 0.0, `region_name` 없음 → 0.0, None → 전체.
- DL-U05 `get_rank_changes`: 부호 규약(양수 = 개선) 명시 단언, 단일 연도 → None, 연도 공백 → 직전 존재 연도 대비 특성화.
- DL-U06 `get_compare_group_data`: 미존재 대학 무예외, 정렬, 타입, 권역 밖 → 권역순위 None.
- DL-U07 `detect_region`(정렬, 다중, 컬럼 없음 → []), `get_region_universities`(year 유무; 컬럼 없음 → KeyError 특성화).
- DL-U08 `get_yoy_changes` 정상: 증감률 round 1, 상위 = 최고 먼저, 하위 = 내림차순 유지, '호서' 키가 `university=` 대상(순천향대 지정 시 학교명 == 순천향대).
- **DL-U09 [V12 xfail]** (1) 5행 비교군 → `set(상위) ∩ set(하위) == ∅`, 2행 → 상위 ≠ 하위; (2) prev=0·cur>0 행이 prev=0·cur=0 행과 구분됨.
- **DL-U10 [V10]** xfail: 다중권역 D + None → YoY 학교명 unique. 특성화: 행 순서 뒤집으면 `get_hoseo_trend` 권역순위가 바뀜(마지막 행 승리 ≠ docstring "첫 권역").
- DL-U11 [V02 전제, 특성화] 레거시 df 직접 투입 → get_hoseo_trend/get_rank_changes/get_compare_group_data KeyError('권역순위'), 나머지 2개 정상.
- DL-U12 NaN 교원수 → ValueError 특성화; `get_available_years` 원소 python int.
- DL-C01 출력 키 집합 ↔ chart_generator/report_builder/gpt_reporter 입력: 합성 프레임으로 get_* 5개 → 5차트 + build_report + generate_* 4종(fake client) 무예외, 키 집합 정확 고정(hoseo_trend/averages/rank_changes/yoy/compare_data).

**chart_generator** (MPLBACKEND=Agg, 누수 단언은 본문)
- VIS-U01 5종: BytesIO, PNG 매직, `PIL.Image.open` OK, `len > 1000`, 호출 후 `plt.get_fignums() == []`.
- VIS-U02 [특성화] 경계값 무예외: 연도 1개, 빈 입력, 대상 부재, NaN이 첫 원소가 아닌 위치(전국평균 NaN).
- VIS-U03 [Figure 누수 xfail] `create_avg_comparison`에 `hoseo_trend[year]["1인당논문수"]=nan` → ValueError(:256 set_xlim) 후 `get_fignums()`가 비어 있어야 함(현재 누수).
- **VIS-U04 [V08 xfail]** 충청권 3 + 수도권 4 DataFrame, `region_name='충청권'` → `cg.plt.subplots` 래핑으로 `len(ax.patches) == 3`(현재 7).
- VIS-U05 `create_rank_trend_chart`: 권역순위 전부 None → 단일 축, 일부 None → 1x2(subplots 인자 캡처).
- VIS-U06 `_setup_korean_font` OS 3분기(`cg._platform.system`, `cg.Path.exists`, `addfont` MagicMock) → rcParams 기대값.
- VIS-U07 [후보 xfail, P2] `university='고려대학교(세종)'` → 제목에 '고려대학교(세' 없음.
- VIS-M01 CI(Linux+fonts-nanum, 3.13)에서 deepcopy 패치·findfont 경고 확인.

**report_builder** (메모리 내 docx)
- DOC-U01 전체 fixture → `PK\x03\x04`, 재오픈 tables == 3, inline_shapes == 5, 폭 [14,12,15,14,11]cm, 제목 5개(정규식 `^[1-5]\. `), `rb.date` 고정.
- DOC-U02 charts/narratives 비어도 무예외, shapes 0, 표 3, 제목 5; averages/rank_changes 인자 미사용(dead parameter) 특성화.
- DOC-U03 yoy 빈/{} → 표 2 + '(전년도 데이터 없음)'; 3+3 → rows 7; 증감률 셀 `+x.x%`.
- **DOC-U04 [V11 xfail]** `_add_narrative("• -0.5편 감소\n- 정상 불릿\n-3.2% 하락\n• ▼1위 하락")` → ['-0.5편 감소','정상 불릿','-3.2% 하락','▼1위 하락'].
- DOC-U05 [후보 xfail] `_set_font` rFonts `w:eastAsia == '맑은 고딕'`.
- DOC-U06 [특성화] 빈/손상 BytesIO 차트 → UnrecognizedImageError; 소진된 BytesIO는 seek(0)로 정상.
- DOC-U07 셀 배경(헤더 2E75B6, zebra D6E4F0, 대상 대학 FFF2CC + bold, `university=` 변경 시 강조 이동), 권역순위 None → '-', 포맷('1,234명', '12.35편').
- DOC-U08 tmp cwd에서 실행 → 파일 0개 생성; `rb.date` 고정 시 두 호출 바이트 동일.
- DOC-U09 [후보 xfail] `university='제주국제대학교', region_name='제주권'` parametrize → 제목·캡션에 '충청권'/'천안·아산 5개 대학'/'호서' 리터럴 없음(현재 COMPARE_GROUP_NAME 하드코딩).
- INT-01 [@realdata] load_all_data → get_*(호서대·충청권·2025) → 5차트 → build_report → 재오픈 검증; 제주국제대·제주권도 무예외.

**gpt_reporter** (fake client: `SimpleNamespace(chat.completions.create(**kw))` → `.choices[0].message.content`)
- GPT-C01 `_call_gpt`: create 1회, kwargs-only, model/max_tokens/temperature == config, messages[0] == system prompt, 반환 == content.strip().
- GPT-C02 generate_* 4종 parametrize: 프롬프트에 `json.dumps(obj, ensure_ascii=False, indent=2)` 부분 문자열, 연도·대학·권역명 반영, `averages.get(year, {})` 누락 시 '{}' 특성화, rank_changes None → null 무예외.
- GPT-C03 [후보 xfail] compare_data 3개 → 프롬프트에 "비교군 5개 대학" 없음.
- GPT-U01 [D08 특성화] choices=[] → IndexError, content=None → AttributeError, RateLimitError/APITimeoutError 그대로 전파.
- GPT-U02 `university=None` → config.UNIVERSITY, 지정 시 그 값(4종). numpy 스칼라 직렬화 OK.
- GPT-M01 실키 수동(불릿 2~4개, 마크다운 없음, 소수 4자리).

**components** (`AppTest.from_function`, ASCII 래퍼 + kwargs)
- UI-01 CSS 계약: `get_css()`가 `<style>`로 시작·종료, 중괄호 균형; 컴포넌트 HTML의 `ir-*` 클래스가 styles.py에 정의(현재 toolbar 10개 미정의 → xfail, D10); 인라인 `<style>` 셀렉터 ∩ styles.py == ∅(현재 gpt_section 7개 → xfail, D09).
- UI-02 sidebar 모듈 클릭 → `_ret == ('research', None)`, 플래그 소비됨.
- UI-03 sidebar 단계 게이팅: `current_step=3, max_step=3` → step 1·2 활성, 3 현재, 4·5 disabled; 클릭 → (research, 1); 현재 단계 클릭 → None.
- UI-04 [V04 전제, 특성화] `sidebar_reset_btn` 클릭 → `_ret == ('home', None)`이고 `'sidebar_reset_clicked' not in session_state`.
- UI-05 sidebar API 섹션: 미설정/설정됨 표기, 변경 버튼 → `sidebar_api_change is True`(pop 안 함).
- UI-06 toolbar: markdown 1개, 모듈명·단계명·날짜·'v5.0' 포함, breadcrumb 항목 수.
- UI-07 metric_card: up → `ir-metric-delta up` + ▲, down → ▼, None → delta 없음, 빈 리스트 → 요소 0.
- UI-08 gpt_section: stub generate_fn → 클릭 후 `session_state[key]`·text_area 값 == 결과; `generate_fn=None` → disabled; raise → `at.error`. (fragment는 AppTest에서 전체 rerun)
- UI-09 chart_card: 1x1 PNG, breakdown df → markdown 제목, dataframe 1, `zoom_*` 클릭 → `_chart_dialog_*` 3키 설정, `at.get('download_button')` 1개.
- UI-10 home: 클릭 없음 → None, `home_research` 클릭 → 'research', 나머지 카드 disabled.
- UI-11 [후보 xfail] title에 `<b>X</b> & Y` → markdown에 `&lt;b&gt;`(chart_card/gpt_section/metric_card).
- UI-12 [후보 xfail] chart_card 렌더 후 `at.warning` 중 'use_container_width' 포함 == 0(대상: st.image·st.dataframe만; button은 경고 없음).
- UI-13 [D11 xfail] chart_card(breakdown 있음) 후 `</div>`만 담긴 markdown 요소 없음.
- UI-M01 브라우저: sticky 툴바, 3분할 정렬, 사이드바 활성 배경, gpt_section 상태 dot 지연 갱신, 다운로드 저장, 확대 모달 폭.

**app.py 셸** (`AppTest.from_file(절대경로)`, 데이터 불필요한 것부터)
- APP-00 부팅 스모크: `at.exception == []`, module == 'home', step == 1, api_key == ''. **wall time 기록**(타임아웃·규모 산정 근거).
- APP-01 라우팅: home 카드 → research/step 1; step 버튼 게이팅; step=3 시드 → max_step 3 갱신.
- APP-02 `_get_api_key` 우선순위: `at.secrets` 평면 키 → 사용 / env → 사용 / 'sk-여기에' → '' / secrets 없음 → env. **[V16 특성화]** `at.secrets = {"openai": {"api_key": "sk-..."}}` → api_key == ''.
- APP-03 API 키 다이얼로그: 플래그 재설정 패턴으로 `_dialog_api_key` 입력 → '저장' → `session_state.api_key` 갱신 + function-scope cwd의 `.env`에 `OPENAI_API_KEY=` 기록(IS_CLOUD=True면 미기록).
- APP-04 settings: `module='settings'` 강제 → 렌더 무예외, 마스킹 키(`sk-abcd...wxyz`) 표시; 리뷰 노트 '사이드바에서 도달 불가'.
- APP-05 IS_CLOUD(6.2-6 monkeypatch): `src_existing` disabled, Raw 저장 버튼 없음, `Raw data/` 미생성, 5단계 후 `output/reports` 미생성.

**pages/research 흐름** (샌드박스 output CSV, charts는 1x1 PNG 시드로 3단계 렌더 우회, `_call_gpt` monkeypatch)
- FLT-01 [V03 회복 경로 긍정 계약] existing 로드 → 1단계 → `apply_filter` → `_target_region == '충청권'`, `_custom_compare_group`에 호서대 포함, `averages[y]['권역평균'] == regional_df[권역명==target].mean()`, `yoy` 상·하위 학교가 모두 그 권역, `charts == {}`.
- FLT-02 다중권역 대학(단국대) 선택 → `_filter_region_select` 등장; 타 권역 대상 → 비교군 == [target] 특성화(data_editor는 읽기만).
- **R7-01 [V07 xfail, parametrize 3경로]** (4→5 버튼→4 버튼), (4→3 버튼→4 버튼), (4→사이드바 5→'Word 생성') → 서술 4개가 text_area·`_saved_*`·보고서에 보존.
- **R7-02 [V04 xfail]** research step 3 + 데이터 시드 → `sidebar_reset_btn` → `national_df is None`, `max_step == 1`, `charts == {}`, `narrative_trend == ''`.
- **R7-03 [V05 xfail]** step 5 '처음부터' → existing 재로드 → '← 1단계로' → `at.exception == []`, '분석 연도 선택' 렌더, `'_raw_national_df' not in session_state`.
- **R7-04 [V06 xfail]** '처음부터' 후 `max_step == 1`, `sidebar_step_1..4` disabled; step=2 강제 시 예외 없음.
- **R7-05 [V03 xfail]** existing 로드 직후 2단계: `averages[y]['권역평균'] == regional_df[권역명 == _target_region()].mean()`, yoy 상·하위 학교가 모두 그 권역.
- **R7-06 [V09 xfail, needs_refactor]** rank_changes에 `권역순위_변화=+5` 시드 → 2단계 markdown에 `ir-metric-delta up`과 `▲ +5계단`(현재 down/▼).
- **R7-07 [V02 xfail, 정적 AST]** `_render_source_csv`·클라우드 raw 분기가 `dl._ensure_new_format` 또는 `load_all_data(national_df=, regional_df=)`를 호출한다(file_uploader는 AppTest 불가 → 정적 대체 + R7-M01).
- R7-08 해피패스: existing → filter → 2 → 3(실제 렌더 1회, 나머지는 시드) → 4(`_call_gpt` stub, 일괄 생성) → 5 'Word 생성' → `report_buf` PK 매직, docx 재오픈 서술 4개 포함.
- R7-09 4단계 API 키 게이트: api_key '' → `at.error`에 '⛔' + 이후 요소 없음(st.stop); 유효 시 gen_all + text_area 4개.
- R7-10 3단계 캐시: charts 시드 시 `cg.create_*` 호출 0회, `{}` 시 5회; `zoom_trend` 클릭 → dataframe 존재.
- **R7-11 [V17 xfail]** A(existing) 로드 → filter → 1단계 → csv/existing으로 B 재로드 → `_raw_national_df`가 B와 동일, `charts == {}`, `_target_university` 기본값.
- R7-12 리셋 매트릭스(table-driven, xfail strict): 경로 {사이드바, step5} × 비포함 키 21개 → 기대 사후값 표(부록 A). V04/V05/V06/V17 잔존 키를 한 테스트로.
- R7-13 비렌더 모드 단위: `_go(5)` → `_saved_narrative_trend == 'abc'`, step 5; `_calc_stats`가 dl.get_* 5개에 `university=/region_name=/compare_group=` 키워드 전달(MagicMock).
- R7-M01 수동: Raw xlsx 업로드 → 전처리 → CSV 생성; 레거시 CSV 업로드 시 "파일 읽기 오류: '권역순위'" 재현; 중첩 버튼(research.py:671) 무반응 재현.

**인프라·데이터**
- INF-01 CSV 계약: 3개 컬럼 순서·BOM·NaN 0·연도 {2016..2025}·(연도,학교명) 유일성(권역 CSV 중복은 정확히 다캠퍼스 6개교)·순위 정수 1..N·`1인당 == round(논문/교원, 4)` ± 1e-4.
- INF-02 `충청권_순위.csv` ≡ `권역별_순위.csv[충청권]`(rename·drop 후 285행 동일) 및 `_ensure_new_format` 결과 동일.
- INF-03 config.py: `IS_CLOUD` 파싱(`"0"`도 True 특성화), 경로 == cwd/output, reload 후 tmp cwd 반영.
- INF-04 저장소 위생(table-driven 1개): 인스톨러 버전 3.0 vs 태그(xfail), Python 버전 선언 집합(xfail), 핀 vs 설치(INFO만), `.gitignore`에 .env/secrets, 추적 텍스트에 `sk-[A-Za-z0-9_-]{20,}` 0건(매치 시 위치만), 문서에 'Hoseo-IR-'·옛 메모리 경로 없음(xfail), **[V16] CHECKLIST의 toml 블록을 파싱해 평면 키 `OPENAI_API_KEY` 존재(xfail)**, `--timeout` 사용 시 pytest-timeout 핀.
- **INF-05 [V15 xfail]** build_windows.py 복사 목록에 `REGIONAL_CSV.name`(AST); research.py:777 메시지가 `REGIONAL_CSV.name` 사용.
- INF-06 [V13 xfail, P2] `subprocess([-c, SMOKE_CODE], cwd=PROJECT_ROOT)` returncode 0 & stdout 'OK'/'SKIP'.
- INF-07 [P2] chart_generator headless import subprocess → PNG 매직, Linux findfont 경고 기록.
- INF-M01 인스톨러 실제 빌드·설치(Windows VM, Intel/ARM Mac).

### 6.4 코드 리뷰 계획

**순서(위험도순)와 파일 × 범주 적용표** (범주: ①정확성 ②데이터 무결성 ③session_state 생명주기 ④이식성 ⑤cloud/local 분기 ⑥비밀·보안 ⑦UI 계약 ⑧테스트/CI 위생 ⑨문서 드리프트)

| 순서 | 파일 | 적용 범주 |
|---|---|---|
| 1 | data_loader.py | ①②⑨ |
| 2 | pages/research.py (step1·필터·_calc_stats·리셋 → step2~5) | ①②③④⑤⑥⑦⑨ |
| 3 | 전처리 find_columns / merge_campuses / calculate_rankings / process_in_memory | ①②④⑨ |
| 4 | app.py + components/sidebar.py (리셋·이벤트 경로) | ③⑤⑥⑦ |
| 5 | chart_generator.py, report_builder.py, gpt_reporter.py | ①④⑥⑦ |
| 6 | components/ 나머지 5개, pages/home·settings | ⑥⑦ |
| 7 | config.py, config/*.json, requirements·runtime·CI·installer·scripts, docs/README/CLAUDE.md | ④⑤⑥⑧⑨ |

**범주별 점검 대상(부록 C에 file:line)**: ① 계산식(1인당·증감률·순위 부호), 죽은 코드(중첩 버튼, 이중 pop, settings 라우트, get_region_universities), `except Exception` 6곳의 메시지 정확성, None/NaN 가드 ② 컬럼/키 계약 4곳 동시 수정 지점, 레거시 변환 누락 경로, 다중권역 중복 규칙, '전국순위' 의미, 3중 복제 ③ `_DEFAULTS` 밖 21키, 리셋 경로 3개 + 재로드, 위젯 키 삭제와 백업 ④ `Path.cwd()` 6곳, 폰트 OS 분기, 3.13+ deepcopy 전역 패치, pandas 2/3, 한글 파일명·NFC ⑤ `IS_CLOUD` 분기 6곳, 파일 쓰기 5곳 ⑥ 키 저장(.env 평문·session_state), 오류 메시지 키 노출, `unsafe_allow_html` 55곳 중 CSV 유래 문자열, traceback 화면 노출 2곳 ⑦ CSS 단일 소스, 하드코딩(버전 4·모델명 3·'충청권' 리터럴 8 + 기본 인자 11), `use_container_width` 49곳 ⑧ e2e stale 단언, 훅 배선, CI ⑨ CLAUDE.md/README 경로·함수 수·CSV 포맷, CHECKLIST secrets, docstring(process_in_memory:655).

**보고서 행 템플릿**: | ID | 파일:줄 | 심각도(§5 기준) | 범주 | 증상 한 줄 | 근거 | 잠금 테스트 ID 또는 manual 항목 | 수정안 | 난이도 |

**완료 기준**: 7개 파일군 × 적용 범주 전부 체크, §5 17건 + 후보 74건 triage(확정/반박/보류) 완료, 모든 High·Medium이 테스트 ID 또는 manual 항목과 1:1.

## 7. 실행 단계 (승인 후)

| Phase | 내용 | 예상 소요 | 완료 기준 |
|---|---|---|---|
| 0 준비 | `.venv-qa`(결정 1 버전) 생성·gitignore; `tests/` 골격, `conftest.py`(6.2), `pytest.ini`, `requirements-dev.txt`; 하네스 가드 4개; APP-00 부팅 시간 측정 | 0.5일 | `pytest --collect-only` 성공, 가드 4개 통과, 부팅 wall time 기록 |
| 1 ★ 최소 QA + 백엔드 | §4 ★ 항목(약 40건)을 먼저, 이어서 ETL/data_loader/chart/report/gpt 나머지 U·C | 1.5일 | `failed 0, xpassed 0`, `xfailed == 잠금 개수`, characterization 전부 통과 |
| 2 실데이터 골든·통합 | ETL-C02, ETL-I01~I05, INT-01, INF-01/02 (@realdata) | 0.5일 | 통과(V01·V14 특성화 표기), 소요 < 2분 |
| 3 UI AppTest | components → app 셸 → research 흐름(결함 재현 R7-01~R7-07, R7-11/12 포함) | 1.5일 | apptest 스위트 < 5분(초과 시 P2를 @slow), 결함 잠금이 모두 xfailed |
| 3.5 리뷰 보고서 | §6.4 순서대로 수행 → `docs/QA_REVIEW_REPORT.md`, `tests/manual/CHECKLIST.md`, 수동 항목 실행·스크린샷 | 1일 | §6.4 완료 기준 |
| 4 수정 | **High 8 + Medium 8 = 16건 수정**(V11 제외) → 해당 xfail 제거·characterization 삭제 → 회귀. V01 수정 후 `output/*.csv`·xlsx 재생성 + 전후 diff 첨부. V14는 라벨 명시만(§결정 2). 헬퍼 추출(`_rank_delta_type`, `_save_api_key`)로 needs_refactor 해소. 문서 동기화(README/CLAUDE.md 경로·CSV 포맷·CHECKLIST secrets) | 2일 | V11 1건만 xfail로 남고 나머지 green, 재생성 diff가 2017 행에 한정 |
| 5 CI | `.github/workflows/test.yml`: ubuntu 단일 Python(결정 1), `apt fonts-nanum`, `pip install -r requirements.txt -r requirements-dev.txt`, `pytest -m "not live"` | 0.5일 | PR에서 green |
| 6 최종 검토 | advisor(Fable)에게 전체 산출물 검토 요청: 테스트가 실제 계약을 잠그는가, 수정 diff가 결함을 제거하고 새 회귀를 만들지 않았는가, 리뷰 보고서가 근거를 갖췄는가, 에이전트가 놓친 것은 무엇인가. 지적 사항은 즉시 반영 | 0.5일 | 검토 의견 전부 반영 또는 반영하지 않은 이유 기록 |

Phase 4의 설계 선택지(보고서에 기재, 결정 필요 없음): V12(2) 이전값 0 표기는 {'신규' 표기 / 집계 제외 / 0.0 유지+주석} 중 택1; V03 기본 권역은 {`detect_region(target)[0]` 자동 설정 / 필터 적용 강제} 중 택1; V02·V15 레거시 파일명은 `REGIONAL_CSV.name` 참조로 통일.

병렬화: Phase 1은 seam별 4개 에이전트(ETL / data_loader / chart+report / gpt), Phase 3은 3개(components / app 셸 / research 흐름). verifier 검증은 Phase 1 종료·Phase 3 종료 2회(`pytest -q` 요약과 xfail 목록이 증거). Phase 0·2·3.5는 명령 결과 자체가 증거.

각주: 어시스턴트 메모리(`~/.claude/projects/C--Users-----Desktop-Hoseo-Reasearch/memory/`)는 Phase 0에서 초기화하고 Phase마다 changelog/issues를 갱신한다. 프로젝트 CLAUDE.md:164의 옛 경로는 Phase 4 문서 동기화 대상.

## 8. 검증 방법 (End-to-End)

1. `.venv-qa` 안에서 `pytest -q -m "not realdata and not live"`: 요약이 **`failed 0, xpassed 0`, `xfailed == 결함 잠금 개수`**(strict xfail이 오늘 실패하면 xfailed로 집계되어 통과, 예상외 통과는 FAILED). 예산 < 3분.
2. `pytest -q -m realdata`: 특성화 골든 통과, < 2분.
3. `pytest -q tests/apptest`: < 5분. 결함 재현 항목이 모두 xfailed.
4. 시스템 Python(pandas 3.0.5)으로 1을 한 번 더 실행: 참고용, 실패 시 보고서에 기록만.
5. 수동: `streamlit run report_app/app.py` 후 `tests/manual/CHECKLIST.md` 실행(레거시 CSV 업로드 오류, 처음부터→재로드 크래시, 5→4 서술 소실, 툴바 정렬, 확대 모달, 다운로드) + 스크린샷.
6. `docs/QA_REVIEW_REPORT.md`의 모든 High·Medium 행에 테스트 ID 또는 manual 항목이 1:1로 있는지 최종 검사.

## 부록 A. session_state 키 40개와 리셋 매트릭스

`_DEFAULTS`(19): module, step, max_step, national_df, regional_df, selected_year, hoseo_trend, averages, rank_changes, yoy_changes, compare_data, charts, narrative_trend/comparison/regional/yoy, api_key, report_buf, data_source.

비포함(21) × 리셋 경로별 현재 동작(R7-12 기대값 표의 기초):

| 키 | 쓰는 곳 | 사이드바 리셋(실제) | step5 리셋 | 재로드 4경로 |
|---|---|---|---|---|
| data_loaded | research.py:630/669/727/769 | 잔존 | False | True |
| _raw_national_df / _raw_regional_df | :321-322 (최초 1회) | 잔존 | **None 대입(V05)** | 잔존(V17) |
| _filter_years / _filter_compare | :544-545 | 잔존 | **None 대입(V05)** | 잔존 |
| _filter_selected_univs / _filter_compare_group(읽는 곳 없음) | :546-547 | 잔존 | 잔존 | 잔존 |
| _target_university | :548 | 잔존 | **잔존** | 잔존(V17) |
| _target_region | :549 | 잔존 | None 대입 | 잔존 |
| _custom_compare_group | :557 | 잔존 | None | 잔존 |
| _saved_narrative_* (4) | :110 | 잔존 | **잔존(V06×V07)** | 잔존 |
| sidebar_api_change / sidebar_reset_clicked / _nav_module_clicked / _nav_step_clicked | sidebar.py | 플래그(pop 소비) | | |
| _chart_dialog_title / _buf / _df | chart_card.py:126-128 | 잔존 | 잔존 | 잔존 |
| max_step (`_DEFAULTS`이지만) | app.py:247 증가만 | 잔존(V04) | **잔존(V06)** | 잔존 |

위젯 키(자동 관리): _dialog_api_key, home_*, src_*, _filter_*_widget, _filter_base_year, _filter_target_univ, _filter_region_select, _univ_selector, upload_*, year_sel_*, gen_all, gen_narrative_*, zoom_*/dl_*, sidebar_mod_*/sidebar_step_*.

## 부록 B. 재사용·퇴역

- `e2e_test_full.py` → **이식**: import 케이스(parametrize 1개), data_loader 행복 경로(키를 권역*로 갱신), 차트 5종 PNG, build_report 3케이스, process_in_memory(@realdata, 컬럼 단언 갱신), requirements/.gitignore 위생. **퇴역**: 커스텀 러너, 정적 grep 계열(:531-605), HTTP 8502 검사, secrets.toml 템플릿 검사(항상 통과).
- `scripts/smoke_test.py` → SMOKE_CODE 첫 줄 제거 후 INF-06 대상. 나머지 훅 8개는 정적 리뷰만(미배선, 일부는 CLAUDE.md를 무한 성장시킴).
- 구 메모리 `~/.claude/projects/c--Users-----Desktop-IR---MCP/memory/*.md`(2026-03-10) → 아키텍처 참고, 일부 stale.

## 부록 C. 리뷰 대상 file:line (§6.4용)

- `Path.cwd()` 6곳: config.py:80, app.py:53, research.py:56, research.py:578, 전처리:783, 전처리:784
- 파일 쓰기 5곳: app.py:132-133(.env), research.py:585(Raw data mkdir), :607(xlsx 저장), :1330(reports mkdir), 전처리:786·:889-891(output)
- `IS_CLOUD` 분기 6곳: app.py:131, research.py:243, :584, :603, :613, :1329
- `except Exception` 6곳: research.py:634, :675, :730, :1177, :1345; gpt_section.py:136. traceback 노출: research.py:638, :679
- '충청권' 리터럴 8곳(research.py:95, :396, :699, :702, :709, :716, :759, :777) + 기본 인자 11곳(chart_generator:103/165/222/275, gpt_reporter:70/105/140/174, report_builder:104/144/242) + data_loader:83(정당) + config:88
- 버전 'v5.0' 4곳: sidebar.py:460, toolbar.py:45, settings.py:104, app.py:261. 모델명 'GPT-4o' 3곳: sidebar.py:460, gpt_section.py:128, app.py:262
- 미정의 CSS: toolbar.py:52-80의 `ir-toolbar-*` 10개. 인라인 중복: gpt_section.py:68-104의 `.ir-gpt-*` 7개 vs styles.py:376-418
- `unsafe_allow_html` 55곳/10파일(CSV 유래 문자열 유입: chart_card:106-107, gpt_section:108-109, metric_card:102-104, research.py:1354-1365). `use_container_width` 49곳/5파일
- 죽은 코드: research.py:671-673(중첩 버튼), app.py:185-190(리셋 블록), app.py:249-250(settings 라우트), data_loader.py:109-118(get_region_universities), config.py:68-75(REGION_MAP 미사용), chart_generator.py:37(COMPARE_GROUP import)
- 문서 드리프트: CLAUDE.md:18/59/72/139/164, README.md:73/80-86/96-100/110/182, docs/CHECKLIST:20-24/54-57/131-136/170-181/209-215, 전처리 docstring :655, scripts/memory_update_reminder.py:29
