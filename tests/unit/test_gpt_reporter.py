"""report_app/gpt_reporter.py 단위·계약 테스트 (GPT-C01~C03, GPT-U01~U02).

네트워크 호출은 한 건도 하지 않는다. gpt_reporter 는 클라이언트를 스스로 만들지 않고
첫 위치 인자로 받으며(gpt_reporter.py:47, :66, :100, :136, :170) isinstance 검사도
없으므로, `.chat.completions.create(**kwargs)` 만 제공하는 대역(fake)으로 완전히
대체된다. 대역은 tests/fixtures/fake_openai.make_fake_client 하나만 사용한다.

이 파일이 고정하는 계약(contract):
    - _call_gpt 의 호출 형태와 반환값 가공(strip)
    - generate_* 4종이 만드는 user 프롬프트에 json.dumps 결과가 원문 그대로 실린다는 점
    - 대학명(university) 해석 순서: 인자 > 모듈 전역 UNIVERSITY
    - 방어 로직 부재(무방어)라는 현재 사실 (characterization)
    - 비교군 개수 하드코딩이라는 확정 결함 (xfail strict)
"""

from __future__ import annotations

import json

import httpx
import numpy as np
import openai
import pytest

import report_app.config as config
import report_app.gpt_reporter as gpt
from tests.fixtures.fake_openai import make_fake_client

# ===========================================================================
# 테스트 입력 데이터
#
# 모양(shape)은 data_loader 의 실제 반환값과 동일하게 맞춘다:
#   get_hoseo_trend()       -> {연도: {"논문수","전임교원수","1인당논문수","권역순위","전국순위"}}
#   get_averages()          -> {연도: {"전국평균","권역평균","비교군평균"}}
#   get_rank_changes()      -> {연도: {"권역순위","전국순위","권역순위_변화","전국순위_변화"}}
#   get_yoy_changes()       -> {"상위": [...], "하위": [...], "호서": {...}|None}
#   get_compare_group_data()-> [{"학교명","전임교원수","논문수","1인당논문수","전국순위","권역순위"}]
#
# 학교명·권역명은 전부 중립값(neutral value)을 쓴다. config 기본값('호서대학교',
# '충청권')이 데이터 내용으로 섞이면 "기본값이 안 쓰였다" 단언이 프롬프트 치환이
# 아니라 JSON 본문 때문에 깨진다.
# ===========================================================================

_YEAR = 2025
_REGION = "호남권"  # config 기본값 '충청권' 이 아닌 값이어야 치환 검증이 의미를 갖는다

_TREND: dict[int, dict] = {
    2024: {"논문수": 300.0, "전임교원수": 480, "1인당논문수": 0.625, "권역순위": 3, "전국순위": 70},
    2025: {"논문수": 330.5, "전임교원수": 477, "1인당논문수": 0.6929, "권역순위": 2, "전국순위": 61},
}

_AVERAGES: dict[int, dict] = {
    2024: {"전국평균": 0.5012, "권역평균": 0.4411, "비교군평균": 0.4802},
    2025: {"전국평균": 0.5233, "권역평균": 0.457, "비교군평균": 0.5011},
}

# 2024 는 직전 연도가 없어 변화량이 None 이다 (data_loader.py:253-254 와 동일한 모양).
_RANK_CHANGES: dict[int, dict] = {
    2024: {"권역순위": 3, "전국순위": 70, "권역순위_변화": None, "전국순위_변화": None},
    2025: {"권역순위": 2, "전국순위": 61, "권역순위_변화": 1, "전국순위_변화": 9},
}

_YOY: dict = {
    "상위": [
        {"학교명": "가나대학교", "증감률": 22.5, "기준연도": 0.8102, "비교연도": 0.6614},
        {"학교명": "다라대학교", "증감률": 11.0, "기준연도": 0.5551, "비교연도": 0.5001},
    ],
    "하위": [
        {"학교명": "사아대학교", "증감률": -18.3, "기준연도": 0.3011, "비교연도": 0.3685},
    ],
    "호서": {"학교명": "마바대학교", "증감률": 10.9, "기준연도": 0.6929, "비교연도": 0.625},
}

