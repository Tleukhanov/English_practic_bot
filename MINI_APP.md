# Telegram Mini App: «живой» урок вместо текстовой ленты

Архитектурный план перехода интерфейса урока с текстовых сообщений и inline-кнопок на
Telegram Mini App (WebApp), где ИИ генерирует презентацию-урок: слайды, карточки слов,
интерактивный квиз и ролевой диалог с персонажем.

Статус: реализованы этапы 1–6 (код + 456 тестов). Осталось только «вживую»:
запустить туннель (этап 0), задать `WEBAPP_URL`, поднять бота и гонять из Telegram.

---

## 1. Проблема

Сейчас урок — это цепочка текстовых сообщений + inline-кнопки «Дальше / Завершить».
LLM уже генерирует структурированный JSON (`LessonContent`: intro, vocabulary, grammar,
slides, tasks), но визуально всё упирается в формат чата:

- слайды — это плоский текст, не «презентация»;
- проверка знаний — только открытые вопросы без обратной связи;
- словарь — текстовый список, нет карточек и озвучки;
- персонаж — только текст сообщения.

Mini App решает это: бот отправляет кнопку, Telegram открывает полноэкранную веб-страницу,
бэкенд отдаёт расширенный «дек» урока, фронт рендерит интерактивные экраны. Весь код на
Python остаётся: генерация, квота, прогресс, SQLite.

## 2. Поток (как это выглядит)

1. Юзер жмёт в боте кнопку «📖 Урок в Mini App» (или `/lesson` → inline `web_app`).
2. Открывается WebApp (HTTPS-URL из `WEBAPP_URL`), Telegram передаёт `initData`.
3. Фронт шлёт `POST /api/deck/new` (тема выбрана на экране меню или подхвачена из плана).
4. Бэкенд: валидация `initData` → `quota.consume(cost=1)` → LLM генерит deck (JSON) →
   сохраняет `lesson_session` (mode=`miniapp`) → возвращает deck фронту.
5. Юзер проходит экраны: Презентация → Карточки → Квиз → (Диалог) → Финиш.
6. `POST /api/deck/finish`: сохранение ответов, score, SRS-апдейт, XP/достижения,
   проверка плана уроков (`_maybe_generate_plan`), отметка finished.
7. Чат-версия урока в боте остаётся (режим `mode=chat` по умолчанию).

## 3. Схема данных (SQLite, миграции в `storage/sqlite.py`)

Расширяем существующую `lesson_sessions`, не плодим параллельные сущности прогресса.

- `lesson_sessions.mode TEXT NOT NULL DEFAULT 'chat'` — `chat` | `miniapp`;
- `lesson_sessions.content_json` — теперь может содержать **deck** (см. §6);
- `lesson_sessions.score_json` (TEXT, NULL) — результаты квиза `[{quiz_index, chosen, correct}]`;
- `lesson_sessions.deck_preset TEXT` — какой пресет брали (`presentation`, `dialogue`, `mixed`).
- Таблица `audio_answers`:
  `id, session_id REFERENCES lesson_sessions, word TEXT, audio_file TEXT, transcript TEXT, rating INT`.

Слова из deck после `finish` попадают в существующий SRS/«Повторить слова» — отдельной
таблицы не нужно (переиспользуем списание `srs_review`).

Миграция — обычным `_migrate()` паттерном проекта (ALTER TABLE + проверка колонок).

## 4. Backend: aiohttp-сервер в том же процессе

aiogram уже тянет aiohttp, новых зависимостей нет. Поднимаем `aiohttp.web.AppServer`
на отдельном порту (`WEBAPP_PORT`, по умолчанию 8081) вместе с поллингом в
`bot/main.py` в одной `async with`-зону.

```
config:
  WEBAPP_URL=https://<tunnel>.trycloudflare.com   # публичный HTTPS
  WEBAPP_PORT=8081
```

Маршруты:

| Method & Path          | Назначение |
|---|---|
| `GET /` и `/assets/*`  | Статика Mini App (пакет `web/`) |
| `POST /api/init`       | Проверка `initData`, возврат `{user_id, level, quota_left, character, interests}` |
| `POST /api/deck/new`   | Генерация deck (тема/пресет), сохранить session, вернуть deck |
| `POST /api/deck/answer`| Ответ квиза: мгновенная правка (`correct/explanation`) + запись в `score_json` |
| `POST /api/deck/finish`| Финал: SRS, XP, достижения, план, `status=finished` |
| `POST /api/tts`        | Озвучка слова/фразы (edge-tts) → mp3 |
| `POST /api/voice/answer` | Голосовая реплика: аудио → STT (faster-whisper) → оценка фразы → `audio_answers` |
| `GET  /api/health`     | healthcheck (нужен туннелю/мониторингу) |

