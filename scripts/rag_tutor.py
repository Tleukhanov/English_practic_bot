"""RAG-тьютор v2: корпус грамматики + роутинг по порогу.

Архитектура (решение):
- RAG включается ТОЛЬКО когда вопрос похож на правило (score >= THRESHOLD).
  Иначе — обычный чат без отказа: бот остаётся собеседником, а не справочником.
- Примеры — по интересам ученика; если интересы неизвестны — классика из чанка.

Запуск:  python scripts/rag_tutor.py
Нужен LLM_API_KEY в .env (OpenRouter).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from openai import AsyncOpenAI

from bot.data.grammar_base import GRAMMAR_CHUNKS

load_dotenv()

CHAT_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")
EMBED_MODEL = "text-embedding-3-small"
TOP_K = 3
THRESHOLD = 0.30  # откалибровано: свои 0.35–0.56, чужие 0.15–0.24

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["LLM_API_KEY"],
)

CHUNK_VECTORS = None


async def embed(texts):
    resp = await client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def init_vectors():
    global CHUNK_VECTORS
    CHUNK_VECTORS = await embed([c["text"] for c in GRAMMAR_CHUNKS])


async def search(question, top_k=TOP_K):
    qv = (await embed([question]))[0]
    ranked = sorted(
        zip(GRAMMAR_CHUNKS, CHUNK_VECTORS),
        key=lambda item: cosine(qv, item[1]),
        reverse=True,
    )
    return [(chunk, cosine(qv, vec)) for chunk, vec in ranked[:top_k]]


def build_messages(question, profile, found):
    """Склейка: профиль (кто) + контекст (что)."""
    level = profile.get("level", "?")
    interests = profile.get("interests") or []
    if interests:
        examples_rule = (
            "Примеры строй на интересах ученика: " + ", ".join(interests) + ". "
            "Классические примеры из контекста НЕ приводи — придумай свои."
        )
    else:
        examples_rule = (
            "Интересы ученика неизвестны — используй классические примеры из контекста."
        )

    base = (
        f"Ты репетитор английского для русскоязычного ученика уровня {level}. "
        f"Отвечай по-русски. {examples_rule}"
    )
    if found:
        context = "\n\n".join(f"[{c['title']}] {c['text']}" for c in found)
        system = (
            base + " Отвечай СТРОГО по контексту ниже и укажи правило, откуда взял. "
            "Если ответа нет в контексте — скажи, что это вне материалов, и ответь коротко сам."
            f"\n\nКонтекст:\n{context}"
        )
    else:
        system = base + " Отвечай как обычно, дружелюбно и коротко."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


async def answer(question, profile):
    """Роутинг: похоже на правило → RAG, иначе → обычный чат."""
    hits = await search(question)
    best = hits[0][1] if hits else 0.0
    if best >= THRESHOLD:
        found = [c for c, _ in hits]
        mode = "rag"
    else:
        found = []
        mode = "chat"
    messages = build_messages(question, profile, found)
    resp = await client.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0.0
    )
    return resp.choices[0].message.content, mode, [(c["title"], round(s, 3)) for c, s in hits]


async def calibrate():
    """Подбор порога: смотрим score своих vs чужих вопросов."""
    probes_in = [
        "Объясни Present Perfect",
        "Когда ставится артикль the?",
        "Как построить вопрос в английском?",
    ]
    probes_out = [
        "Расскажи про Англию",
        "Какая столица Франции?",
        "Что такое фотосинтез?",
    ]
    print("--- СВОИ (должны быть высокие) ---")
    for q in probes_in:
        hits = await search(q, top_k=1)
        print(f"{hits[0][1]:.3f}  {q}  ->  {hits[0][0]['title']}")
    print("--- ЧУЖИЕ (должны быть низкие) ---")
    for q in probes_out:
        hits = await search(q, top_k=1)
        print(f"{hits[0][1]:.3f}  {q}  ->  {hits[0][0]['title']}")


async def main():
    await init_vectors()
    profile = {"level": "A1", "interests": ["football"]}
    for q in [
        "Объясни Present Perfect",
        "Расскажи про Англию",
    ]:
        text, mode, hits = await answer(q, profile)
        print(f"\n=== [{mode}] {q} ===")
        print("top:", hits)
        print(text)


if __name__ == "__main__":
    import sys as _sys

    async def _run():
        await init_vectors()
        if len(_sys.argv) > 1 and _sys.argv[1] == "calibrate":
            await calibrate()
        else:
            await main()

    asyncio.run(_run())
