import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
load_dotenv()
api_key = os.environ["LLM_API_KEY"]  

client = AsyncOpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=api_key,
)


CHUNKS = ["1. Порядок слов (SVO): Подлежащее + Глагол + Дополнение (I like apples).",
    "2. Наличие глагола: В любом предложении обязательно есть глагол; если нет действия, нужен 'to be' (She is a teacher).",
    "3. Согласование от 3-го лица: В Present Simple к глаголу для He/She/It добавляется -s/-es (He runs).",
    "4. Артикли: Используй 'a/an' для исчисляемых предметов впервые и 'the' для конкретных (A cat sit on the mat).",
    "5. Вспомогательные глаголы: Для вопросов и отрицаний нужны do/does/did/be/have (Do you know English? I do not know)."
    ]
CHUNK_VECTORS = None

async def init_vectors():
    global CHUNK_VECTORS
    CHUNK_VECTORS = await embed(CHUNKS)

async def embed(texts: list[str]) -> list[list[float]]:
  resp = await client.embeddings.create(
    model="text-embedding-3-small",
    input=texts,
  )
  return [item.embedding for item in resp.data]

def cosine(a: list[float], b: list[float]) -> float:
  dot = sum(x * y for x, y in zip(a, b))
  na = sum(x * x for x in a) ** 0.5
  nb = sum(y * y for y in b) ** 0.5
  # В исходном коде return имел неправильный отступ и вызывал
  # IndentationError. Проверка na и nb также защищает от деления на ноль.
  return dot / (na * nb) if na and nb else 0.0

async def retrieve(question: str, limit: int = 3) -> list[str]:
    if not question.strip() or limit <= 0:
        return []
    qv = (await embed([question]))[0]  # только вопрос!
    ranked = sorted(
        zip(CHUNKS, CHUNK_VECTORS),
        key=lambda item: cosine(qv, item[1]),
        reverse=True,
    )
    return [chunk for chunk, _ in ranked[:limit]]



def build_rag_prompt(question: str, chunks: list[str]) -> list[dict]:
  # Исправлена опечатка в названии promt: правильное английское слово — prompt.
  context = "\n\n".join(chunks)
  return [{"role": "system", "content": (
    "Отвечай СТРОГО по контексту ниже. "
    "В ответе укажи номер правила, откуда взял информацию. "
    "Если ответа нет в контексте — напиши ровно: НЕТ В КОНТЕКСТЕ. "
    "Запрещено придумывать свои примеры.\n\n"
    f"Контекст:\n{context}"
  )}, {"role": "user", "content": question}]

async def main():
  await init_vectors()
  question = "Приведи пример предложения с артиклями из правила"
  found = await retrieve(question)
  print("НАШЛИ ЧАНКИ:", found)
  messages = build_rag_prompt(question, found)
  resp = await client.chat.completions.create(model="openai/gpt-4o-mini",messages=messages,temperature=0.0)
  print(resp.choices[0].message.content)

asyncio.run(main())