**initData (обязательно):** на каждый `POST` фронт передаёт `initData` (Telegram.WebApp.initData).
Валидация:
1. `data_check_string = sorted(params)` по алфавиту `k=v`, склеить через `\n`, исключая `hash`.
2. `secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)`.
3. `hash = HMAC_SHA256(key=secret_key, msg=data_check_string).hexdigest()`.
4. Сравнить с `hash` из initData (`hmac.compare_digest`), иначе 401.
5. `user = json.loads(initData["user"])` — `id` = `user_id` в боте.

Такой же secret_key позволяет валидировать initData для webhook (без запроса к Telegram).
Не передавать bot token во фронт ни в каком виде.

## 5. Frontend: ванильный SPA без сборки

Пакет `web/`: `index.html`, `app.js`, `style.css`. Бэкенд отдаёт как статику.

Интеграция с Telegram (`window.Telegram.WebApp`):
- `ready()`, `expand()` при старте; `themeParams` (тёмная тема, accent_color) через CSS-переменные;
- `HapticFeedback` (impact/notification) на проверку квиза и перелистывание;
- контроль закрытия: если deck не финализирован — `setClosingConfirmation(true)`, сброс — `sendData`.

Экраны (роутинг внутри одного `#app` div, без сторонних библиотек):

1. **Menu**: приветствие, уровень, оставшаяся квота, персонаж, интересы; выбор темы
   (3 из генератора тем / из плана уроков) или «случайная»; кнопка «🚀 Начать урок».
2. **Loading**: спиннер + «ИИ готовит твой урок…»; уходит после получения deck.
3. **Presentation**: полноэкранные слайды (обложка → N слайдов), тап/стрелки/свайп,
   прогресс-дотсы, emoji-акценты. Соответствует пресету `presentation`.
4. **Cards**: карточки слов (слово → перевод, пример, транскрипция), кнопка 🔊 TTS,
   флип-анимация, «знаю / повторю» (влияет на SRS).
5. **Quiz**: вопросы с вариантами, мгновенная подсветка правильного + короткое объяснение,
   прогресс-бар и счёт. Ответы уходят в `/api/deck/answer`.
6. **Dialogue**: реплики персонажа (левая/правая колонки), юзер выбирает фразу из вариантов —
   сценка развивается, движок диалога — просто deck-структурой, без диалогового агента.
7. **Finish**: score, XP, слова в «Повторить», следующий шаг из плана, кнопка «Ещё урок».

Состояние фронта — в памяти JS (deck + answers). Переживание рестарта — серверное
(фреш старт по `POST /api/deck/new`).

## 6. Генерация контента: «дек» урока

Новый модуль `core/deck.py` (аналог `core/lessons.py`), тот же трёхшаговый стиль,
но цель — цельный JSON одной генерацией `generate_deck(...) -> Deck | None` (безопасный
парсинг, как фикс-рейзер `lesson_content_from_json`).

Схема deck (пример):

```json
{
  "title": "Coffee Around the World",
  "subtitle_ru": "Путешествие по кофейным традициям",
  "preset": "mixed",
  "emoji": "☕",
  "slides": [
    {"headline": "Why coffee?", "body": "Coffee is the most popular morning drink.",
     "emoji": "🌅"},
    {"headline": "Espresso in Italy", "body": "Italians drink espresso standing at the bar.",
     "emoji": "🇮🇹"}
  ],
  "vocabulary": [
    {"word": "brew", "translation": "заваривать", "example": "I brew coffee every morning.",
     "transcription": "/bruː/"}
  ],
  "quiz": [
    {"question": "What does 'brew' mean?", "options": ["заваривать", "пить", "глотать"],
     "answer_index": 0, "explanation_ru": "to brew — заваривать напиток"}
  ],
  "dialogue": {
    "scene_ru": "Ты в римской кофейне у прилавка.",
    "lines": [{"character": "Barista", "line": "Ciao! Un caffè?"}],
    "choices": [{"line": "Yes, please! Can I have a cappuccino?", "next": 1}]
  }
}
```

Пресеты (`deck_preset`): `presentation`, `cards`, `quiz`, `dialogue`, `mixed` (по умолчанию).
Персонаж подмешивается в текст слайдов и реплики диалога. Правила уровня и языка — как в
текущих промптах (слайды/вопросы/примеры на английском, объяснения на русском).

Квота: `deck/new` = `cost=1` (одна LLM-генерация деки вместо трёх шагов урока).

## 7. Интеграция с существующим

