# 연구실적 분석 포털 — 코드 리뷰 및 컴포넌트 검증 보고서

| 항목 | 값 |
|---|---|
| 대상 | Hoseo-Research 연구실적 분석 포털 v5.0 |
| 범위 | Python 약 8,000줄 (중첩 사본 `전임교원_연구실적_학교별자료/` 591줄 제외) |
| 기준 환경 | `.venv-qa` (Python 3.11.9, pandas 2.3.3, streamlit 1.52.2, openai 2.14.0, python-docx 1.1.0) |
| 배포 환경 | Streamlit Community Cloud, `runtime.txt` = python-3.12 |
| 작성일 | 2026-09-14 |
| 계획 문서 | `plan.md` |

---

## 1. 요약

착수 시점에 자동 테스트는 0개였다. 기존 `e2e_test_full.py` 는 옛 컬럼명을 단언해
항상 실패했고 `scripts/smoke_test.py` 는 항상 NameError 로 끝났다. CI 에도 테스트
job 이 없었다.

이번 QA 에서 pytest 스위트를 신설하고 코드 리뷰를 수행해 **확정 결함 17건**을
찾았다. 심각도 분포는 High 8건, Medium 8건, Low 1건이다.

확정 결함의 뿌리는 셋이다.

1. **ETL 입력 가정 오류.** 2017년 원본 파일만 SCI/SCOPUS 열이 '남'·'여' 쌍이고
   '계' 열이 없다. 폴백이 '남' 열을 골라 2017년 128개교 전부가 과소 집계됐다.
   또한 등재 대상이 사립 134개교로 좁혀져 '전국순위' 가 전국 순위가 아니다.
   **추적 중인 `output/*.csv` 자체가 부정확하다.**
2. **세션 상태 설계 결함.** 리셋 경로 3개(사이드바·5단계·재로드)가 서로 다른 키
   집합을 초기화한다. 여기서 잘못된 권역 라벨, 크래시, GPT 서술 소실이 파생된다.
3. **레거시 파일명·컬럼의 하드코딩.** UI 문자열과 인스톨러 스크립트가 옛
   `충청권_순위.csv` 를 그대로 참조한다.

## 2. 검증 규모

| 계층 | 파일 | 통과 | xfail(결함 잠금) |
|---|---|---|---|
| 하네스 가드 | `tests/test_harness_guards.py` | 12 | 0 |
| 단위 | `tests/unit/` 8파일 | (§7) | (§7) |
| 계약 | `tests/contract/` 3파일 | (§7) | (§7) |
| 실데이터 골든 | `tests/integration/` | (§7) | (§7) |
| AppTest | `tests/apptest/` 3파일 | (§7) | (§7) |
| 수동 | `tests/manual/CHECKLIST.md` | 6영역 | — |

> `pytest.ini` 에 `xfail_strict = true` 를 설정했다. 결함 잠금 테스트는
> **오늘 반드시 실패**해야 하며, 예상외로 통과하면 실행이 FAILED 로 떨어진다.
> 따라서 "수정했다고 착각한 채 green" 이 되는 일이 구조적으로 불가능하다.

## 3. 심각도 기준

- **High** — 화면 또는 보고서의 수치가 틀리거나, 문서화된 경로에서 크래시·데이터 손실
- **Medium** — 라벨·표시 오류, 또는 우회 가능한 기능 불능
- **Low** — 외관·문서

## 4. 확정 결함 (V01~V17)

