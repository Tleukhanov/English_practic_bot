"""База знаний грамматики для RAG (русскоязычные чанки).

Каждый чанк — одна мысль (правило + формула + 1 классический пример).
Классические примеры — запасные: если интересы ученика неизвестны,
LLM берёт пример отсюда. Если интересы известны — строит свой.
"""

GRAMMAR_CHUNKS = [
    {
        "id": "present_simple",
        "title": "Present Simple",
        "text": (
            "Present Simple — регулярные действия и факты. Формула: подлежащее + глагол. "
            "Для he/she/it к глаголу добавляется -s/-es. "
            "Классический пример: He runs every morning."
        ),
    },
    {
        "id": "present_continuous",
        "title": "Present Continuous",
        "text": (
            "Present Continuous — действие прямо сейчас. Формула: am/is/are + глагол-ing. "
            "Классический пример: I am reading now."
        ),
    },
    {
        "id": "present_perfect",
        "title": "Present Perfect",
        "text": (
            "Present Perfect — прошлое с результатом в настоящем. Формула: have/has + V3 "
            "(третья форма глагола). Маркеры: just, already, ever, never, yet. "
            "Классический пример: I have just eaten."
        ),
    },
    {
        "id": "present_perfect_vs_past_simple",
        "title": "Present Perfect vs Past Simple",
        "text": (
            "Present Perfect — важен результат (I have lost my keys — ключей нет сейчас). "
            "Past Simple — важен факт в прошлом с указанием времени (I lost my keys yesterday). "
            "Если есть yesterday/last year — только Past Simple. "
            "Классический пример: I have seen this movie vs I saw this movie yesterday."
        ),
    },
    {
        "id": "past_simple",
        "title": "Past Simple",
        "text": (
            "Past Simple — завершённое действие в прошлом. Правильные глаголы + -ed, "
            "неправильные — вторая форма (went, ate, saw). "
            "Классический пример: We visited Astana last year."
        ),
    },
    {
        "id": "past_continuous",
        "title": "Past Continuous",
        "text": (
            "Past Continuous — длительное действие в момент прошлого. Формула: was/were + глагол-ing. "
            "Часто пара с Past Simple: длинное прерывалось коротким. "
            "Классический пример: I was sleeping when you called."
        ),
    },
    {
        "id": "past_perfect",
        "title": "Past Perfect",
        "text": (
            "Past Perfect — «прошлое в прошлом»: действие завершилось раньше другого прошлого. "
            "Формула: had + V3. "
            "Классический пример: When I arrived, the train had left."
        ),
    },
    {
        "id": "future_simple",
        "title": "Future Simple (will)",
        "text": (
            "Will — спонтанные решения, обещания, прогнозы. Формула: will + глагол. "
            "Классический пример: I will help you."
        ),
    },
    {
        "id": "be_going_to",
        "title": "Be going to",
        "text": (
            "Be going to — планы и намерения. Формула: am/is/are + going to + глагол. "
            "Отличие от will: going to — заранее решено, will — решил сейчас. "
            "Классический пример: I am going to learn English."
        ),
    },
    {
        "id": "articles",
        "title": "Артикли a/an/the",
        "text": (
            "A/an — первое упоминание исчисляемого в единственном числе. "
            "The — уже известное, конкретное. Во множественном и с неисчисляемыми a/an нет. "
            "Классический пример: A cat sat on the mat."
        ),
    },
    {
        "id": "conditionals_01",
        "title": "Conditionals 0 и 1",
        "text": (
            "Zero Conditional — общие истины: If + Present Simple, Present Simple. "
            "First Conditional — реальное будущее: If + Present Simple, will + глагол. "
            "Классический пример: If it rains, we will stay at home."
        ),
    },
    {
        "id": "conditionals_23",
        "title": "Conditionals 2 и 3",
        "text": (
            "Second Conditional — нереальное настоящее: If + Past Simple, would + глагол. "
            "Third Conditional — сожаление о прошлом: If + Past Perfect, would have + V3. "
            "Классический пример: If I had studied, I would have passed."
        ),
    },
    {
        "id": "passive",
        "title": "Passive Voice",
        "text": (
            "Passive — важно действие/объект, а не кто делает. Формула: be + V3, время меняется глаголом be. "
            "Классический пример: The cake was eaten."
        ),
    },
    {
        "id": "reported_speech",
        "title": "Reported Speech",
        "text": (
            "Косвенная речь: сдвиг времени назад (Present Simple → Past Simple, will → would). "
            "Say + that необязательно. Вопросы перестраиваются в утверждения. "
            "Классический пример: He said (that) he was tired."
        ),
    },
    {
        "id": "modals",
        "title": "Модальные глаголы",
        "text": (
            "Can — умение, must — долг/приказ, should — совет, may/might — возможность. "
            "После модальных — глагол без to и без -s. "
            "Классический пример: You should rest."
        ),
    },
    {
        "id": "gerund_infinitive",
        "title": "Gerund vs Infinitive",
        "text": (
            "После enjoy, finish, mind — только герундий (verb-ing). "
            "После want, decide, plan — только инфинитив (to + verb). "
            "Некоторые глаголы меняют смысл: stop smoking (бросить) vs stop to smoke (остановиться чтобы). "
            "Классический пример: I enjoy reading."
        ),
    },
    {
        "id": "much_many",
        "title": "Much / Many / A lot",
        "text": (
            "Much — неисчисляемые (much water), many — исчисляемые во множественном (many books). "
            "A lot of — универсально для обоих. В вопросах и отрицаниях much/many, в утвердительных — a lot of. "
            "Классический пример: How much time? How many people?"
        ),
    },
    {
        "id": "comparatives",
        "title": "Сравнения",
        "text": (
            "Короткие прилагательные: -er + than (taller than). Длинные: more + прилагательное (more beautiful than). "
            "Superlative: the + -est / the most. Исключения: good-better-best, bad-worse-worst. "
            "Классический пример: This book is more interesting than that one."
        ),
    },
    {
        "id": "prepositions_place",
        "title": "Предлоги места in/at/on",
        "text": (
            "In — внутри/город/страна (in the box, in Astana). At — точка (at the bus stop, at 5 pm — и время). "
            "On — поверхность/день (on the table, on Monday). "
            "Классический пример: The keys are on the table."
        ),
    },
    {
        "id": "there_is_are",
        "title": "There is / There are",
        "text": (
            "There is — единственное число, there are — множественное. Описывает наличие, не действие. "
            "Классический пример: There is a book on the desk."
        ),
    },
    {
        "id": "questions",
        "title": "Построение вопросов",
        "text": (
            "Общий вопрос: вспомогательный глагол + подлежащее + глагол (Do you like tea?). "
            "Специальный: wh-слово + вспомогательный + подлежащее + глагол (Where do you live?). "
            "С глаголом to be вспомогательный не нужен (Are you ready?). "
            "Классический пример: What time do you wake up?"
        ),
    },
    {
        "id": "negation",
        "title": "Отрицания",
        "text": (
            "Отрицание строится через do/does/did + not + глагол без изменений. "
            "С to be: просто not после (is not). Двойных отрицаний в английском нет. "
            "Классический пример: I do not know."
        ),
    },
    {
        "id": "used_to",
        "title": "Used to",
        "text": (
            "Used to + глагол — привычка в прошлом, которой больше нет. "
            "Не путать с be used to + gerund (привык к чему-то сейчас). "
            "Классический пример: I used to play football."
        ),
    },
    {
        "id": "plurals",
        "title": "Множественное число",
        "text": (
            "Обычно + -s/-es. Исключения надо учить: man-men, child-children, foot-feet, "
            "mouse-mice, sheep-sheep, fish-fish. "
            "Классический пример: One child, two children."
        ),
    },
]