| Система | Что делаем |
|---|---|
| **Quota** (`bot/quota.py`) | `consume(cost=1)` на `deck/new`; остаток квоты показываем на экране Menu |
| **План уроков** (`core/lesson_plan`) | после `finish` вызывается та же `_maybe_generate_plan`; тема из плана — одним из 3 предложений в Menu |
| **SRS / Review** (`core/srs.py`) | слова из deck после finish уходят в SRS; видны в `/review` |
| **Достижения/XP/лидерборд** | `finish` = обычный finished-урок: `record_lesson`, achievements, leaderboard |
| **Персонаж** (`core/characters.py`) | используется в презентации и диалоге |
| **TTS** (edge-tts) | 🔊 на карточках слов → `POST /api/tts` |
| **STT** (faster-whisper) | `POST /api/voice/answer` — аудио с устройства юзера, оценка по близости фразы |
| **Kaspi/promo/premium** | без изменений; квота-апселл при 0 осталось на экране Menu |

## 8. Безопасность

- Никаких токенов во фронте; initData валидируется на бэке каждого POST (HMAC, §4).
- `user_id` берём ТОЛЬКО из проверенного initData, не из тела запроса.
- Ограничение частоты: web-эндпоинты — поверх существующего `LLMThrottle`/`rate_limit`.
- Размер аудио на `voice/answer` ≤ `MAX_VOICE_DURATION_SEC` (60с), валидация content-type.
- Ошибки API — JSON `{ok, error}`, лаконичные сообщения, никаких стектрейсов во фронт.

## 9. План работы (этапы и критерии)

**Этап 0 — Туннель.** cloudflared quick tunnel на порт 8081. Критерий: `GET /api/health`
отвечает по HTTPS извне. Настройка `WEBAPP_URL` в `.env`.

**Этап 1 — Каркас + валидация.** aiohttp-server в `bot/main.py`, статика `web/`,
`POST /api/init`, кнопка WebApp в боте (`/lesson` и стартовое меню). Критерий: бот
открывает Mini App, `/api/init` возвращает корректный `user_id`, невалидный initData → 401.
Тесты: `tests/test_webapp.py` (валидация initData, 401, статика 200).

**Этап 2 — Deck-генерация.** `core/deck.py` + промпты по пресетам + безопасный парсинг.
Критерий: ручной вызов `generate_deck` даёт валидный deck для каждого пресета.
Тесты: `tests/test_deck.py` (все пресеты, битый JSON → None).

**Этап 3 — API урока.** `deck/new`, `deck/answer`, `deck/finish`, миграция `lesson_sessions`,
квота, SRS, план, XP. Критерий: полный цикл из теста: new → 2 answer → finish; в БД
finished-урок + счёт + SRS-записи. Тесты: `tests/test_webapp.py` расширяется.

**Этап 4 — Фронт.** Экраны Presentation/Cards/Quiz/Finish (Dialogue — этап 5).
Критерий: ручной проход в Telegram (тёмная/светлая темы, свайпы, haptics).

**Этап 5 — Диалог и голос.** Dialogue-сценки и `POST /api/voice/answer` (STT-оценка),
запись в `audio_answers`. Критерий: реплика голосом сохраняется и оценивается.

**Этап 6 — Полировка/деплой.** Кэши статики, сжатие, кнопка «Ещё урок», апселлы,
README-гайд развёртывания (туннель → постоянный host/nginx/certbot).

## 10. Риски и решения

- **WebApp не открывается на localhost** — обязателен публичный HTTPS; этапы начинаются
  с туннеля (cloudflared quick tunnel, бесплатно, без регистрации домена).
- **LLM медленный (5–20с)** — один вызов на deck, не три; экран loading; повторный запрос
  не дублирует генерацию (идемпотентность по `user_id` + ластактив-сессии).
- **Регресс чат-урока** — бот-формат остаётся `mode=chat`; мини-апп не трогает `bot/lessons.py`
  по-существу (только добавляет web-роуты).
- **Голос на фронте** — в некоторых клиентах нет доступа к микрофону; диалог и карточки
  работают и без голоса (voice-этап отдельный и опциональный).
- **Совмещение сессий** — мини-апп использует `lesson_sessions` только с `mode='miniapp'`,
  чтобы не конфликтовать с активной чат-сессией.

## 11. Открытые вопросы (решить на Этапе 1)

1. Кнопка входа: `/lesson` всегда открывает Mini App, или «полноэкранный режим» отдельной
   командой `/app`? (Рекомендация: `/lesson` → Mini App, чат-урок остаётся по кнопке ниже.)
2. Персонаж выбирается в Mini App или остаётся в чате? (Рекомендация: и там и там,
   `GET /api/menu` отдаёт выбор персонажа.)
3. Сколько quiz-вопросов в «mixed»-режиме: 3 (быстро) или 5 (глубже)? (Рекомендация: 3.)
4. Голосовая реплика в MVP или во второй итерации? (Рекомендация: вторая итерация, Этап 5.)