| ID | 심각도 | 위치 | 증상 | 잠금 테스트 |
|---|---|---|---|---|
| V01 | High | 전처리 `find_columns` :242-257 | 2017 Raw 만 SCI 그룹이 '남/여' 쌍(계 없음) → 폴백이 '남' 열 채택. 분자는 남성 논문수, 분모는 전체 교원. 2017년 128개교 전부 과소(합계 -17.6%, 116개교 순위 변동). 호서대 61.4167 → 정확값 77.3614 | ETL-U03(특성화), ETL-U04(xfail ×2) |
| V02 | High | research.py :682-731 | CSV 업로드 경로에 `_ensure_new_format` 없음. 화면이 안내하는 레거시 `충청권_순위.csv` 를 올리면 KeyError('권역순위') 가 "파일 읽기 오류" 로 오표기되고 진행 불가 | DL-U11(전제), R7-07(정적 AST xfail), R7-M01 |
| V03 | High | research.py :139 vs :95 | csv/existing 소스는 필터 없이 2단계 직행 → `region_name=None` → '권역평균' 이 6개 권역 전체 평균(2025: 0.2264, 실제 충청권 0.1781). YoY 상·하위가 전국 혼합인데 라벨·범례·프롬프트·보고서 제목은 '충청권' | R7-05(xfail), R7-13(xfail), FLT-01 |
| V04 | Medium | sidebar.py :203 vs app.py :185 | 사이드바가 같은 run 에서 `sidebar_reset_clicked` 를 먼저 pop → app.py 리셋 블록이 죽은 코드. '처음부터 다시' 가 home 이동만 하고 데이터·서술·max_step 을 남긴다 | UI-04(전제), R7-02(xfail), R7-12 |
| V05 | High | research.py :1401-1403 → :320-340 | 5단계 리셋이 `_raw_*_df` 등을 삭제 대신 None 대입 → 재로드 후 `_render_data_filter` :338 에서 `TypeError: 'NoneType' object is not subscriptable`. 매 rerun 반복 | R7-03(xfail), R7-12 |
| V06 | Medium | research.py :1383-1407 | 리셋이 `max_step` 을 초기화하지 않아 2~5단계가 '✓' 로 클릭 가능 → 2단계 TypeError, 3단계 AttributeError. 4·5단계는 "None년 / 0종" 오표시 | R7-04(xfail), R7-12 |
| V07 | High | research.py `_go` :108-117; app.py :202-204 | 4단계를 벗어난 run 종료 시 Streamlit 이 text_area 위젯 키를 제거 → 다음 `_go` 콜백의 `get` 이 '' 를 돌려주고 그 값이 백업을 덮는다. **4→5→4, 4→3→4 등 모든 왕복에서 서술 4개 소실.** 사이드바 이동은 백업조차 없어 서술 없는 Word 보고서가 만들어진다 | R7-01(3경로 xfail), R7-13(xfail) |
| V08 | High | chart_generator :176 | `create_comparison_bar` 가 '연도' 만 필터하고 `region_name` 은 제목 전용. V03 경로에서 6개 권역 140행을 "충청권 대학 비교" 로 그린다 | VIS-U04(xfail) |
| V09 | Medium | data_loader :253-254 vs research.py :826-830 | 부호 이중 반전. 개선(+N)이 빨간 `▼ +N계단`, 악화가 초록 `▲ -N계단` 으로 표시된다 | DL-U05(규약), R7-06(xfail) |
| V10 | Medium | data_loader :297 | 다중권역 대학 + `region_name=None` 에서 학교명 단일키 merge 가 cross-product 를 만든다(실데이터 2023 하위 3에 예원예술대 2회). trend/rank 는 '마지막 행 승리' 로 docstring 의 "첫 권역" 과 불일치 | DL-U10(xfail + 특성화) |
| V11 | Low | report_builder :81 | `lstrip('•-· ')` 가 줄 선두 음수 부호를 제거('• -0.5편 감소' → '0.5편 감소') | DOC-U04(xfail) — **이번 수정 범위 제외(결정 4)** |
| V12 | High | data_loader :298-317 | (1) merge 결과가 6행 미만이면 head(3)/tail(3) 이 겹쳐 **기본 경로(비교군 5개교)에서 호서대가 상위 3과 하위에 동시 출력**. (2) 이전값 0 이 "+0.0%" 로 나와 신규 실적이 무변화로 표기 | DL-U09(xfail ×2) |
| V13 | Medium | scripts/smoke_test.py :40; e2e_test_full.py | SMOKE_CODE 첫 줄이 try 밖에서 `Path`/`__file__` 참조 → 항상 NameError 후 exit 0. e2e 는 옛 키 단언·포트 8502 불일치로 매 실행 exit 1 | INF-06(xfail) |
| V14 | High | 전처리 `merge_campuses` :389-404 | 2025 기준 '대학교' 209행 중 57행 제외(국립 29·국립대법인 2·과기원 5·특별법국립 1·공립 1·사립 19) → 남는 134개교가 **100% 사립**. 전임교원 30.9% 누락. '전국순위/전국평균' 은 등재 사립 내 수치(호서대 77/134위 vs 전체 113/188위) | ETL-I04(특성화), ETL-I05(라벨 xfail) |
| V15 | Medium | build_windows.py :197,204; research.py :777 | 번들에 `권역별_순위.csv` 누락. 설치 직후 '기존 output/ 사용' 카드가 존재하는 파일을 "파일 없음: 충청권_순위.csv" 로 표시 | INF-05(xfail ×2) |
| V16 | Medium | docs/CHECKLIST :20-24 외 4곳 vs app.py :83 | 문서는 `[openai] api_key` 중첩 테이블, 코드는 평면 `st.secrets["OPENAI_API_KEY"]`. Streamlit 이 테이블을 env 로 내보내지 않아 폴백도 실패 → 키 '' | APP-02(특성화), INF-04(xfail) |
| V17 | Medium | research.py :320-322, :625-771 | 4개 로드 경로 모두 `_raw_*`·`charts`·`narrative_*`·`_target_university` 를 지우지 않는다. A 로드 후 B 재로드 시 필터에 A 원본, 3단계에 A 차트. V06×V07 연쇄로 이전 데이터의 서술이 새 보고서에 삽입된다 | R7-11(xfail), R7-12 |

### 4.1 연쇄 관계 (수정 순서)

- V03 이 V08·V10·V12 의 도달 경로다. V03 을 먼저 고쳐야 나머지 3건이 기본 경로에서 사라진다.
- V04·V05·V06·V17 은 "리셋 경로 3개가 서로 다른 키 집합을 초기화한다" 는 **한 원인**이다. 개별 패치가 아니라 단일 `reset_analysis_state()` 로 통합해야 한다.
- V02·V15 는 "레거시 파일명이 UI·스크립트 문자열에 하드코딩" 이라는 **한 원인**이다.
- V01·V14 는 ETL 입력 가정 문제이며, 추적 중인 `output/*.csv` 재생성을 요구한다.

## 5. 정적 확인 (드리프트 15건)

