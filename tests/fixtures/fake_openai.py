"""OpenAI 클라이언트 대역(fake client).

gpt_reporter 는 클라이언트를 스스로 만들지 않고 첫 위치 인자로 받으며
(gpt_reporter.py:47, :66, :100, :136, :170) isinstance 검사도 없다.
따라서 `.chat.completions.create(**kwargs)` 하나만 제공하는
덕 타이핑(duck typing) 대역으로 완전히 대체할 수 있다.

코드가 실제로 만지는 경로:
    client.chat.completions.create(model=, messages=, max_tokens=, temperature=)
        -> .choices[0].message.content  (str)
"""

from __future__ import annotations

from types import SimpleNamespace


class FakeCompletions:
    """create() 호출을 기록하고 고정 응답(canned content)을 돌려준다."""

    def __init__(self, content="고정 응답", raises=None, choices=None):
        self.content = content
        self.raises = raises
        self._choices = choices
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        if self._choices is not None:
            return SimpleNamespace(choices=self._choices)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    # 편의 접근자 -------------------------------------------------------
    @property
    def last_call(self) -> dict:
        assert self.calls, "create() 가 한 번도 호출되지 않았다"
        return self.calls[-1]

    @property
    def last_user_prompt(self) -> str:
        messages = self.last_call["messages"]
        user = [m for m in messages if m["role"] == "user"]
        assert user, "user 메시지가 없다"
        return user[-1]["content"]

    @property
    def last_system_prompt(self) -> str:
        messages = self.last_call["messages"]
        system = [m for m in messages if m["role"] == "system"]
        assert system, "system 메시지가 없다"
        return system[-1]["content"]


def make_fake_client(content="고정 응답", raises=None, choices=None):
    """gpt_reporter 에 그대로 넘길 수 있는 대역 클라이언트를 만든다.

    Args:
        content: message.content 로 돌려줄 문자열. None 이면 그대로 None.
        raises: create() 가 던질 예외 인스턴스.
        choices: choices 리스트를 직접 지정 (빈 리스트로 IndexError 재현 등).

    Returns:
        (client, completions) 튜플. completions.calls 로 호출 인자 검사.
    """
    completions = FakeCompletions(content=content, raises=raises, choices=choices)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions
