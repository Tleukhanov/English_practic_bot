"""Тесты для лидерборда."""

import pytest

from bot.formatters import format_leaderboard
from storage.repo import LeaderboardRow


def _make_row(user_id: int, name: str, xp: int, lessons: int, streak: int = 0) -> LeaderboardRow:
    return LeaderboardRow(
        user_id=user_id,
        username=f"user{user_id}",
        first_name=name,
        level="B1",
        xp=xp,
        total_lessons=lessons,
        streak_days=streak,
    )


class TestFormatLeaderboard:
    def test_empty_leaderboard(self) -> None:
        result = format_leaderboard([], 1)
        assert "Пока никто не заработал XP" in result

    def test_single_user(self) -> None:
        rows = [_make_row(1, "Иван", 100, 5)]
        result = format_leaderboard(rows, 1)
        assert "Иван" in result
        assert "100 XP" in result
        assert "5 урок." in result

    def test_top_3_medals(self) -> None:
        rows = [
            _make_row(1, "Аня", 300, 10),
            _make_row(2, "Борис", 200, 7),
            _make_row(3, "Вера", 150, 5),
        ]
        result = format_leaderboard(rows, 99)
        assert "🥇" in result
        assert "🥈" in result
        assert "🥉" in result

    def test_position_outside_top_10(self) -> None:
        rows = [_make_row(1, "Аня", 300, 10)]
        result = format_leaderboard(rows, 99, current_user_position=23)
        assert "#23" in result

    def test_position_inside_top_10(self) -> None:
        rows = [_make_row(1, "Аня", 300, 10)]
        result = format_leaderboard(rows, 1, current_user_position=1)
        assert "📌" not in result

    def test_streak_displayed(self) -> None:
        rows = [_make_row(1, "Иван", 100, 5, streak=7)]
        result = format_leaderboard(rows, 1)
        assert "🔥 7" in result

    def test_no_streak_not_shown(self) -> None:
        rows = [_make_row(1, "Иван", 100, 5, streak=0)]
        result = format_leaderboard(rows, 1)
        assert "🔥" not in result

    def test_10_users(self) -> None:
        rows = [_make_row(i, f"User{i}", 100 - i * 10, 5 - i // 3) for i in range(1, 11)]
        result = format_leaderboard(rows, 99)
        assert "User1" in result
        assert "User10" in result


class TestLeaderboardRow:
    def test_defaults(self) -> None:
        row = LeaderboardRow()
        assert row.user_id == 0
        assert row.xp == 0
        assert row.total_lessons == 0
        assert row.streak_days == 0

    def test_fields(self) -> None:
        row = LeaderboardRow(
            user_id=42,
            username="test",
            first_name="Test",
            level="A2",
            xp=500,
            total_lessons=15,
            streak_days=10,
        )
        assert row.user_id == 42
        assert row.xp == 500
        assert row.streak_days == 10