| # | 항목 | 결과 |
|---|---|---|
| D01 | research.py 1,410줄 거대 모듈 | 확인 |
| D02 | REGION_MAP 이중 정의(값 동일, config 쪽 미사용) | 확인 |
| D03 | `Path.cwd()` 6곳 | 확인 (config.py:80, app.py:53, research.py:56/:578, 전처리:783/:784) |
| D04 | 버전 문자열 하드코딩 4곳 | 확인 |
| D05 | 리셋 갭(비포함 키 21개, 5단계 리셋은 23키만) | 부분 확인 |
| D06 | 이벤트 플래그 이중 pop | 확인 (V04) |
| D07 | '호서' 하드코딩으로 데이터 손실 | **반박** — 딕셔너리 키 이름일 뿐 값은 대상 대학을 따른다 |
| D08 | `_call_gpt` 예외 무방어 | 확인 |
| D09 | gpt_section 인라인 CSS 7개가 styles.py 와 충돌 | 확인 |
| D10 | toolbar 미정의 CSS 클래스 10개 | 확인 |
| D11 | chart_card 래핑 불완전 | 확인 |
| D12 | pytest 인프라 부재 | 확인 (이번에 해소) |
| D13 | e2e 의 `hasattr` 목록에 `detect_region` 등 누락 | 부분 확인 |
| D14 | `process_in_memory` 3중 복제 | 확인 |
| D15 | CLAUDE.md/README 경로 드리프트 | 확인 |

## 6. 코드 리뷰 신규 발견