# 비교군 원소 3개 -> GPT-C03 의 '5개 대학' 하드코딩을 드러내는 입력.
_COMPARE_DATA_3: list[dict] = [
    {"학교명": "가나대학교", "전임교원수": 300, "논문수": 210.0, "1인당논문수": 0.7, "전국순위": 45, "권역순위": 1},
    {"학교명": "다라대학교", "전임교원수": 250, "논문수": 150.0, "1인당논문수": 0.6, "전국순위": 58, "권역순위": 2},
    {"학교명": "마바대학교", "전임교원수": 477, "논문수": 330.5, "1인당논문수": 0.6929, "전국순위": 61, "권역순위": 3},
]

_FUNC_NAMES = ["trend", "comparison", "regional", "yoy"]

# 함수별로 "프롬프트에 json.dumps 결과가 원문 그대로 실려야 하는" 객체 목록.
_EXPECTED_JSON_OBJECTS: dict[str, list] = {
    "trend": [_TREND, _AVERAGES],
    "comparison": [_COMPARE_DATA_3, _AVERAGES[_YEAR]],
    "regional": [_RANK_CHANGES, _TREND],
    "yoy": [_YOY["상위"], _YOY["하위"], _YOY["호서"]],
}


def _invoke(func_name: str, client, *, university=None, region_name: str = _REGION) -> str:
    """generate_* 4종을 동일한 시그니처로 부르는 어댑터(adapter).

    parametrize 로 4종을 한 테스트에서 다루기 위해 인자 차이(year 유무)를 여기서 흡수한다.
    """
    if func_name == "trend":
        return gpt.generate_trend_narrative(
            client, _TREND, _AVERAGES, university=university, region_name=region_name
        )
    if func_name == "comparison":
        return gpt.generate_comparison_narrative(
            client, _COMPARE_DATA_3, _AVERAGES, _YEAR, university=university, region_name=region_name
        )
    if func_name == "regional":
        return gpt.generate_regional_narrative(
            client, _TREND, _RANK_CHANGES, university=university, region_name=region_name
        )
    if func_name == "yoy":
        return gpt.generate_yoy_narrative(
            client, _YOY, _YEAR, university=university, region_name=region_name
        )
    raise AssertionError(f"알 수 없는 함수 이름(func_name): {func_name}")


# ===========================================================================
# GPT-C01 : _call_gpt 호출 계약
# ===========================================================================

def test_gpt_c01_call_gpt_invocation_contract():
    """GPT-C01: _call_gpt 이 config 설정값으로 create 를 정확히 1회 키워드 인자로만 호출하고 content.strip() 을 반환한다."""
    client, completions = make_fake_client(content="  서술 본문입니다.  \n")

    result = gpt._call_gpt(client, "사용자 본문")

    assert len(completions.calls) == 1, f"create() 호출 횟수가 1이 아님: {len(completions.calls)}"

    call = completions.last_call
    # FakeCompletions.create(self, **kwargs) 에는 위치 슬롯(positional slot)이 하나도
    # 없다. 따라서 호출이 TypeError 없이 성공했다는 사실 자체가
    # "키워드 인자로만 호출됐다"는 증거다. 남은 일은 키 집합을 정확히 못 박는 것.
    assert set(call) == {"model", "messages", "max_tokens", "temperature"}, (
        f"create() 키워드 인자 집합이 계약과 다름: {sorted(call)}"
    )

    assert call["model"] == gpt.GPT_MODEL == "gpt-4o"
    assert call["max_tokens"] == gpt.GPT_MAX_TOKENS == 2000
    assert call["temperature"] == gpt.GPT_TEMPERATURE == pytest.approx(0.4)

    messages = call["messages"]
    assert len(messages) == 2, f"messages 길이가 2가 아님: {len(messages)}"
    assert messages[0] == {"role": "system", "content": gpt._SYSTEM_PROMPT}, (
        "messages[0] 이 system 프롬프트(_SYSTEM_PROMPT) 와 정확히 일치해야 한다"
    )
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "사용자 본문", "user 본문은 인자 그대로 전달돼야 한다"

    assert result == "서술 본문입니다.", "반환값은 content.strip() 이어야 한다"


