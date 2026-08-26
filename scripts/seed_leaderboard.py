"""Скрипт для добавления фейковых пользователей в лидерборд."""

import asyncio
import random
from datetime import datetime, timedelta

import aiosqlite

DB_PATH = "data/english_bot.db"

FAKE_USERS = [
    {
        "tg_id": 777000001,
        "username": "alex_dev",
        "first_name": "Alex",
        "level": "C1",
        "lessons": 85,
        "correct": 420,
        "errors": 30,
    },
    {
        "tg_id": 777000002,
        "username": "maria_k",
        "first_name": "Мария",
        "level": "B2",
        "lessons": 62,
        "correct": 310,
        "errors": 25,
    },
    {
        "tg_id": 777000003,
        "username": "dmitry_w",
        "first_name": "Дмитрий",
        "level": "B1",
        "lessons": 40,
        "correct": 180,
        "errors": 20,
    },
    {
        "tg_id": 777000004,
        "username": "anna_eng",
        "first_name": "Анна",
        "level": "A2",
        "lessons": 25,
        "correct": 100,
        "errors": 15,
    },
    {
        "tg_id": 777000005,
        "username": "sergey_p",
        "first_name": "Сергей",
        "level": "B1",
        "lessons": 18,
        "correct": 70,
        "errors": 10,
    },
]


async def main() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE tg_id >= 777000000 AND tg_id < 800000000"
        )
        existing = (await cursor.fetchone())[0]
        if existing > 0:
            print(f"Already {existing} fake users. Skipping.")
            return

        now = datetime.now()

        for user in FAKE_USERS:
            cursor = await db.execute(
                "INSERT INTO users (tg_id, username, first_name, level, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user["tg_id"], user["username"], user["first_name"], user["level"], now.isoformat()),
            )
            user_id = cursor.lastrowid

            topics = [
                "Travel Vocabulary", "Business English", "Daily Routines",
                "Past Tense Practice", "Conditionals", "Phrasal Verbs",
                "Idioms", "Pronunciation", "Reading Comprehension",
            ]

            for i in range(user["lessons"]):
                days_ago = random.randint(0, 60)
                lesson_date = (now - timedelta(days=days_ago)).isoformat()
                topic = random.choice(topics)

                cursor = await db.execute(
                    "INSERT INTO lesson_sessions "
                    "(user_id, topic, step, task_index, content_json, status, created_at, updated_at) "
                    "VALUES (?, ?, 5, 0, '{}', 'finished', ?, ?)",
                    (user_id, topic, lesson_date, lesson_date),
                )
                session_id = cursor.lastrowid

                await db.execute(
                    "INSERT INTO lesson_notes "
                    "(user_id, lesson_id, topic, vocabulary, grammar, speaking, mistakes, recommendation, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, session_id, topic, "6 words", "Past Simple", "Good", "", "Keep practicing", lesson_date),
                )

            for i in range(user["correct"]):
                days_ago = random.randint(0, 60)
                msg_date = (now - timedelta(days=days_ago)).isoformat()
                await db.execute(
                    "INSERT INTO messages (user_id, role, content, is_correct, created_at) "
                    "VALUES (?, 'user', 'test', 1, ?)",
                    (user_id, msg_date),
                )

            for i in range(user["errors"]):
                days_ago = random.randint(0, 60)
                msg_date = (now - timedelta(days=days_ago)).isoformat()
                await db.execute(
                    "INSERT INTO messages (user_id, role, content, is_correct, created_at) "
                    "VALUES (?, 'user', 'test', 0, ?)",
                    (user_id, msg_date),
                )

            xp = user["lessons"] * 10 + user["correct"] * 5 - user["errors"] * 2
            print(f"  {user['first_name']}: {xp} XP, {user['lessons']} lessons")

        await db.commit()
        print(f"Done. {len(FAKE_USERS)} fake users added.")


if __name__ == "__main__":
    asyncio.run(main())