| ID | 파일:줄 | 심각도 | 증상 한 줄 | 수정 여부 |
|---|---|---|---|---|
| R-ETL-01 | 전처리.py:410-425 | High | 다중캠퍼스 대학이 전국 합산치로 충청권 순위에 참여해 왜곡 | 권고 |
| R-ETL-02 | 전처리.py:114,719 | High | 동일 연도 파일 2개면 경고 없이 1개만 사용 | 수정됨 |
| R-APP-01 | app.py:97-117, research.py:1383-1405 | High | 리셋 목록이 갈라져 대상대학 비교군이 안 지워짐 | 권고 |
| R-INF-01 | build_windows.py:177-180, build_macos.sh:108 | High | .streamlit 통째 복사로 로컬 시크릿이 배포물에 포함 | 수정됨 |
| R-RS-01 | research.py:511-516,552 | High | 필터 적용 시 권역평균이 비교군평균과 같아짐 | 수정됨 |
| R-RS-02 | research.py:437-440,488,500 | High | 비교군이 자기 자신 1개가 되는데 경고 없음 | 수정됨 |
| R-RS-03 | research.py:935-937 | High | 2단계 증감 안내가 현재에서 이전 순서로 역순 표시 | 수정됨 |
| R-ETL-03 | 전처리.py:106,676 | Medium | 로컬 클라우드 연도 정규식이 달라 같은 파일이 한쪽만 처리 | 수정됨 |
| R-ETL-04 | 전처리.py:389-398 | Medium | 개명 대학 6곳의 시계열이 중간 연도부터 시작 | 권고 |
| R-ETL-05 | 전처리.py:360 | Medium | 산업대학 2곳이 config에 대학으로 등록돼 전 연도 제외 | 권고 |
| R-ETL-06 | 전처리.py:868,501-509,741-745 | Medium | regions.json 27곳이 결과에 영향을 못 주는 죽은 설정 | 권고 |
| R-ETL-07 | 전처리.py:694-713,749-772 | Medium | read_excel export_csv를 인라인 복제해 3중 드리프트 위험 | 권고 |
| R-ETL-08 | 전처리.py:398, research.py:621-625 | Medium | 클라우드 경로에서 제외 경고가 화면에 표시되지 않음 | 권고 |
| R-APP-02 | app.py:47,249-250 | Medium | settings 라우트에 도달 불가해 전체가 죽은 코드 | 권고 |
| R-APP-03 | config.py:46, app.py:131-133, research.py:584-608 | Medium | IS_CLOUD 오탐 시 클라우드에서 로컬 전용 쓰기 경로 실행 | 권고 |
| R-APP-04 | app.py:261-262 외 4곳 | Medium | 버전 모델명 하드코딩으로 GPT_MODEL 변경이 화면에 미반영 | 권고 |
| R-VIS-01 | chart_generator.py:133,381 | Medium | 괄호 포함 대학명을 잘라 제목이 깨짐 | 권고 |
| R-DOC-01 | report_builder.py:55-62 | Medium | eastAsia 미설정으로 한글 본문이 기본 폰트로 렌더 | 수정됨 |
| R-DOC-02 | report_builder.py:315,340 | Medium | 비교군 이름이 상수 고정이라 보고서 제목과 불일치 | 권고 |
| R-GPT-04 | gpt_reporter.py:128 | Medium | 프롬프트에 5개 대학이 하드코딩돼 개수 변경 시 오표기 | 권고 |
| R-GPT-01 | gpt_reporter.py:47-57 | Medium | timeout 미지정으로 스피너가 최대 30분 가까이 블록 | 권고 |
| R-GPT-03 | gpt_reporter.py:49-58, config.py:94 | Medium | finish_reason 미검사로 잘린 서술이 경고 없이 삽입 | 권고 |
| R-VIS-02 | chart_generator.py:43-54 | Medium | py3.13 이상에서 deepcopy를 전역 교체하는 몽키패치 | 권고 |
| R-INF-02 | setup.iss:11 외 다수 | Medium | 설치본 버전 3.0 고정, 앱 UI는 v5.0로 3중 불일치 | 수정됨 |
| R-INF-03 | build_macos.sh:31-37 | Medium | 단일 아키 빌드라 Intel Mac이 DMG를 실행 못함 | 권고 |
| R-INF-04 | build_macos.sh:128-133 | Medium | 코드서명 공증이 없어 Gatekeeper가 실행을 차단 | 권고 |
| R-INF-05 | build_macos.sh:105-110, build_windows.py:196-201 | Medium | macOS 번들만 CSV 미복사로 설치 직후 데이터 0 | 권고 |
| R-INF-07 | config.py:80 | Medium | PROJECT_ROOT가 cwd 기준인데 주석은 파일 위치 기준이라 설명 | 권고 |
| R-INF-08 | requirements.txt:7 | Medium | matplotlib만 하한 고정이라 빌드마다 버전이 달라짐 | 수정됨 |
| R-INF-15 | README.md:99,110-113, CLAUDE.md:74 | Medium | 데이터 계약 문서가 폐기된 레거시 파일명으로만 기술 | 권고 |
| R-DL-01 | data_loader.py:138,149-166 | Medium | docstring은 첫 권역인데 실제는 마지막 행이 승리 | 권고 |
| R-RS-04 | research.py:1383-1407 | Medium | 2단계 리셋 키 목록에서 4종이 누락 | 수정됨 |
| R-RS-05 | research.py:744-749 | Medium | 레거시 CSV 폴백 없이 pd.read_csv를 직접 호출 | 수정됨 |
| R-RS-06 | research.py:1153-1155 | Medium | API 키 없으면 네비게이션 버튼까지 사라짐 | 권고 |
| R-RS-07 | research.py:671-673 | Medium | 중첩된 버튼을 눌러도 화면이 반응하지 않음 | 권고 |
| R-RS-08 | research.py:1162-1223 | Medium | 연도가 1개일 때 빈 YoY로 GPT 서술을 생성 | 권고 |
| R-RS-09 | research.py:634,675,730 | Medium | 통계 계산 실패가 파일 읽기 오류로 잘못 표시됨 | 권고 |
| R-RS-10 | research.py:698-703 | Medium | 업로더 라벨이 폐기된 파일명과 컬럼을 안내 | 권고 |
| R-DL-02 | data_loader.py:211-212 | Medium | 해당 연도 권역 데이터가 없으면 평균이 0.0으로 기록 | 권고 |
| R-RS-11 | research.py:491 | Medium | 비교군을 비워도 다음 rerun에 기본값이 되살아남 | 권고 |
| R-ETL-09 | 전처리.py:616-625 | Low | 조건부 CSV 기록이라 stale 파일이 남을 수 있음 | 권고 |
| R-ETL-10 | 전처리.py:655,764-772 | Low | process_in_memory 반환 컬럼 문서가 실제와 어긋남 | 권고 |
| R-ETL-11 | 전처리.py:783-784,786,889-891 | Low | 경로 기준이 파일 위치와 cwd로 혼재 | 권고 |
| R-APP-05 | config.py:68-75 | Low | REGION_MAP이 어디서도 참조 안 되는 사본으로 남음 | 권고 |
| R-APP-06 | app.py:53,129-134 | Low | .env 기록 경로가 cwd에 의존해 위치가 흔들림 | 권고 |
| V18 | chart_card.py:106-107 외 | Low | CSV 유래 대학명이 이스케이프 없이 HTML로 삽입 | 권고 |
| R-VIS-03 | chart_generator.py:86-92 | Low | savefig 예외 시 close 누락으로 Figure가 누적됨 | 권고 |
| R-VIS-04 | chart_generator.py:37 | Low | COMPARE_GROUP을 import만 하고 쓰지 않음 | 권고 |
| R-VIS-05 | chart_generator.py:256 | Low | 값이 전부 0이면 xlim(0,0)으로 축이 붕괴 | 권고 |
| R-VIS-06 | chart_generator.py:67-73 | Low | 폰트 파일이 없어도 강제 설정해 한글이 깨짐 | 권고 |
| R-VIS-07 | chart_generator.py:176 | Low | 단일 컬럼 불안정 정렬로 동점 막대 순서가 매번 바뀜 | 권고 |
| R-DOC-03 | report_builder.py:234,238 | Low | averages rank_changes 파라미터를 본문에서 미사용 | 권고 |
| R-GPT-02 | gpt_reporter.py:58 | Low | content가 None이면 AttributeError로 원인 파악 어려움 | 권고 |
| R-UI-05 | gpt_section.py:59,141 | Low | 상태 dot과 글자수가 갱신 전 값으로 계산됨 | 권고 |
| R-UI-06 | CLAUDE.md:150, gpt_section.py:52 | Low | 지침이 fragment 구조와 충돌하는 rerun을 지시 | 권고 |
| R-UI-08 | chart_card.py:48 | Low | 대괄호 접근이라 키 부재 시 KeyError 발생 | 권고 |
| R-UI-09 | settings.py:90 | Low | API Key를 앞 7자 뒤 4자로 화면에 노출 | 권고 |
| R-INF-06 | build_macos.sh:91 | Low | sed 치환이 무동작이며 전역 치환이라 위험 | 권고 |
| R-INF-09 | runtime.txt 외 6곳 | Low | 파이썬 버전 선언이 세 값으로 갈려 있음 | 권고 |
| R-INF-10 | create_icon.py:17-24 | Low | docstring은 Pillow라 하나 실제 구현은 순수 파이썬 | 권고 |
| R-INF-11 | scripts/log_change.py:60-78 | Low | 저장할 때마다 CLAUDE.md 로그가 무한히 증식 | 권고 |
| R-INF-12 | scripts/ 9개 스크립트 | Low | 훅 스크립트 9개가 어디에도 배선돼 있지 않음 | 권고 |
| R-INF-13 | README.md:73,182 | Low | 저장소명 오기와 Issues 죽은 링크 | 권고 |
| R-INF-14 | README.md:80-86, CLAUDE.md:58-63 | Low | 문서에 components pages 등 v5.0 UI 계층이 누락 | 권고 |
| R-INF-16 | CLAUDE.md:18,83,139,141,164 | Low | 경로 연도 루트명 등 5곳이 현실과 어긋남 | 권고 |
| R-INF-17 | tests/fixtures/tiny_png.py:43 | Low | 동일 바이트라 이미지 개수 기반 계측이 왜곡됨 | 권고 |
| R-RS-12 | research.py:1354-1365 | Low | CSV 유래 대학명이 이스케이프 없이 삽입됨 | 권고 |
| R-RS-13 | research.py:636-638,677-679 | Low | traceback이 화면에 그대로 노출됨 | 권고 |
| R-RS-14 | research.py 25곳+ | Low | use_container_width가 deprecated 상태로 다수 잔존 | 권고 |
| R-RS-15 | research.py:475 | Low | 빈 프레임에서 선택 키 조회 시 KeyError 발생 | 권고 |
| R-DL-03 | data_loader.py:109-118 | Low | get_region_universities를 프로덕션에서 호출하는 곳이 없음 | 권고 |
| R-RS-16 | research.py:1329-1330 | Low | output reports 폴더만 만들고 실제로 저장은 안 함 | 권고 |
| R-RS-17 | research.py:1269,1360 | Low | docstring이 실제 동작과 어긋나는 드리프트 | 권고 |

