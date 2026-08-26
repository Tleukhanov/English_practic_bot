"""Добавить реального пользователя с 999999 XP."""

import asyncio
import random
from datetime import datetime, timedelta

import aiosqlite

DB_PATH = "data/english_bot.db"


async def main() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now()
        user_id = 1  # Napaleonwww

        lessons = 9999
        correct = 180003
        errors = 3
        xp = lessons * 10 + correct * 5 - errors * 2
        print(f"Target: {xp} XP")

        topics = ["Travel", "Business", "Grammar", "Vocabulary", "Speaking", "Idioms"]

        # Batch insert lessons
        lesson_values = []
        note_values = []
        for i in range(lessons):
            days_ago = random.randint(0, 365)
            lesson_date = (now - timedelta(days=days_ago)).isoformat()
            topic = random.choice(topics)
            lesson_values.append((user_id, topic, 5, 0, "{}", "finished", lesson_date, lesson_date))

        cursor = await db.executemany(
            "INSERT INTO lesson_sessions "
            "(user_id, topic, step, task_index, content_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            lesson_values,
        )

        # Get lesson IDs
        cursor = await db.execute(
            "SELECT id FROM lesson_sessions WHERE user_id = ? AND status = 'finished' ORDER BY id",
            (user_id,),
        )
        session_ids = [row[0] for row in await cursor.fetchall()]

        for sid in session_ids:
            note_values.append((user_id, sid, random.choice(topics), "6 words", "Grammar", "Good", "", "Keep it up", now.isoformat()))

        await db.executemany(
            "INSERT INTO lesson_notes "
            "(user_id, lesson_id, topic, vocabulary, grammar, speaking, mistakes, recommendation, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            note_values,
        )

        # Batch insert correct messages
        batch_size = 10000
        for start in range(0, correct, batch_size):
            end = min(start + batch_size, correct)
            msg_values = []
            for i in range(end - start):
                days_ago = random.randint(0, 365)
                msg_date = (now - timedelta(days=days_ago)).isoformat()
                msg_values.append((user_id, "user", "test", 1, msg_date))
            await db.executemany(
                "INSERT INTO messages (user_id, role, content, is_correct, created_at) VALUES (?, ?, ?, ?, ?)",
                msg_values,
            )
            print(f"  Messages: {end}/{correct}")

        # Error messages
        for i in range(errors):
            days_ago = random.randint(0, 365)
            msg_date = (now - timedelta(days=days_ago)).isoformat()
            await db.execute(
                "INSERT INTO messages (user_id, role, content, is_correct, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, "user", "test", 0, msg_date),
            )

        await db.commit()
        print(f"Done! {xp} XP for user {user_id}")


if __name__ == "__main__":
    asyncio.run(main())