def test_gpt_c01_system_prompt_is_shared_by_all_generators():
    """GPT-C01: generate_* 4종 모두 동일한 _SYSTEM_PROMPT 를 system 메시지로 보낸다."""
    for func_name in _FUNC_NAMES:
        client, completions = make_fake_client()
        _invoke(func_name, client)
        assert completions.last_system_prompt == gpt._SYSTEM_PROMPT, (
            f"{func_name} 의 system 프롬프트가 _SYSTEM_PROMPT 와 다르다"
        )


# ===========================================================================
# GPT-C02 : 프롬프트 직렬화 계약
# ===========================================================================

@pytest.mark.parametrize("func_name", _FUNC_NAMES)
def test_gpt_c02_prompt_embeds_json_dumps_verbatim(func_name: str):
    """GPT-C02: generate_* 4종의 user 프롬프트에 json.dumps(obj, ensure_ascii=False, indent=2) 결과가 부분 문자열로 그대로 들어간다."""
    client, completions = make_fake_client()

    result = _invoke(func_name, client)
    assert result == "고정 응답"

    prompt = completions.last_user_prompt

    for obj in _EXPECTED_JSON_OBJECTS[func_name]:
        dumped = json.dumps(obj, ensure_ascii=False, indent=2)
        assert dumped in prompt, (
            f"{func_name} 프롬프트에 직렬화 결과가 원문 그대로 들어있지 않다.\n"
            f"기대 조각:\n{dumped}\n실제 프롬프트:\n{prompt}"
        )

    # 대학명·권역명 치환 확인 (university 미지정 -> 모듈 전역 UNIVERSITY)
    assert gpt.UNIVERSITY in prompt, f"{func_name} 프롬프트에 대학명이 없다"
    assert _REGION in prompt, f"{func_name} 프롬프트에 권역명({_REGION})이 없다"

    # 연도 인자를 받는 두 함수만 기준연도가 본문에 노출된다.
    if func_name in ("comparison", "yoy"):
        assert f"{_YEAR}년" in prompt, f"{func_name} 프롬프트에 기준연도({_YEAR})가 없다"
    if func_name == "yoy":
        assert f"{_YEAR - 1}년" in prompt, "yoy 프롬프트에 직전 연도(year-1)가 없다"


@pytest.mark.characterization
def test_gpt_c02_missing_year_in_averages_becomes_empty_object():
    """GPT-C02(특성화): averages 에 기준 연도 키가 없으면 프롬프트에 '{}' 가 들어가고 예외는 나지 않는다."""
    client, completions = make_fake_client()

    # 2099 는 _AVERAGES 에 없는 연도 -> averages.get(year, {}) 가 {} 로 폴백(gpt_reporter.py:125)
    gpt.generate_comparison_narrative(
        client, _COMPARE_DATA_3, _AVERAGES, 2099, region_name=_REGION
    )

    prompt = completions.last_user_prompt
    assert "평균 데이터(2099년):\n{}" in prompt, (
        f"누락 연도에 대한 폴백이 '{{}}' 가 아니다.\n실제 프롬프트:\n{prompt}"
    )


def test_gpt_c02_none_values_serialize_to_json_null():
    """GPT-C02: rank_changes 값에 None 이 있어도 json 직렬화되어 프롬프트에 'null' 로 들어간다."""
    client, completions = make_fake_client()

    gpt.generate_regional_narrative(client, _TREND, _RANK_CHANGES, region_name=_REGION)

    prompt = completions.last_user_prompt
    assert '"권역순위_변화": null' in prompt
    assert '"전국순위_변화": null' in prompt


def test_gpt_c02_yoy_none_hoseo_row_serializes_to_null():
    """GPT-C02: yoy_changes['호서'] 가 None 이면(권역 데이터 부재) 프롬프트에 'null' 만 들어가고 예외가 없다."""
    client, completions = make_fake_client()
    empty_yoy = {"상위": [], "하위": [], "호서": None}

    gpt.generate_yoy_narrative(client, empty_yoy, _YEAR, region_name=_REGION)

    prompt = completions.last_user_prompt
    assert f"{gpt.UNIVERSITY} 증감 현황:\nnull" in prompt, (
        f"호서 행이 None 일 때 'null' 이 아니다.\n실제 프롬프트:\n{prompt}"
    )
    assert "증감률 상위 3개 대학:\n[]" in prompt