> **ID 중복 안내.** 두 리뷰 에이전트가 같은 결함에 다른 번호를 붙였다.
> `R-INF-01`(.streamlit 통째 복사) 과 `V22`(인스톨러 secrets 번들) 는 같은 건이고,
> `R-RS-04`(2단계 리셋 키 누락) 는 §9.1 의 리셋 통합에 흡수됐다.
> §9 의 건수는 이 중복을 제거한 뒤의 수치다.

## 7. 반박된 결함 후보

- builtin round의 뱅커 반올림이 1인당논문수를 틀리게 만든다: 2025년 134개교 전량에서 ROUND_HALF_UP과 차이가 0건이다.
- calculate_rankings가 NaN으로 IntCastingNaNError를 낸다: 앞단에서 항상 fillna 0.0이 선행돼 도달 불가하다.
- 빈 DataFrame에서 calculate_metrics가 터진다: pandas 2.3.3에서 빈 apply가 정상 처리돼 0행을 반환한다.
- .env 키가 오류 메시지로 에코된다: gpt_reporter.py는 api_key 문자열을 포함하지 않고 예외도 st.error로만 표시된다.
- 2016년 SCI 컬럼도 남 전용 값이다: 2016 파일은 계 남 여 하위헤더 자체가 없어 폴백이 정상 동작한다.
- 2017년 전임교원수도 남 전용 값이다: find_columns가 계 컬럼을 선택해 남 여 합산값을 쓴다.
- _DEFAULTS 19키 대비 세션키 21개가 정리되지 않는다: 대부분 위젯 키와 1회성 플래그라 리셋 대상이 아니다.
- _call_gpt에 에러 처리가 없어 크래시가 노출된다: 두 호출부 모두 broad except와 st.error로 포착한다.
- 저장소에 커밋된 자격증명이 있다: 스캔 결과 테스트 더미 2건뿐이고 실키 형태가 아니다.
- .gitignore가 .env와 시크릿을 못 덮는다: 실제로 .env와 시크릿 파일을 제외 처리하고 있다.
- requirements.txt 핀이 실제 설치본과 어긋난다: pip freeze 실측이 matplotlib만 빼고 전부 일치한다.
- deepcopy 몽키패치가 현재 배포에 영향을 준다: 배포 CI 설치본 세 타깃 모두 3.13 미만이라 비활성이다.
- IS_CLOUD가 정의만 되고 쓰이지 않는다: app.py와 research.py 여러 곳에서 실제로 분기한다.
- build_report가 averages와 rank_changes를 사용한다: 본문 전체에서 두 이름이 한 번도 등장하지 않는다.
- fake_charts가 report_builder 결함을 드러낸다: r:embed 5회로 차트 5장이 모두 정상 삽입된 것이 확인된다.
- installer의 build_windows.py에 앱 버전 3.0이 박혀 있다: 해당 파일엔 앱 버전 문자열이 없고 임베디드 파이썬 버전뿐이다.
- research.py:56의 Path.cwd()는 :54가 __file__ 기준으로 먼저 해석해 사실상 데드 코드다.
- IS_CLOUD 분기 6곳이 모두 정합한다: :1329의 스킵은 build_report가 BytesIO에만 쓰기 때문에 안전하다.
- bare except가 st.rerun()을 삼키지 않는다: RerunException은 BaseException을 상속한다.

## 8. 테스트 실행 결과

기준 환경은 `.venv-qa` 이다. 배포본과 같은 핀(pandas 2.3.3, streamlit 1.52.2,
openai 2.14.0, python-docx 1.1.0)을 쓴다.

```
pytest -q -m "not live"
328 passed, 12 xfailed in 19s        # 경고 0건
```

기존 커스텀 러너 두 개도 함께 살렸다(V13). 둘 다 착수 시점에는 어떤 코드
상태에서도 실패하게 되어 있어 회귀 신호가 되지 못했다.

```
# smoke_test.py 는 PostToolUse 훅이라 stdin 으로 JSON 페이로드를 받는다.
# 그냥 실행하면 빈 stdin 을 파싱하다 조용히 exit 0 으로 끝난다.
echo '{"tool_input":{"file_path":"report_app/data_loader.py"}}' | python scripts/smoke_test.py
[스모크 테스트 ✓] data_loader.py — OK: 1308행(전국) / 1368행(권역) / 10개년 / 차트 96287bytes

python e2e_test_full.py
PASS 50 / FAIL 0 / WARN 3            # exit 0
```

`e2e_test_full.py` 의 WARN 3건은 모두 환경 의존이다. 로컬 `secrets.toml`
부재(클라우드에서는 대시보드로 설정)와 Streamlit 서버 미기동 2건이다.
서버를 띄우지 않고 돌리는 것이 기본이므로 연결 거부는 FAIL 이 아니라
WARN 으로 바꿨다.

| 구분 | 착수 시점 | Phase 4 완료 |
|---|---|---|
| 자동 테스트 | 0개 | 340개 |
| passed | — | 328 |
| xfailed (의도적 잔존) | — | 12 |
| failed | 기존 러너가 항상 실패 | 0 |
| xpassed | — | 0 |

`pytest.ini` 에 `xfail_strict = true` 를 걸었다. 결함 잠금 테스트가 예상외로
통과하면 실행이 FAILED 로 떨어진다. 따라서 "고쳤다고 착각한 채 green" 이
구조적으로 불가능하다.

### 8.1 남은 xfail 12건은 의도적이다

| 대상 | 사유 |
|---|---|
| V11 불릿 음수 부호 | 사용자가 수정 제외를 명시적으로 결정 |
| V18 HTML 미이스케이프 3건 | 이번 수정 범위 밖 |
| D09 / D10 / D11 CSS 계약 3건 | 이번 수정 범위 밖 |
| 차트 Figure 누수 | 이번 수정 범위 밖 |
| 대학명 절단 2건 | 이번 수정 범위 밖 |
| GPT 프롬프트 "5개 대학" 고정 | 이번 수정 범위 밖 |
| 보고서 비교군 이름 고정 | 이번 수정 범위 밖 |

이 12건 중 하나라도 나중에 통과로 바뀌면, 어떤 수정이 의도한 범위를 넘어
다른 동작까지 건드렸다는 신호다.

## 9. Phase 4 수정 내역

실제로 고친 것은 **30건**이다. 사용자가 승인한 16건과, 코드 리뷰가 추가로
찾아낸 14건이다. 추가분은 모두 "화면이나 보고서에 잘못된 수치가 실린다" 는
승인 당시와 같은 기준을 충족하거나, 배포 산출물에 자격증명이 들어갈 수 있는
보안 문제다.

| 구분 | 건수 | ID |
|---|---|---|
| ① 사용자 승인 (2026-09-14) | 16 | V01~V10, V12~V17 |
| ② 리뷰 추가 — High | 5 | V22, R-RS-01, R-RS-02, R-RS-03, R-ETL-02 |
| ③ 리뷰 추가 — Medium | 9 | V19, V20, V21, R-RS-05, R-ETL-03, R-DOC-01, R-INF-02, R-INF-08, D15 |
| **합계** | **30** | |

> ②③ 은 사용자가 승인한 범위 밖이다. 개별적으로 되돌릴 수 있도록 티어를
> 나눠 두었다. 되돌린다면 해당 잠금 테스트도 함께 되돌려야 한다
> (`xfail_strict` 때문에 테스트만 남기면 실행이 FAILED 로 떨어진다).

### 9.1 세션 상태 리셋 통합

리셋 경로가 셋이었고 각자 다른 키 집합을 건드렸다. 사이드바 리셋, 5단계
'처음부터' 버튼, 데이터 재로드다. 이 하나의 원인에서 V04, V05, V06, V17,
R-RS-04 가 파생됐다.

`research.py` 에 `reset_analysis_state()` 하나를 두고 세 경로가 모두 이를
호출하게 했다. 핵심은 원본 프레임을 `None` 으로 덮지 않고 **키 자체를
삭제**하는 것이다. `None` 을 넣으면 `"key" not in session_state` 가드를
통과해 다음 렌더에서 `None` 을 인덱싱하다 TypeError 가 난다.

사이드바가 리셋 플래그를 같은 run 에서 먼저 소비하던 문제도 함께 고쳤다.
사이드바는 플래그를 들여다보기만 하고, 소비와 실제 리셋은 `app.py` 가 한다.

### 9.2 GPT 서술 소실

`_go()` 가 이동 방향과 무관하게 서술을 백업했다. 4단계를 벗어난 뒤의
콜백에서는 Streamlit 이 위젯 키를 이미 지운 상태라 빈 문자열이 멀쩡한
백업을 덮어썼다. 백업을 "현재 단계가 4일 때만" 수행하도록 바꿨다.

"빈 값이면 백업하지 않는다" 는 단축은 쓰지 않았다. 사용자가 의도적으로
섹션을 비운 경우를 조용히 되살려 버리기 때문이다.

사이드바로 단계를 옮길 때도 백업 경로를 거치게 했다. 이전에는 사이드바
이동에 백업 자체가 없어 4단계에서 5단계로 직행하면 서술 없는 보고서가
만들어졌다.

