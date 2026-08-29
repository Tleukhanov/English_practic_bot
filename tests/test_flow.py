from core.models import PracticeResult

from bot.flow import practice_markup
from bot.keyboards import lesson_keyboard


def test_practice_markup_reveal_when_incorrect_and_no_base():
    result = PracticeResult(is_correct=False, corrected_text="")
    markup = practice_markup(result)
    assert markup is not None
    assert markup.inline_keyboard[0][0].text == "🔍 Показать ошибку"


def test_practice_markup_none_when_correct():
    result = PracticeResult(is_correct=True, corrected_text="")
    assert practice_markup(result) is None


def test_practice_markup_keeps_lesson_keyboard():
    result = PracticeResult(is_correct=False, corrected_text="")
    base = lesson_keyboard()
    markup = practice_markup(result, base)
    assert markup is not None
    assert len(markup.inline_keyboard) == len(base.inline_keyboard) + 1
    assert markup.inline_keyboard[0][0].callback_data == "practice:reveal"


def test_practice_markup_binds_to_message_id():
    result = PracticeResult(is_correct=False, corrected_text="")
    markup = practice_markup(result, lesson_keyboard(), message_id=42)
    assert markup.inline_keyboard[0][0].callback_data == "practice:reveal:42"