# ===========================================================================
# GPT-C03 : 비교군 개수 하드코딩 (확정 결함 -> xfail strict)
# ===========================================================================

@pytest.mark.xfail(
    strict=True,
    reason="GPT-C03 (plan.md:126, V번호 미배정): 비교군 개수가 '5개 대학' 으로 하드코딩 (gpt_reporter.py:128)",
)
def test_gpt_c03_compare_group_size_must_not_be_hardcoded():
    """GPT-C03: compare_data 가 3개면 프롬프트에 '비교군 5개 대학' 이 없어야 한다(고쳐진 뒤의 기대 동작)."""
    assert len(_COMPARE_DATA_3) == 3, "이 테스트의 전제는 비교군 원소 3개다"

    client, completions = make_fake_client()
    gpt.generate_comparison_narrative(
        client, _COMPARE_DATA_3, _AVERAGES, _YEAR, region_name=_REGION
    )

    prompt = completions.last_user_prompt
    assert "비교군 5개 대학" not in prompt, (
        "비교군이 3개인데 프롬프트가 '비교군 5개 대학' 이라고 단정한다. "
        "개수는 len(compare_data) 에서 와야 한다."
    )


# ===========================================================================
# GPT-U01 : 오류 경로 (특성화 — 방어 로직 부재)
# ===========================================================================

@pytest.mark.characterization
def test_gpt_u01_empty_choices_raises_indexerror():
    """GPT-U01(특성화): choices 가 빈 리스트면 IndexError 가 그대로 난다 — 방어 로직이 없다는 사실 자체를 기록한다."""
    client, _ = make_fake_client(choices=[])

    with pytest.raises(IndexError):
        gpt._call_gpt(client, "본문")


@pytest.mark.characterization
def test_gpt_u01_none_content_raises_attributeerror():
    """GPT-U01(특성화): message.content 가 None 이면 .strip() 에서 AttributeError 가 난다 — 방어 로직이 없다는 사실 자체를 기록한다."""
    client, _ = make_fake_client(content=None)

    with pytest.raises(AttributeError):
        gpt._call_gpt(client, "본문")


@pytest.mark.characterization
@pytest.mark.parametrize(
    "make_error",
    [
        pytest.param(
            lambda: openai.APITimeoutError(
                httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            ),
            id="APITimeoutError",
        ),
        pytest.param(lambda: RuntimeError("임의의 전송 계층 오류"), id="RuntimeError"),
    ],
)
def test_gpt_u01_create_exception_propagates_unchanged(make_error):
    """GPT-U01(특성화): create() 가 던진 예외를 감싸지도 삼키지도 않고 그대로 전파한다 — 방어 로직이 없다는 사실 자체를 기록한다."""
    sentinel = make_error()
    client, _ = make_fake_client(raises=sentinel)

    with pytest.raises(type(sentinel)) as excinfo:
        gpt._call_gpt(client, "본문")

    # 동일 타입이 아니라 '같은 객체' 여야 래핑(wrapping)이 없다는 증명이 된다.
    assert excinfo.value is sentinel, "예외가 감싸져 다른 객체로 바뀌었다"


@pytest.mark.characterization
@pytest.mark.parametrize("func_name", _FUNC_NAMES)
def test_gpt_u01_generators_also_propagate_unchanged(func_name: str):
    """GPT-U01(특성화): generate_* 4종도 _call_gpt 의 예외를 그대로 올려보낸다 — 방어 로직이 없다는 사실 자체를 기록한다."""
    sentinel = RuntimeError("임의의 전송 계층 오류")
    client, _ = make_fake_client(raises=sentinel)

    with pytest.raises(RuntimeError) as excinfo:
        _invoke(func_name, client)

    assert excinfo.value is sentinel


# ===========================================================================
# GPT-U02 : 대학명 해석 순서 + numpy 스칼라 직렬화
# ===========================================================================

@pytest.mark.parametrize("func_name", _FUNC_NAMES)
def test_gpt_u02_default_university_comes_from_config(func_name: str):
    """GPT-U02: university=None 이면 config.UNIVERSITY 가 프롬프트에 쓰인다."""
    assert config.UNIVERSITY == "호서대학교", "이 테스트의 전제는 config 기본 대학명이다"

    client, completions = make_fake_client()
    _invoke(func_name, client, university=None)

    assert config.UNIVERSITY in completions.last_user_prompt, (
        f"{func_name} 프롬프트에 config 기본 대학명이 없다"
    )


@pytest.mark.parametrize("func_name", _FUNC_NAMES)
def test_gpt_u02_explicit_university_wins(func_name: str):
    """GPT-U02: university 를 지정하면 그 값이 쓰이고 config 기본값은 프롬프트에 나타나지 않는다."""
    client, completions = make_fake_client()
    _invoke(func_name, client, university="지정대학교")

    prompt = completions.last_user_prompt
    assert "지정대학교" in prompt, f"{func_name} 프롬프트에 지정 대학명이 없다"
    assert config.UNIVERSITY not in prompt, (
        f"{func_name} 프롬프트에 config 기본 대학명이 남아있다.\n실제 프롬프트:\n{prompt}"
    )


@pytest.mark.parametrize("func_name", _FUNC_NAMES)
def test_gpt_u02_module_level_university_is_followed(func_name: str, monkeypatch):
    """GPT-U02: gpt_reporter 모듈 전역 UNIVERSITY 를 바꾸면 university=None 일 때 그 값이 따라온다."""
    # gpt_reporter 는 `from ... import UNIVERSITY` 로 값을 자기 전역에 복사해 두고
    # 함수 안에서 그 전역을 읽는다(gpt_reporter.py:28, :82). 따라서 패치 지점은
    # report_app.config 가 아니라 report_app.gpt_reporter 다.
    monkeypatch.setattr(gpt, "UNIVERSITY", "패치대학교")

    client, completions = make_fake_client()
    _invoke(func_name, client, university=None)

    prompt = completions.last_user_prompt
    assert "패치대학교" in prompt, f"{func_name} 이 모듈 전역 UNIVERSITY 를 따르지 않는다"
    assert "호서대학교" not in prompt


def test_gpt_u02_module_level_university_restored_after_monkeypatch():
    """GPT-U02: 앞선 monkeypatch 가 새어나가지 않아 gpt.UNIVERSITY 가 config 값과 같다."""
    assert gpt.UNIVERSITY == config.UNIVERSITY == "호서대학교"


def test_gpt_u02_numpy_float_scalars_serialize_without_error():
    """GPT-U02: 데이터에 numpy 스칼라(np.float64)가 섞여도 json.dumps 가 성공하고 값이 프롬프트에 실린다."""
    trend = {
        2025: {
            "논문수": np.float64(330.5),
            "전임교원수": 477,
            "1인당논문수": np.float64(0.6929),
            "권역순위": 2,
            "전국순위": 61,
        }
    }
    averages = {
        2025: {
            "전국평균": np.float64(0.5233),
            "권역평균": np.float64(0.457),
            "비교군평균": np.float64(0.5011),
        }
    }

    client, completions = make_fake_client()
    gpt.generate_trend_narrative(client, trend, averages, region_name=_REGION)

    prompt = completions.last_user_prompt
    # np.float64 는 파이썬 float 의 하위 클래스라 json 표준 인코더가 그대로 처리한다.
    assert '"1인당논문수": 0.6929' in prompt
    assert '"논문수": 330.5' in prompt
    assert '"전국평균": 0.5233' in prompt
    assert '"비교군평균": 0.5011' in prompt


@pytest.mark.characterization
def test_gpt_u02_numpy_int_scalars_are_not_serializable():
    """GPT-U02(특성화): np.int64 는 json 표준 인코더가 처리하지 못해 TypeError 가 난다 — 직렬화 경계를 기록한다."""
    trend = {2025: {"전임교원수": np.int64(477)}}

    client, _ = make_fake_client()
    with pytest.raises(TypeError, match="int64"):
        gpt.generate_trend_narrative(client, trend, _AVERAGES, region_name=_REGION)