### 9.3 권역 평균 모집단

두 갈래가 있었고 각각 다른 잘못된 값을 냈다.

| 경로 | 수정 전 2025 권역평균 | 정답 |
|---|---|---|
| 필터를 거치지 않음 | 0.2264 (전국 전체) | 0.1781 |
| 필터를 거침 | 0.1814 (체크된 5개교) | 0.1781 |

전자는 대상 대학의 권역을 자동 감지해 계산과 화면 라벨이 같은 권역을
가리키게 했다. 후자는 통계용 프레임에서 체크 목록 필터를 뺐다. 체크
목록은 비교군 후보 선정과 미리보기에만 쓴다.

### 9.4 ETL 재생성

2017년 원본만 SCI/SCOPUS 열이 '남'과 '여' 쌍이고 '계' 열이 없다. 폴백이
'남' 열을 골라 분자는 남성 교원 논문수, 분모는 전체 교원수가 됐다.
두 열을 합산하도록 고쳤다.

재생성 전에 임시 디렉터리에서 먼저 돌려 차이를 분석했다. `(연도, 학교명)`
기준으로 값만 비교하면 **바뀐 연도는 2017년뿐**이다.

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 2017 SCI 논문수 합계 | 14360.5351 | 17424.9495 |
| 호서대 2017 SCI | 61.4167 | 77.3614 |
| 호서대 2017 1인당 | 0.1288 | 0.1622 |
| 2017 순위 변동 대학 | — | 128개교 중 116개교 |

정렬에 타이브레이커가 없어 동순위 행 순서가 환경마다 달랐다. 동순위
그룹 28개에 117행이 걸려 있었다. 모든 정렬의 마지막 키에 학교명을 붙여
재현 가능하게 만들었다. 이 덕분에 골든 비교 테스트가 이제 행 순서까지
단언할 수 있다.

### 9.5 전국순위의 의미는 바꾸지 않았다

`merge_campuses` 가 2025년 기준 209개 대학 중 57개를 제외한다. 국립 29,
국립대법인 2, 과기원 5, 특별법국립 1, 공립 1, 사립 19다. 남는 134개교는
**전원 사립**이고 전임교원의 30.9% 가 빠진다.

사용자 결정에 따라 순위 계산식과 등재 목록은 그대로 두었다. 대신
제외된 대학 수를 전처리 로그로 노출해 사용자가 모집단을 알 수 있게 했다.

같은 원칙을 다중캠퍼스 대학 문제에도 적용했다. 다중캠퍼스 대학이 전국
합산치로 여러 권역 순위에 동시 참여하는데, 이는 버그라기보다 대학 단위
지표를 캠퍼스별로 쪼갤 것인가라는 의미론 결정이다. 수치는 두고 이 보고서에
제한사항으로 기재한다.

### 9.6 보안

인스톨러 빌드 스크립트가 `.streamlit` 디렉터리를 제외 필터 없이 복사했다.
`.gitignore` 는 시크릿 파일을 git 에서만 막고 빌드는 막지 못한다. 배포
문서가 Cloud 용으로 실제 키를 시크릿에 넣으라고 안내하므로, 유지보수자가
로컬에 시크릿 파일을 만든 뒤 인스톨러를 빌드하면 배포 실행파일 안에 키가
들어간다.

**현재 이 저장소에는 시크릿 파일이 없어 유출된 키는 없다.** 경로만 열려
있던 잠재 결함이다. Windows 와 macOS 빌드 양쪽에서 제외하도록 고쳤고,
정적 검사로 잠갔다.

## 10. 테스트 하네스에서 발견해 고친 문제

테스트를 만드는 과정에서 스위트 자체의 신뢰성을 해치는 문제 셋을 찾았다.

**파일 단독 실행은 통과하는데 전체 실행에서 27건이 깨졌다.**
`PagesManager.uses_pages_directory` 가 클래스 전역이고 최초 생성 시 한 번만
정해진 뒤 리셋되지 않는다. 앱 진입점 옆에 `pages` 디렉터리가 있어서
그 플래그가 True 로 굳으면 이후 모든 함수 기반 AppTest 가 멀티페이지 경로로
빠져 죽는다. conftest 에 격리 픽스처를 넣어 해소했다.

이 조사에서 **프로덕션 결함 V21** 이 나왔다. 같은 메커니즘이 실제 앱에도
적용되어 사이드바에 자동 네비게이션 4개가 주입되고, 그중 셋은 빈 화면이다.

**경로 인자 없이 `pytest` 를 돌리면 스위트 전체가 죽었다.**
훅 스크립트 하나가 pytest 의 기본 수집 규칙에 걸리는 이름인데 모듈 본문에서
프로세스를 종료시킨다. 새로 만든 CI 워크플로가 정확히 그 형태로 실행하므로
그대로 뒀다면 첫 실행부터 깨졌을 것이다.

**한글 xfail 사유가 콘솔에서 전부 깨졌다.**
결함 번호를 훑는 요약 줄이 읽히지 않으면 스위트의 가치가 크게 떨어진다.
conftest 의 세션 시작 훅에서 터미널 리포터 스트림을 UTF-8 로 재설정했다.

## 11. 남은 작업

- 수동 검증: `tests/manual/CHECKLIST.md` 의 6개 영역. 브라우저, 파일 업로드,
  실제 GPT 호출, 인스톨러 빌드가 필요해 자동화할 수 없다.
