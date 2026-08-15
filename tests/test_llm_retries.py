from unittest.mock import MagicMock

import pytest
from openai import RateLimitError

from providers.llm_openai import OpenAIChatProvider


def _failing_client(failures: int):
    state = {"n": 0}

    async def create(**kwargs):
        state["n"] += 1
        if state["n"] <= failures:
            raise RateLimitError("rate limited", response=MagicMock(), body=None)
        resp = MagicMock()
        resp.choices[0].message.content = "hello"
        return resp

    provider = OpenAIChatProvider(
        base_url="https://x.test",
        api_key="k",
        model="m",
        retries=3,
        backoff=(0.01, 0.01, 0.01),
    )
    provider._client.chat.completions.create = create
    provider._state = state
    return provider


async def test_no_retry_on_success():
    provider = _failing_client(failures=0)
    text = await provider.chat([{"role": "user", "content": "hi"}], temperature=0.5)
    assert text == "hello"
    assert provider._state["n"] == 1


async def test_retries_then_succeeds():
    provider = _failing_client(failures=2)
    text = await provider.chat([{"role": "user", "content": "hi"}])
    assert text == "hello"
    assert provider._state["n"] == 3


async def test_raises_after_exhausting_retries():
    provider = _failing_client(failures=99)
    with pytest.raises(RateLimitError):
        await provider.chat([{"role": "user", "content": "hi"}])
    assert provider._state["n"] == 4
