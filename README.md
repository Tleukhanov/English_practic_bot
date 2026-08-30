<div align="center">

# 🇬🇧 English Practic Bot

**AI-репетитор английского в Telegram** — пиши или говори по-английски, бот исправит
ошибки, объяснит их по-русски и продолжит диалог. Голосом отвечает голосом.
Плюс короткие уроки, диагностика уровня, словарь с интервальным повторением и геймификация.

---

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram)
![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)
![Deploy](https://img.shields.io/badge/deploy-Docker-2496ED?logo=docker&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-7%20providers-7C3AED)
![STT](https://img.shields.io/badge/STT-faster--whisper-0EA5E9)
![Tests](https://img.shields.io/badge/tests-244%20passed-2EA043)
![GitHub stars](https://img.shields.io/github/stars/Tleukhanov/English_practic_bot.svg?style=social&label=stars)
![GitHub forks](https://img.shields.io/github/forks/Tleukhanov/English_practic_bot.svg?style=social&label=forks)

</div>

Бот построен вокруг **дешёвой LLM** (провайдер меняется одной строкой в `.env`),
локального **Whisper** для распознавания речи и бесплатного **edge-tts** для озвучки.
Архитектура разделена на доменную логику (без `Telegram`) и тонкий бот-слой —
переезд на web/mobile не потребует переписывания сервисов.

## ✨ Возможности

- 📚 **Короткие и разнообразные уроки** — `/lesson`: 3–5 минут, 5 случайных форматов —
  📖 история, 💬 разговорный, 🎮 квиз, 💭 обсуждение, классика — без повторов подряд
- ⚙️ **Генерация урока в 3 шага LLM** — ядро (тема/слова/грамматика) → слайды → задания
  параллельно; сбой одного шага не роняет весь урок
- 📝 **Заметки после урока** — итог: слова, грамматика, ошибки и рекомендация;
  слабые места попадают в память пользователя
- 🧠 **Память пользователя** — `/profile`: цель, интересы, слабые места, формат
  тренировок — всё подмешивается в практику и уроки
- 🎯 **Диагностика уровня** — `/diagnostic`: определяет CEFR (A1–C1), уроки подстраиваются под уровень
- 📚 **Словарь с интервальным повторением** — `/review`: SM-2, слова из уроков
  появляются в очереди повторения
- ✍️ **Текстовая практика** — проверка фразы, ошибки с объяснениями и исправленный вариант
- 🎤 **Голосовая практика** — распознавание (Whisper) + голосовой ответ с исправлением
- 💬 **Диалог** — помнит последние реплики и задаёт следующий вопрос
- 🔥 **Стрик и крючок возврата** — серия дней горит при пропуске; после урока бот
  напоминает про серию и слова, ждущие повторения
- 🏅 **Лидерборд** — `/leaderboard`: XP, уроки и стрики друзей
- 🎮 **Достижения** — `/achievements`: 15 ачивок, 8 уровней игрока
- 📊 **Прогресс** — `/progress` и `/stats`: уровень, точность, слабые места, XP
- 🎭 **Персонажи** — `/character`: 6 стилей общения (Chill, Toxic, Strict…)

## 🧱 Стек

| Компонент | Технология |
|---|---|
| Бот | `aiogram` 3.x |
| БД | `aiosqlite` (SQLite) |
| LLM | OpenAI-совместимый адаптер: DeepSeek / OpenAI / Ollama / Groq / Mistral / Gemini / OpenRouter |
| STT | `faster-whisper` (локально) или OpenAI API |
| TTS | `edge-tts` (бесплатно) или OpenAI API |
| Аудио | `imageio-ffmpeg` — статический ffmpeg, ставить в систему не нужно |

## 📁 Структура

```
├── bot/                  # Telegram-бот (тонкий слой)
│   ├── main.py           # точка входа (python -m bot.main)
│   ├── config.py         # настройки из .env + пресеты LLM-провайдеров
│   ├── flow.py           # общая логика практики (текст и голос)
│   ├── lessons.py        # роутер уроков (/lesson, навигация по шагам)
│   ├── achievements.py   # анонс новых достижений
│   ├── formatters.py     # форматирование ответов/статистики/шагов урока
│   ├── keyboards.py      # клавиатуры (меню, урок)
│   └── handlers/         # start, menu, text, voice, interests, review, …
├── core/                 # домен: модели и сервисы (без Telegram)
│   ├── lessons.py        # уроки: 5 форматов, генерация в 3 шага
│   ├── practice.py       # практика: промпт, парсер, PracticeService
│   ├── diagnostic.py     # диагностика уровня CEFR
│   ├── srs.py            # SM-2: интервальное повторение слов
│   ├── progress.py       # XP, стрики, слабые/сильные места
│   ├── profile.py        # память пользователя
│   ├── lesson_notes.py   # заметка после урока
│   └── scheduler.py      # ежедневные напоминания
├── providers/            # LLM / STT / TTS / аудио-утилиты
├── storage/              # Repository + SQLite-реализация
└── tests/                # pytest (244 теста)
```

## 🚀 Быстрый старт (локально)

Требуется **Python 3.10+**.

```bash
# 1. Клонировать и создать окружение
git clone https://github.com/Tleukhanov/English_practic_bot.git
cd English_practic_bot
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

# 2. Зависимости
pip install -r requirements.txt          # рантайм
pip install -r requirements-dev.txt      # + тесты

# 3. Настройки
cp .env.example .env
# заполни TELEGRAM_BOT_TOKEN и LLM_API_KEY (см. ниже)

# 4. Запуск
python -m bot.main
```

### ⚙️ Настройка `.env`

```env
TELEGRAM_BOT_TOKEN=123456:ABC...   # токен от @BotFather
LLM_PROVIDER=deepseek              # выбери провайдера
LLM_API_KEY=sk-...                 # ключ API (для ollama не нужен)
```

**Защита от пережога LLM на тестерах:**
- `LLM_DAILY_LIMIT=30` — дневной лимит LLM-действий (урок, реплика, диагностика) на пользователя. `0` — без лимита.
- `PROMO_UNLIMITED_CODE=ENG-PREMIUM-2026` — промокод безлимита: пользователь шлёт боту `/promo <код>`, лимит для него снимается навсегда. Пустое значение — промокоды выключены.
- Счётчик хранится в БД (таблица `llm_usage`), не зависит от рестартов.

**Смена LLM-провайдера — одна строка.** Все говорят по одному OpenAI-совместимому протоколу:

| `LLM_PROVIDER` | Модель по умолчанию | Нужен ключ? |
|---|---|---|
| `deepseek` | `deepseek-chat` | да |
| `openai` | `gpt-4o-mini` | да |
| `ollama` | `gemma2:2b` | нет |
| `groq` | `llama-3.3-70b-versatile` | да |
| `mistral` | `mistral-small-latest` | да |
| `gemini` | `gemini-2.0-flash` | да |
| `openrouter` | `deepseek/deepseek-chat` | да |

Любой пресет перекрывается полями `LLM_BASE_URL` и `LLM_MODEL` — подключается любой другой совместимый провайдер.

- STT: `STT_PROVIDER=faster-whisper` (локально, модель качается один раз) или `openai`
- TTS: `TTS_PROVIDER=edge-tts` (бесплатно) или `openai`

## 🎙️ Голос

- Telegram шлёт голосовые в `.ogg/opus`; встроенный ffmpeg (`imageio-ffmpeg`) конвертирует в `wav 16кГц` для Whisper
- `faster-whisper` работает на CPU (модель `small` — быстро и точно)
- Ответ бота: текст проверки + голосовое с исправленной фразой (edge-tts → ogg/opus для Telegram)

## 🐳 Деплой с Docker

```bash
# 1. Скопировать и заполнить .env
cp .env.example .env

# 2. Собрать и запустить
docker compose up -d --build

# 3. Логи
docker compose logs -f bot

# 4. Остановить
docker compose down
```

Данные (SQLite + кэш Whisper) живут в `./data/` на хосте — они переживают пересоздание
контейнера. Бот сам перезапускается при падении (`restart: unless-stopped`), образ
содержит healthcheck.

## 🧪 Тесты

```bash
pytest
```

**244 теста**: парсеры JSON-ответов LLM, сервисы практики/уроков/профиля/заметок/SRS,
ретраи LLM, навигация по шагам урока, генерация урока в 3 шага, SQLite-хранилище,
форматтеры, достижения, конвертация аудио.

## 🗺️ Дорожная карта

Видение, фазы и приоритеты — в [ROADMAP.md](ROADMAP.md). Кратко:

### ✅ Сделано
- **MVP** — текстовая и голосовая практика с исправлением ошибок
- **Фаза 1** — мини-уроки: тема, слова, слайды, грамматика, задания
- **Фаза 2** — выбор темы из предложений LLM
- **Фаза 3** — диагностика уровня A1–C1
- **Фаза 4** — память пользователя (цель, интересы, слабые места)
- **Фаза 5** — заметки после урока; слабые места → профиль
- **Фаза 6** — адаптивное обучение: без повторов тем, по интересам
- **Фаза 7** — /interests (13 тем) и приоритет в промптах
- **Фаза 8** — AI-персонажи: 6 стилей через /character
- **Фаза 9** — удержание: приветствие + streak + weak areas
- **Фаза 10** — /progress: XP, streak, слабые/сильные места
- **Фаза 11** — напоминания: ежедневный планировщик + retention
- **Фаза 12** — игровые элементы: 15 достижений, 8 уровней
- **Фаза 13** — словарь SRS: /review, интервалы SM-2
- ⚡ **Хардкор** — короткие уроки в 5 форматах без повторов подряд
- ⚡ **Хардкор** — генерация урока в 3 шага LLM (устойчивость к сбоям)
- ⚡ **Хардкор** — /leaderboard: XP, уроки, стрики
- ⚡ **Хардкор** — крючок возврата: серия 🔥 и очередь повторения 📚

### 🔜 Позже
- Telegram Mini App, Web/Mobile-клиент, миграция на Postgres (интерфейс `Repository` уже готов)

---

<div align="center">

Сделано с ❤️ и большим количеством кофе.

</div>