- 권고로 남긴 결함 62건. §6 표 73행 중 "권고" 행이며, 심각도는
  High 2 / Medium 27 / Low 33 이다. High 2건은 둘 다 "무엇이 옳은가" 를
  사용자가 정해야 하는 의미론 결정이라 임의로 바꾸지 않았다.
  R-ETL-01 은 다중캠퍼스 대학을 캠퍼스별로 쪼갤 것인가의 문제이고
  (§9.5 의 V14 와 같은 성격이다), R-APP-01 은 "처음부터 다시" 가 대상 대학
  선택까지 지울 것인가의 문제다.
- `e2e_test_full.py` 의 퇴역 여부. 계획 부록 B 는 퇴역을 권고했지만, 이번에
  고쳐서 exit 0 이 됐으므로 일단 남겼다. pytest 스위트와 단언이 겹치므로
  유지 비용을 생각하면 다음 정리 때 없애는 편이 낫다.
- V21 의 잔여 위험: 설정으로 네비게이션 UI 만 숨겼다. 멀티페이지 실행 자체와
  `/home`, `/research`, `/settings` URL 은 남는다. 근본 해결은 디렉터리 개명이다.

## 12. 에이전트 산출물 평가

이 작업은 상당 부분을 서브에이전트에 나눠 맡겼다. 사용자가 "에이전트들이
잘했는지" 를 물었으므로, 단계별로 실제로 어땠는지 기록한다.

**테스트 작성 (Phase 1~3) — 좋았다.**
자기가 쓴 파일을 직접 돌려보고, 단언이 약하면 스스로 다시 조였다. 가장 좋은
판단은 ETL 담당이 한 것이다. ETL-U04 의 xfail 에 `raises=` 가 없으면
언패킹 `ValueError` 가 xfail 로 흡수되어 **V01 수정의 증거가 사라진다**는 것을
수정 전에 먼저 보고했다. 누가 시켜서 본 게 아니라 잠금 방향을 이해하고 있었다.

**코드 리뷰 — 발견은 좋았고 전달이 나빴다.**
찾아낸 것 자체는 실질적이었다. R-RS-01(필터 적용 시 권역평균이 비교군평균과
같아짐) 과 V22(인스톨러가 로컬 secrets 를 번들) 는 원래 계획에 없던 진짜
High 결함이다. 반면 3개 중 2개가 결과물 전달에 두 번 실패해서 파일로 직접
받아와야 했다.

**수정 (Phase 4) — 4개 중 3개가 새 결함을 넣었다.**

| 에이전트 | 넣은 결함 | 결과 |
|---|---|---|
| fix-infra | `data_csv_names()` 를 정의 없이 호출 | 인스톨러 빌드가 NameError 로 죽음 |
| fix-etl | `merge_campuses` 3-튜플 변환에서 호출부 1곳 누락 | ETL-I01/I02 (긍정 계약) 파손 |
| fix-dataloader | 증감률에 `None` 반환, 소비자 3곳 무방어 | `f"{None:+.1f}%"` TypeError |

셋 다 "완료" 보고를 냈다. 셋 다 보고를 믿지 않고 직접 돌려봤기 때문에 잡혔다.
fix-infra 는 파일 하나를 고친 뒤 멈춰서 나머지를 이어받아야 했다.

**오케스트레이션(나) — 중대한 실수 1건.**
"실패한 characterization 은 삭제" 라는 규칙을 기계적으로 적용해 ETL-I03
(`output/*.csv` 골든 회귀 테스트) 을 지웠다. 이 테스트는 틀린 게 아니라
기댓값이 낡았을 뿐이었다. 되살렸고, 행 순서 단언과 xlsx 시트 비교까지 더해
지우기 전보다 강하게 만들었다.

**결론.** 산출물이 믿을 만한 이유는 에이전트가 믿을 만해서가 아니라, 보고가
아니라 실행 결과를 증거로 삼았기 때문이다. 에이전트가 넣은 결함 3건은 모두
"완료" 보고 뒤에 숨어 있었고, 전부 직접 코드를 돌려서 찾았다.

## 13. 커밋되지 않은 변경

이 작업은 아직 하나도 커밋하지 않았다(사용자가 요청하지 않았다).
지금 상태에서 `git checkout .` 은 ETL 수정과 재생성한 `output/` 을 날리고,
`git clean` 은 테스트 스위트 전체를 날린다.

**수정된 추적 파일 24개**

| 묶음 | 파일 |
|---|---|
| 프로덕션 | `report_app/{app,data_loader,chart_generator,report_builder}.py`, `report_app/pages/research.py`, `report_app/components/sidebar.py`, `전임교원_연구실적_전처리.py` |
| 재생성 데이터 | `output/` 4개 (CSV 3 + xlsx 1) — §9.4 |
| 인스톨러·배포 | `installer/windows/{build_windows.py,setup.iss}`, `installer/macos/{build_macos.sh,launcher.sh}`, `.github/workflows/build-installer.yml`, `requirements.txt`, `.streamlit/config.toml`, `.gitignore` |
| 기존 러너 | `scripts/smoke_test.py`, `e2e_test_full.py` |
| 문서 | `README.md`, `CLAUDE.md`, `docs/CHECKLIST_StreamlitCloud_배포.md` |

**새 파일 6개**: `tests/`, `pytest.ini`, `requirements-dev.txt`,
`.github/workflows/test.yml`, `docs/QA_REVIEW_REPORT.md`, `plan.md`
