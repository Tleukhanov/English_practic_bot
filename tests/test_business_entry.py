"""Monetization/engagement entry-point tests: premium & wheel discoverability."""

from bot.keyboards import main_menu, premium_upsell_keyboard, main_menu_with_srs
from bot.handlers.onboarding import _done_text
from bot.handlers.start import HELP_TEXT


def test_main_menu_has_premium_button():
    kb = main_menu()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    premium = [b for b in buttons if b.callback_data == "premium:open"]
    assert premium, "меню должно содержать кнопку с callback_data premium:open"
    assert premium[0].text == "💎 Подписка"


def test_main_menu_with_srs_has_premium_button():
    kb = main_menu_with_srs(5)
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert any(b.callback_data == "premium:open" for b in buttons)


def test_premium_upsell_keyboard_has_buy_7():
    kb = premium_upsell_keyboard()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert any(b.callback_data == "premium:buy:7" for b in buttons)
    assert buttons[0].text == "💳 Купить подписку"


def test_done_text_mentions_wheel_and_premium():
    text = _done_text()
    assert "/wheel" in text
    assert "/premium" in text


def test_help_text_mentions_wheel_and_premium():
    assert "/wheel" in HELP_TEXT
    assert "/premium" in HELP_TEXT
