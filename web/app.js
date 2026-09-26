(() => {
  'use strict';

  const app = document.getElementById('app');
  const telegram = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const themeVariables = {
    bg_color: '--tg-bg-color',
    text_color: '--tg-text-color',
    hint_color: '--tg-hint-color',
    button_color: '--tg-button-color',
    button_text_color: '--tg-button-text-color',
    secondary_bg_color: '--tg-secondary-bg-color'
  };
  const defaultProfile = {
    user_id: null,
    level: 'B1',
    quota_left: 12,
    character: 'Samantha',
    interests: ['coffee', 'travel'],
    topics: []
  };
  const state = {
    initData: '',
    demo: false,
    profile: { ...defaultProfile },
    selectedTopic: '',
    deck: null,
    sessionId: null,
    sequence: [],
    sectionIndex: 0,
    screen: 'menu',
    loading: false,
    startRequestId: 0,
    presentationIndex: 0,
    cardIndex: 0,
    cardFlipped: false,
    flashcards: {},
    quizIndex: 0,
    quizSelected: null,
    quizAnswers: [],
    quizScore: 0,
    quizPending: false,
    quizRequestId: 0,
    quizFeedbackError: '',
    dialogueReady: false,
    dialogueIndex: 0,
    dialogueLog: [],
    dialogueUsedChoices: new Set(),
    dialogueShowAll: false,
    dialogueDone: false,
    voiceFeedback: {},
    finishRequesting: false,
    finishRequestId: 0,
    finishData: null,
    finishError: '',
    errorTitle: '',
    errorMessage: '',
    errorKind: '',
    toast: '',
    toastError: false,
    toastTimer: null
  };
  let touchStart = null;
  let ignoreSurfaceClickUntil = 0;

  const demoDeck = {
    title: 'Coffee Around the World',
    subtitle_ru: 'Путешествие по кофейным традициям',
    preset: 'mixed',
    emoji: '☕',
    slides: [
      { headline: 'Why coffee?', body: 'Coffee is more than a morning drink. It is a small ritual that connects people, places and cultures.', emoji: '🌅' },
      { headline: 'Espresso in Italy', body: 'In Italy, espresso is often enjoyed standing at the bar. The classic serving is short, strong and aromatic.', emoji: '🇮🇹' },
      { headline: 'A global language', body: 'From Ethiopia to Scandinavia, every region has its own method, roast and favorite way to share a cup.', emoji: '🌍' }
    ],
    vocabulary: [
      { word: 'brew', translation: 'заваривать', example: 'I brew coffee every morning.', transcription: '/bruː/' },
      { word: 'roast', translation: 'обжаривать', example: 'The beans are roasted in small batches.', transcription: '/rəʊst/' },
      { word: 'aromatic', translation: 'ароматный', example: 'The kitchen smells warm and aromatic.', transcription: '/ˌærəˈmætɪk/' }
    ],
    quiz: [
      { question: 'What does brew mean?', options: ['заваривать', 'пить быстро', 'убирать посуду'], answer_index: 0, explanation_ru: 'To brew — заваривать напиток, например кофе или чай.' },
      { question: 'Which sentence sounds natural?', options: ['I espresso every day.', 'I drink an espresso every day.', 'I espresso a coffee every day.'], answer_index: 1, explanation_ru: 'Для названия напитка используем артикль an: an espresso.' },
      { question: 'Where is espresso traditionally served?', options: ['At the bar', 'In a cinema', 'At a stadium'], answer_index: 0, explanation_ru: 'Итальянцы часто пьют эспрессо стоя у стойки — at the bar.' }
    ],
    dialogue: {
      scene_ru: 'Ты в римской кофейне у прилавка.',
      lines: [
        { character: 'Barista', line: 'Ciao! Un caffè?' },
        { character: 'Samantha', line: 'Sì, grazie. It looks delicious!' },
        { character: 'Barista', line: 'Perfetto. Where are you travelling today?' }
      ],
      choices: [
        { line: 'I am exploring the city. Could I have a cappuccino, please?', next: 1 },
        { line: 'Just a small espresso, thank you.', next: 1 }
      ]
    }
  };

  const topicLibrary = {
    coffee: ['Coffee rituals', 'A café conversation', 'The art of brunch'],
    travel: ['City stories', 'A weekend escape', 'Directions in English'],
    business: ['A confident meeting', 'Pitching an idea', 'Small talk at work'],
    technology: ['Life online', 'A new app', 'Digital habits'],
    sport: ['The winning habit', 'A morning workout', 'The team spirit'],
    music: ['A song in your head', 'A live concert', 'The rhythm of a city']
  };
  const defaultTopics = ['Coffee around the world', 'Small talk, big ideas', 'A day in another city'];

  function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function asString(value, fallback = '') {
    if (value === undefined || value === null) {
      return fallback;
    }
    if (typeof value === 'string') {
      return value || fallback;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    return fallback;
  }

  function escapeHtml(value) {
    const entities = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '\u0022': '&quot;',
      '\u0027': '&#39;'
    };
    return String(value ?? '').replace(/[&<>\u0022\u0027]/g, character => entities[character]);
  }

  function numberOrNull(value) {
    if (value === undefined || value === null || value === '') {
      return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function displayValue(value, fallback = '—') {
    if (value === undefined || value === null || value === '') {
      return escapeHtml(fallback);
    }
    const number = numberOrNull(value);
    return escapeHtml(number === null ? String(value) : String(number));
  }

  function countLabel(count, one, few, many) {
    const remainder100 = count % 100;
    const remainder10 = count % 10;
    if (remainder100 >= 11 && remainder100 <= 14) {
      return many;
    }
    if (remainder10 === 1) {
      return one;
    }
    if (remainder10 >= 2 && remainder10 <= 4) {
      return few;
    }
    return many;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function optionText(value, index) {
    if (isObject(value)) {
      return asString(value.text || value.label || value.option, `Вариант ${index + 1}`);
    }
    return asString(value, `Вариант ${index + 1}`);
  }

  function normalizeProfile(raw) {
    const source = isObject(raw) ? raw : {};
    const interests = Array.isArray(source.interests) ? source.interests : [];
    const topics = Array.isArray(source.topics) ? source.topics : [];
    return {
      user_id: source.user_id ?? null,
      level: asString(source.level, 'B1'),
      quota_left: source.quota_left ?? null,
      character: asString(source.character, 'Samantha'),
      interests: interests.map(value => asString(value)).filter(Boolean),
      topics: topics.map(value => asString(value)).filter(Boolean)
    };
  }

  function normalizeDeck(raw) {
    const source = isObject(raw) ? raw : {};
    const slides = Array.isArray(source.slides) ? source.slides.filter(isObject).map((slide, index) => ({
      headline: asString(slide.headline, `Idea ${index + 1}`),
      body: asString(slide.body),
      emoji: asString(slide.emoji, '✦')
    })) : [];
    const vocabulary = Array.isArray(source.vocabulary) ? source.vocabulary.filter(isObject).map(item => ({
      word: asString(item.word, 'word'),
      translation: asString(item.translation),
      example: asString(item.example),
      transcription: asString(item.transcription)
    })).filter(item => item.word) : [];
    const quiz = Array.isArray(source.quiz) ? source.quiz.filter(isObject).map(item => ({
      question: asString(item.question, 'Choose the best answer.'),
      options: Array.isArray(item.options) ? item.options.map(optionText) : [],
      answer_index: numberOrNull(item.answer_index) ?? -1,
      explanation_ru: asString(item.explanation_ru)
    })) : [];
    const dialogueSource = isObject(source.dialogue) ? source.dialogue : null;
    const dialogueLines = dialogueSource && Array.isArray(dialogueSource.lines) ? dialogueSource.lines.filter(isObject).map((line, index) => ({
      id: line.id ?? null,
      character: asString(line.character, 'Character'),
      line: asString(line.line, `Line ${index + 1}`),
      index
    })) : [];
    const dialogueChoices = dialogueSource && Array.isArray(dialogueSource.choices) ? dialogueSource.choices.filter(isObject).map(choice => ({
      line: asString(choice.line, 'Continue the conversation.'),
      next: choice.next,
      line_index: numberOrNull(choice.line_index ?? choice.at ?? choice.from)
    })) : [];
    return {
      title: asString(source.title, 'English moment'),
      subtitle_ru: asString(source.subtitle_ru, 'A fresh little lesson for you.'),
      preset: normalizePreset(source.preset),
      emoji: asString(source.emoji, '✨'),
      slides,
      vocabulary,
      quiz,
      dialogue: dialogueLines.length ? {
        scene_ru: asString(dialogueSource.scene_ru, 'A little scene to practise.'),
        lines: dialogueLines,
        choices: dialogueChoices
      } : null
    };
  }

  function normalizePreset(value) {
    const preset = asString(value, 'mixed').toLowerCase();
    return ['presentation', 'cards', 'quiz', 'dialogue', 'mixed'].includes(preset) ? preset : 'mixed';
  }

  function getInitData() {
    return telegram && typeof telegram.initData === 'string' ? telegram.initData : '';
  }

  function setClosingConfirmation(value) {
    if (!telegram || typeof telegram.setClosingConfirmation !== 'function') {
      return;
    }
    try {
      telegram.setClosingConfirmation(Boolean(value));
    } catch (error) {
      void error;
    }
  }

  function haptic(type) {
    if (!telegram || !telegram.HapticFeedback) {
      return;
    }
    try {
      if (['success', 'warning', 'error'].includes(type)) {
        telegram.HapticFeedback.notificationOccurred(type);
      } else {
        telegram.HapticFeedback.impactOccurred(type || 'light');
      }
    } catch (error) {
      void error;
    }
  }

  function applyTheme() {
    const root = document.documentElement;
    const scheme = telegram && typeof telegram.colorScheme === 'string' ? telegram.colorScheme : '';
    if (scheme === 'dark' || scheme === 'light') {
      root.dataset.theme = scheme;
    } else {
      root.removeAttribute('data-theme');
    }
    const params = telegram && isObject(telegram.themeParams) ? telegram.themeParams : {};
    Object.keys(themeVariables).forEach(key => {
      const value = typeof params[key] === 'string' ? params[key].trim() : '';
      if (value) {
        root.style.setProperty(themeVariables[key], value);
      }
    });
  }

  async function apiPost(path, payload = {}) {
    if (!state.initData) {
      throw new Error('Нет initData Telegram. Запустите приложение из Telegram.');
    }
    if (typeof fetch !== 'function') {
      throw new Error('Браузер не поддерживает сетевые запросы.');
    }
    const requestPayload = { ...payload, initData: state.initData };
    const url = `${path}?initData=${encodeURIComponent(state.initData)}`;
    let response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': state.initData
        },
        body: JSON.stringify(requestPayload),
        credentials: 'same-origin',
        cache: 'no-store'
      });
    } catch (error) {
      throw new Error('Не удалось связаться с сервером. Проверьте подключение и попробуйте ещё раз.');
    }
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error(`Сервер вернул некорректный ответ (${response.status}).`);
    }
    if (!response.ok || !isObject(data) || data.ok === false) {
      throw new Error(asString(data && (data.error || data.message), `Ошибка сервера (${response.status}).`));
    }
    return data;
  }

  function uniqueStrings(values) {
    const seen = new Set();
    const result = [];
    values.forEach(value => {
      const text = asString(value).trim();
      const key = text.toLocaleLowerCase();
      if (text && !seen.has(key)) {
        seen.add(key);
        result.push(text);
      }
    });
    return result;
  }

  function getSuggestedTopics() {
    const interests = Array.isArray(state.profile.interests) ? state.profile.interests : [];
    const interestTopics = interests.flatMap(interest => topicLibrary[asString(interest).toLowerCase()] || []);
    const topics = uniqueStrings([...(state.profile.topics || []), ...interestTopics, ...defaultTopics]);
    return topics.slice(0, 3);
  }

  function topicEmoji(topic, index) {
    const text = asString(topic).toLowerCase();
    if (text.includes('coffee') || text.includes('cafe') || text.includes('brunch')) {
      return '☕';
    }
    if (text.includes('travel') || text.includes('city') || text.includes('weekend')) {
      return '🧭';
    }
    if (text.includes('work') || text.includes('meeting') || text.includes('pitch')) {
      return '💼';
    }
    if (text.includes('music') || text.includes('concert') || text.includes('song')) {
      return '🎧';
    }
    if (text.includes('sport') || text.includes('workout') || text.includes('team')) {
      return '🏃';
    }
    return ['✨', '💡', '🌱'][index % 3];
  }

  function topicSubtitle(topic, index) {
    const text = asString(topic).toLowerCase();
    if (text.includes('coffee') || text.includes('cafe') || text.includes('brunch')) {
      return 'Кофе и разговор';
    }
    if (text.includes('travel') || text.includes('city') || text.includes('weekend')) {
      return 'Городские истории';
    }
    if (text.includes('work') || text.includes('meeting') || text.includes('pitch')) {
      return 'Уверенная речь';
    }
    if (index === 0) {
      return 'Твоя следующая тема';
    }
    return 'Практика без стресса';
  }

  function hasSection(section) {
    if (!state.deck) {
      return false;
    }
    if (section === 'presentation') {
      return state.deck.slides.length > 0;
    }
    if (section === 'cards') {
      return state.deck.vocabulary.length > 0;
    }
    if (section === 'quiz') {
      return state.deck.quiz.length > 0;
    }
    if (section === 'dialogue') {
      return Boolean(state.deck.dialogue);
    }
    return false;
  }

  function getLessonSequence() {
    const preset = state.deck ? state.deck.preset : 'mixed';
    if (preset === 'mixed') {
      return ['presentation', 'cards', 'quiz', 'dialogue'].filter(hasSection);
    }
    return hasSection(preset) ? [preset] : [];
  }

  function resetSectionState(section) {
    if (section === 'presentation') {
      state.presentationIndex = 0;
    }
    if (section === 'cards') {
      state.cardIndex = 0;
      state.cardFlipped = false;
    }
    if (section === 'quiz') {
      state.quizIndex = 0;
      state.quizSelected = null;
      state.quizPending = false;
      state.quizFeedbackError = '';
    }
    if (section === 'dialogue') {
      state.dialogueReady = false;
      state.dialogueIndex = 0;
      state.dialogueLog = [];
      state.dialogueUsedChoices = new Set();
      state.dialogueShowAll = false;
      state.dialogueDone = false;
      state.voiceFeedback = {};
    }
  }

  function resetLessonState() {
    state.deck = null;
    state.sessionId = null;
    state.sequence = [];
    state.sectionIndex = 0;
    state.presentationIndex = 0;
    state.cardIndex = 0;
    state.cardFlipped = false;
    state.flashcards = {};
    state.quizIndex = 0;
    state.quizSelected = null;
    state.quizAnswers = [];
    state.quizScore = 0;
    state.quizPending = false;
    state.quizRequestId += 1;
    state.quizFeedbackError = '';
    state.dialogueReady = false;
    state.dialogueIndex = 0;
    state.dialogueLog = [];
    state.dialogueUsedChoices = new Set();
    state.dialogueShowAll = false;
    state.dialogueDone = false;
    state.voiceFeedback = {};
    state.finishRequesting = false;
    state.finishRequestId += 1;
    state.finishData = null;
    state.finishError = '';
  }

  function prepareSection(section) {
    if (section !== 'dialogue' || state.dialogueReady || !state.deck || !state.deck.dialogue) {
      return;
    }
    const lines = state.deck.dialogue.lines;
    const choices = state.deck.dialogue.choices;
    state.dialogueReady = true;
    state.dialogueIndex = 0;
    state.dialogueShowAll = choices.length === 0;
    if (lines[0]) {
      state.dialogueLog.push({ type: 'line', ...lines[0] });
    }
  }

  function getPresentationItems() {
    if (!state.deck) {
      return [];
    }
    return [
      { cover: true, headline: state.deck.title, body: state.deck.subtitle_ru, emoji: state.deck.emoji },
      ...state.deck.slides
    ];
  }

  function showToast(message, isError = false) {
    state.toast = asString(message, 'Готово');
    state.toastError = Boolean(isError);
    if (state.toastTimer) {
      window.clearTimeout(state.toastTimer);
    }
    render();
    state.toastTimer = window.setTimeout(() => {
      state.toast = '';
      state.toastTimer = null;
      if (app.innerHTML) {
        render();
      }
    }, 3200);
  }

  function render() {
    let markup = '';
    if (state.screen === 'menu') {
      markup = renderMenu();
    } else if (state.screen === 'loading') {
      markup = renderLoading();
    } else if (state.screen === 'presentation') {
      markup = renderPresentation();
    } else if (state.screen === 'cards') {
      markup = renderCards();
    } else if (state.screen === 'quiz') {
      markup = renderQuiz();
    } else if (state.screen === 'dialogue') {
      markup = renderDialogue();
    } else if (state.screen === 'finish') {
      markup = renderFinish();
    } else {
      markup = renderError();
    }
    const toast = state.toast ? `<div class='toast${state.toastError ? ' is-error' : ''}' role='status'>${escapeHtml(state.toast)}</div>` : '';
    app.innerHTML = `${markup}${toast}`;
  }

  function renderMenu() {
    const topics = getSuggestedTopics();
    if (!state.selectedTopic || !topics.includes(state.selectedTopic)) {
      state.selectedTopic = topics[0] || defaultTopics[0];
    }
    const profile = state.profile;
    const quotaLeft = numberOrNull(profile.quota_left);
    const interestMarkup = (profile.interests || []).slice(0, 4).map(interest => `<span class='meta-pill'>${escapeHtml(interest)}</span>`).join('');
    const topicMarkup = topics.map((topic, index) => {
      const selected = topic === state.selectedTopic;
      return `<button class='topic-button${selected ? ' is-selected' : ''}' type='button' data-action='select-topic' data-topic='${escapeHtml(topic)}' aria-pressed='${selected}'>
        <span class='topic-icon'>${topicEmoji(topic, index)}</span>
        <span class='topic-copy'><span class='topic-title'>${escapeHtml(topic)}</span><span class='topic-subtitle'>${escapeHtml(topicSubtitle(topic, index))}</span></span>
        <span class='topic-check'>✓</span>
      </button>`;
    }).join('');
    return `<section class='screen menu-screen'>
      <div class='menu-shell'>
        <div class='welcome-orb' aria-hidden='true'>✦</div>
        <p class='eyebrow'>Startup English</p>
        <h1 class='menu-heading'>Привет, <span class='name'>${escapeHtml(profile.character || 'друг')}</span>!</h1>
        <p class='lead'>Короткий урок, который sounds like you — с новыми словами, живой практикой и маленькой победой.</p>
        <div class='profile-stats'>
          <div class='profile-stat'><span class='profile-stat-label'>Уровень</span><strong class='profile-stat-value accent'>${escapeHtml(profile.level || 'B1')}</strong></div>
          <div class='profile-stat'><span class='profile-stat-label'>Квота</span><strong class='profile-stat-value'>${displayValue(profile.quota_left, '∞')}</strong></div>
          <div class='profile-stat'><span class='profile-stat-label'>Партнёр</span><strong class='profile-stat-value'>${escapeHtml(profile.character || 'Samantha')}</strong></div>
        </div>
        ${quotaLeft !== null && quotaLeft <= 0 ? `<div class='upsell-banner'><span class='banner-icon'>💎</span><span class='upsell-copy'><strong>Квота на сегодня закончилась</strong><small>Отправь боту /premium — оформим подписку за минуту.</small></span><button class='upsell-button' type='button' data-action='premium-upsell'>💳 Подписка</button></div>` : ''}
        <div class='section-heading'><h2>О чём поговорим?</h2><span>3 темы на выбор</span></div>
        <div class='topic-list'>${topicMarkup}</div>
        <button class='random-button' type='button' data-action='random-topic'>🎲 Случайная тема</button>
        <button class='primary-button start-button' type='button' data-action='start-lesson'>🚀 Начать урок <span aria-hidden='true'>→</span></button>
        <div class='utility-row'>
          <button class='utility-button' type='button' data-action='personality-stub'>⚙️ Персонаж</button>
          <button class='utility-button' type='button' data-action='interests-stub'>🎯 Интересы</button>
        </div>
        ${interestMarkup ? `<div class='demo-banner'><span class='banner-icon'>✦</span><span>Твои интересы: ${interestMarkup}</span></div>` : ''}
        ${state.demo ? `<div class='warning-banner'><span class='banner-icon'>🌐</span><span>Запустите из Telegram — сейчас открыт демо-режим с фейковой декой.</span></div>` : ''}
      </div>
    </section>`;
  }

  function renderLoading() {
    return `<section class='screen loading-screen'>
      <div class='loading-inner'>
        <div class='loading-orb' aria-hidden='true'>${state.deck ? escapeHtml(state.deck.emoji) : '✦'}</div>
        <p class='eyebrow'>Startup English</p>
        <h1>ИИ готовит твой урок<span class='loading-dots' aria-hidden='true'><i></i><i></i><i></i></span></h1>
        <p class='loading-caption'>${escapeHtml(state.selectedTopic || 'Собираем идеи для практики')}</p>
        <div class='skeleton-stack' aria-label='Загрузка урока'>
          <div class='skeleton-card'><div class='skeleton-avatar'></div><div class='skeleton-lines'><div class='skeleton-line'></div><div class='skeleton-line short'></div></div></div>
          <div class='skeleton-card'><div class='skeleton-avatar'></div><div class='skeleton-lines'><div class='skeleton-line'></div><div class='skeleton-line short'></div></div></div>
          <div class='skeleton-card'><div class='skeleton-avatar'></div><div class='skeleton-lines'><div class='skeleton-line'></div><div class='skeleton-line short'></div></div></div>
        </div>
      </div>
    </section>`;
  }

  function renderLessonTopbar(label) {
    return `<div class='lesson-topbar'>
      <button class='back-button' type='button' data-action='back-menu' aria-label='Вернуться в меню'>←</button>
      <div class='lesson-label'><span aria-hidden='true'>✦</span><strong>${escapeHtml(label)}</strong></div>
      <span class='muted'>${escapeHtml(state.deck ? state.deck.emoji : '✨')}</span>
    </div>`;
  }

  function renderPresentation() {
    const items = getPresentationItems();
    if (!items.length) {
      return renderError();
    }
    state.presentationIndex = Math.max(0, Math.min(state.presentationIndex, items.length - 1));
    const current = items[state.presentationIndex];
    const isCover = state.presentationIndex === 0;
    const slideWord = countLabel(state.deck.slides.length, 'слайд', 'слайда', 'слайдов');
    const dots = items.map((item, index) => `<button class='progress-dot${index === state.presentationIndex ? ' is-active' : ''}' type='button' data-action='presentation-dot' data-index='${index}' aria-label='Открыть слайд ${index + 1}'></button>`).join('');
    const nextLabel = state.presentationIndex === items.length - 1 ? 'Следующий раздел' : 'Далее';
    return `<section class='screen presentation-screen'>
      <div class='presentation-content'>
        <div class='presentation-header'><span class='presentation-counter'>${state.presentationIndex + 1} / ${items.length}</span><span class='muted'>${isCover ? 'Открытие урока' : 'Идея'} </span></div>
        <div class='presentation-surface' role='button' tabindex='0' data-action='presentation-surface' aria-label='Открыть слайд, коснитесь или нажмите стрелку'>
          <div class='slide-art' aria-hidden='true'>${escapeHtml(current.emoji || state.deck.emoji)}</div>
          <p class='slide-kicker'>${isCover ? 'Твой урок' : `Шаг ${state.presentationIndex} из ${state.deck.slides.length}`}</p>
          <h1 class='slide-headline'>${escapeHtml(current.headline)}</h1>
          <p class='slide-body'>${escapeHtml(current.body)}</p>
          <div class='slide-meta'>${isCover ? `<span class='meta-pill'>${state.deck.slides.length} ${slideWord}</span><span class='meta-pill'>${state.deck.vocabulary.length} ${countLabel(state.deck.vocabulary.length, 'слово', 'слова', 'слов')}</span>` : `<span class='meta-pill'>English practice</span>`}</div>
        </div>
        <div class='presentation-footer'>
          <div class='presentation-arrows'>
            <button class='icon-button' type='button' data-action='presentation-prev' aria-label='Предыдущий слайд' ${state.presentationIndex === 0 ? 'disabled' : ''}>←</button>
            <button class='icon-button' type='button' data-action='presentation-next' aria-label='Следующий слайд'>→</button>
          </div>
          <button class='primary-button' type='button' data-action='presentation-next'>${nextLabel} <span aria-hidden='true'>→</span></button>
        </div>
        <div class='progress-dots' aria-label='Прогресс презентации'>${dots}</div>
      </div>
    </section>`;
  }

  function renderCards() {
    const cards = state.deck ? state.deck.vocabulary : [];
    if (!cards.length) {
      return renderError();
    }
    state.cardIndex = Math.max(0, Math.min(state.cardIndex, cards.length - 1));
    const card = cards[state.cardIndex];
    const progress = ((state.cardIndex + 1) / cards.length) * 100;
    const transcription = card.transcription ? `<span class='card-transcription'>${escapeHtml(card.transcription)}</span>` : '';
    const example = card.example || 'Add your own sentence with this word.';
    return `<section class='screen cards-screen'>
      ${renderLessonTopbar('Карточки слов')}
      <div class='lesson-main'>
        <div class='lesson-progress-row'><span>Карточка ${state.cardIndex + 1} из ${cards.length}</span><span>${Math.round(progress)}%</span></div>
        <div class='progress-track' aria-label='Прогресс карточек'><div class='progress-fill' style='width: ${progress}%'></div></div>
        <div class='card-stage'>
          <button class='flashcard${state.cardFlipped ? ' is-flipped' : ''}' type='button' data-action='card-flip' aria-pressed='${state.cardFlipped}' aria-label='${state.cardFlipped ? 'Показать слово' : 'Показать перевод'}'>
            <span class='flashcard-inner'>
              <span class='flashcard-face flashcard-front'><span class='card-label'>Word · ${state.cardIndex + 1}/${cards.length}</span><strong class='card-word'>${escapeHtml(card.word)}</strong><span class='card-tap-hint'>Нажми, чтобы перевернуть ↻</span></span>
              <span class='flashcard-face flashcard-back'><span class='card-label'>Meaning</span><strong class='card-translation'>${escapeHtml(card.translation || '—')}</strong>${transcription}<span class='card-example'>${escapeHtml(example)}</span><span class='card-back-footer'>✦ <span>Example sentence</span></span></span>
            </span>
          </button>
        </div>
        <div class='card-audio-row'><span class='card-audio-note'>Попроси голос и запомни произношение</span><button class='sound-button' type='button' data-action='card-speak' data-word='${escapeHtml(card.word)}'>🔊 Послушать</button></div>
        <div class='card-actions'><button class='card-action known' type='button' data-action='card-mark' data-known='true'>✓ Знаю</button><button class='card-action repeat' type='button' data-action='card-mark' data-known='false'>↻ Повторю</button></div>
      </div>
    </section>`;
  }

  function renderQuiz() {
    const questions = state.deck ? state.deck.quiz : [];
    if (!questions.length) {
      return renderError();
    }
    state.quizIndex = Math.max(0, Math.min(state.quizIndex, questions.length - 1));
    const question = questions[state.quizIndex];
    const answered = state.quizSelected !== null;
    const answer = state.quizAnswers[state.quizIndex];
    const progress = ((state.quizIndex + 1) / questions.length) * 100;
    const answerMarkup = question.options.map((option, index) => {
      const selected = index === state.quizSelected;
      const correct = index === question.answer_index;
      let className = 'answer-button';
      if (answered && correct) {
        className += ' is-correct';
      } else if (answered && selected) {
        className += ' is-wrong';
      }
      return `<button class='${className}' type='button' data-action='quiz-answer' data-index='${index}' ${answered ? 'disabled' : ''}><span class='answer-letter'>${String.fromCharCode(65 + index)}</span><span class='answer-copy'>${escapeHtml(option)}</span></button>`;
    }).join('');
    const feedback = answered ? (answer && answer.correct ? 'Верно!' : 'Почти!') : '';
    const explanation = answer && answer.explanation ? answer.explanation : question.explanation_ru;
    return `<section class='screen quiz-screen'>
      ${renderLessonTopbar('Проверка')}
      <div class='lesson-main'>
        <div class='quiz-header'><div><p class='eyebrow'>Question ${state.quizIndex + 1} of ${questions.length}</p><h1>Ты справишься</h1></div><div class='quiz-score'>Счёт <strong>${state.quizScore}</strong></div></div>
        <div class='lesson-progress-row'><span>Ответ ${state.quizIndex + 1} / ${questions.length}</span><span>${Math.round(progress)}%</span></div>
        <div class='progress-track' aria-label='Прогресс квиза'><div class='progress-fill' style='width: ${progress}%'></div></div>
        <div class='quiz-card'>
          <span class='question-label'>Choose the best answer</span>
          <h2 class='question-text'>${escapeHtml(question.question)}</h2>
          <div class='answer-list'>${answerMarkup || `<p class='quiz-empty'>В этом вопросе пока нет вариантов ответа.</p>`}</div>
          ${answered ? `<div class='answer-result ${answer && answer.correct ? 'is-correct' : 'is-wrong'}'><div class='answer-result-title'>${answer && answer.correct ? '🎉' : '💡'} ${escapeHtml(feedback)}</div><p class='answer-explanation'>${escapeHtml(explanation || 'Продолжай практиковаться — так запоминается быстрее.')}</p>${state.quizFeedbackError ? `<p class='answer-error'>Ответ сохранён локально: ${escapeHtml(state.quizFeedbackError)}</p>` : ''}</div>` : ''}
          ${answered ? `<div class='quiz-next-row'><button class='primary-button' type='button' data-action='quiz-next'>${state.quizIndex === questions.length - 1 ? 'К итогам' : 'Далее'} <span aria-hidden='true'>→</span></button></div>` : ''}
        </div>
      </div>
    </section>`;
  }

  function getDialogueChoices() {
    if (!state.deck || !state.deck.dialogue) {
      return [];
    }
    const allChoices = state.deck.dialogue.choices;
    const hasScopedChoices = allChoices.some(choice => choice.line_index !== null);
    const candidates = hasScopedChoices ? allChoices.filter(choice => choice.line_index === state.dialogueIndex) : allChoices;
    return candidates
      .map((choice, index) => ({ choice, index: allChoices.indexOf(choice) }))
      .filter(item => !state.dialogueUsedChoices.has(item.index));
  }

  function renderBubble(item) {
    const isUser = item.type === 'user';
    const character = isUser ? 'Ты' : asString(item.character, 'Character');
    return `<div class='bubble${isUser ? ' is-user' : ''}'><span class='bubble-avatar' aria-hidden='true'>${isUser ? '🙂' : '✦'}</span><div class='bubble-content'><p class='bubble-character'>${escapeHtml(character)}</p><p class='bubble-text'>${escapeHtml(item.line)}</p></div></div>`;
  }

  function renderDialogue() {
    const dialogue = state.deck && state.deck.dialogue;
    if (!dialogue) {
      return renderError();
    }
    prepareSection('dialogue');
    const availableChoices = getDialogueChoices();
    if (!state.dialogueDone && !state.dialogueShowAll && availableChoices.length === 0) {
      state.dialogueDone = true;
    }
    const visibleItems = state.dialogueShowAll ? dialogue.lines.map(line => ({ type: 'line', ...line })) : state.dialogueLog;
    const conversation = visibleItems.map(renderBubble).join('');
    const choices = state.dialogueDone || state.dialogueShowAll ? '' : availableChoices.map(item => {
      const feedback = state.voiceFeedback[item.index];
      let feedbackHtml = '';
      if (feedback) {
        if (feedback.busy) {
          feedbackHtml = `<span class='voice-feedback busy'><span class='voice-dot' aria-hidden='true'></span>Слушаем…</span>`;
        } else if (feedback.error) {
          feedbackHtml = `<span class='voice-feedback error'>⚠️ ${escapeHtml(feedback.error)}</span>`;
        } else if (feedback.transcript) {
          const tone = feedback.rating == null ? '' : feedback.rating >= 70 ? ' good' : feedback.rating >= 40 ? ' mid' : ' weak';
          const ratingText = feedback.rating == null ? '' : ` · ${feedback.rating}%`;
          const tipText = feedback.tip ? ` · ${escapeHtml(feedback.tip)}` : '';
          feedbackHtml = `<span class='voice-feedback${tone}'>🎤 ${escapeHtml(feedback.transcript)}${ratingText}${tipText}</span>`;
        }
      }
      return `<div class='choice-wrap'>
        <button class='voice-button' type='button' data-action='voice-check' data-choice-index='${item.index}' aria-label='Сказать эту фразу' title='Произнести фразу'>🎤</button>
        <button class='choice-button' type='button' data-action='dialogue-choice' data-choice-index='${item.index}'>${escapeHtml(item.choice.line)} <span aria-hidden='true'>→</span></button>
        ${feedbackHtml}
      </div>`;
    }).join('');
    const nextButton = state.dialogueDone || state.dialogueShowAll ? `<button class='primary-button dialogue-next' type='button' data-action='dialogue-next'>${state.dialogueDone ? 'К итогам' : 'Далее'} <span aria-hidden='true'>→</span></button>` : '';
    return `<section class='screen dialogue-screen'>
      ${renderLessonTopbar('Живой диалог')}
      <div class='lesson-main'>
        <div class='section-intro'><p class='eyebrow'>Speak naturally</p><h1>Твоя сцена</h1><p>Выбирай реплику и продолжай разговор.</p></div>
        <div class='dialogue-scene'><span class='dialogue-scene-label'>Сцена</span>${escapeHtml(dialogue.scene_ru)}</div>
        <div class='conversation' aria-live='polite'>${conversation}</div>
        ${choices ? `<div class='dialogue-choices'>${choices}</div>` : ''}
        ${nextButton}
      </div>
    </section>`;
  }

  function getRepeatWords() {
    return Object.entries(state.flashcards).filter(([, known]) => known === false).map(([word]) => word);
  }

  function finishScore() {
    return numberOrNull(state.finishData && state.finishData.score) ?? state.quizScore;
  }

  function finishXp() {
    return numberOrNull(state.finishData && state.finishData.xp) ?? 0;
  }

  function nextTopicLabel(value) {
    if (isObject(value)) {
      return asString(value.title || value.name || value.topic, 'Следующая тема уже готовится');
    }
    return asString(value, 'Следующая тема уже готовится');
  }

  function renderFinish() {
    const result = state.finishData;
    if (state.finishRequesting || (!result && !state.finishError)) {
      return `<section class='screen finish-screen'><div class='lesson-main'>${renderLessonTopbar('Финал')}<div class='saving-card'><div class='saving-spinner' aria-hidden='true'></div><h2>Собираем итоги…</h2><p>Сохраняем ответы и начисляем XP.</p></div></div></section>`;
    }
    if (state.finishError) {
      return `<section class='screen finish-screen'><div class='lesson-main'>${renderLessonTopbar('Финал')}<div class='error-banner'><span class='banner-icon'>!</span><span>${escapeHtml(state.finishError)}</span></div><div class='error-actions' style='margin-top: 16px'><button class='primary-button' type='button' data-action='finish-retry'>Повторить сохранение</button><button class='ghost-button' type='button' data-action='back-menu'>Вернуться в меню</button></div></div></section>`;
    }
    const repeatWords = getRepeatWords();
    const repeatMarkup = repeatWords.length ? `<div class='review-words'>${repeatWords.map(word => `<span class='review-word'>${escapeHtml(word)}</span>`).join('')}</div>` : `<div class='review-words empty'>Все слова запомнены — отличная работа!</div>`;
    const score = finishScore();
    const xp = finishXp();
    const nextTopic = nextTopicLabel(result && result.next_topic);
    return `<section class='screen finish-screen'>
      <div class='lesson-main'>
        ${renderLessonTopbar('Финал')}
        <div class='finish-hero'><div class='finish-emoji'>${escapeHtml(state.deck ? state.deck.emoji : '✨')}</div><h1>Урок завершён!</h1><p>Ты сделал ещё один шаг к свободной речи.</p></div>
        <div class='result-grid'><div class='result-card'><span class='result-label'>Счёт квиза</span><strong class='result-value'>${displayValue(score)}</strong></div><div class='result-card accent'><span class='result-label'>Награда</span><strong class='result-value'>+${displayValue(xp)} XP</strong></div></div>
        <div class='review-card'><h3>Повторить слова</h3><p>${repeatWords.length ? 'Эти слова попадут в твой следующий круг SRS.' : 'Ты отметил все слова как знакомые.'}</p>${repeatMarkup}</div>
        <div class='next-topic'><span aria-hidden='true'>🧭</span><span><strong>Дальше:</strong> ${escapeHtml(nextTopic)}</span></div>
        <div class='finish-actions'><button class='finish-button primary' type='button' data-action='finish-restart'>↻ Ещё урок</button><button class='finish-button secondary' type='button' data-action='exit-app'>↗ Выйти в бот</button></div>
      </div>
    </section>`;
  }

  function renderError() {
    const isInit = state.errorKind === 'init';
    const title = state.errorTitle || (isInit ? 'Не удалось подключиться' : 'Урок не загрузился');
    const message = state.errorMessage || 'Попробуйте ещё раз чуть позже.';
    const retryAction = isInit ? 'retry-init' : 'retry-lesson';
    return `<section class='screen error-screen'><div class='error-card'><div class='error-icon' aria-hidden='true'>⚠️</div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(message)}</p><div class='error-actions'><button class='primary-button' type='button' data-action='${retryAction}'>Повторить</button>${!state.demo ? `<button class='secondary-button' type='button' data-action='use-demo'>Открыть демо-режим</button>` : ''}<button class='ghost-button' type='button' data-action='back-menu'>Вернуться в меню</button></div></div></section>`;
  }

  function errorMessage(error) {
    return error instanceof Error && error.message ? error.message : 'Что-то пошло не так. Попробуйте ещё раз.';
  }

  function showError(title, message, kind) {
    state.errorTitle = asString(title, 'Что-то пошло не так');
    state.errorMessage = asString(message, 'Попробуйте ещё раз чуть позже.');
    state.errorKind = kind || 'lesson';
    state.screen = 'error';
    state.loading = false;
    setClosingConfirmation(false);
    render();
  }

  function goBackToMenu() {
    state.startRequestId += 1;
    state.loading = false;
    state.errorTitle = '';
    state.errorMessage = '';
    state.errorKind = '';
    resetLessonState();
    setClosingConfirmation(false);
    state.screen = 'menu';
    render();
  }

  function openSection(section) {
    state.screen = section;
    resetSectionState(section);
    render();
  }

  function advanceFromSection() {
    if (state.sectionIndex + 1 < state.sequence.length) {
      state.sectionIndex += 1;
      const section = state.sequence[state.sectionIndex];
      openSection(section);
      return;
    }
    openFinish();
  }

  function changePresentation(delta) {
    const items = getPresentationItems();
    if (!items.length) {
      return;
    }
    if (delta > 0 && state.presentationIndex >= items.length - 1) {
      advanceFromSection();
      return;
    }
    state.presentationIndex = Math.max(0, Math.min(items.length - 1, state.presentationIndex + delta));
    haptic('light');
    render();
  }

  function handleSurfaceTap(event, surface) {
    if (Date.now() < ignoreSurfaceClickUntil) {
      return;
    }
    const rect = surface.getBoundingClientRect();
    const x = Number.isFinite(event.clientX) && event.clientX ? event.clientX : rect.left + rect.width / 2;
    changePresentation(x < rect.left + rect.width * 0.36 ? -1 : 1);
  }

  function markCard(known) {
    const cards = state.deck ? state.deck.vocabulary : [];
    if (!cards.length) {
      return;
    }
    const card = cards[state.cardIndex];
    state.flashcards[card.word] = Boolean(known);
    haptic(known ? 'success' : 'warning');
    if (state.cardIndex < cards.length - 1) {
      state.cardIndex += 1;
      state.cardFlipped = false;
      render();
      return;
    }
    advanceFromSection();
  }

  function toggleCard() {
    state.cardFlipped = !state.cardFlipped;
    haptic('light');
    render();
  }

  function makeAudioSource(data) {
    if (!isObject(data)) {
      return '';
    }
    const base64 = asString(data.audio_base64 || data.audio);
    if (base64) {
      if (base64.startsWith('data:')) {
        return base64;
      }
      return `data:audio/mpeg;base64,${base64}`;
    }
    const url = asString(data.url || data.audio_url);
    if (/^https:\/\//i.test(url) || /^http:\/\//i.test(url) || url.startsWith('/')) {
      return url;
    }
    return '';
  }

  async function apiTTS(text) {
    const word = asString(text, 'word');
    if (state.demo) {
      if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
        throw new Error('Озвучка недоступна в этом браузере.');
      }
      const utterance = new SpeechSynthesisUtterance(word);
      utterance.lang = 'en-US';
      utterance.rate = 0.88;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      return;
    }
    const data = await apiPost('/api/tts', { text: word, word });
    const source = makeAudioSource(data);
    if (!source) {
      throw new Error('Сервер не вернул аудио для этого слова.');
    }
    if (typeof Audio !== 'function') {
      throw new Error('Браузер не поддерживает воспроизведение аудио.');
    }
    const audio = new Audio(source);
    await audio.play();
  }

  async function answerQuiz(optionIndex) {
    const questions = state.deck ? state.deck.quiz : [];
    if (!questions.length || state.quizSelected !== null) {
      return;
    }
    const index = state.quizIndex;
    const question = questions[index];
    const localCorrect = optionIndex === question.answer_index;
    const requestId = ++state.quizRequestId;
    state.quizSelected = optionIndex;
    state.quizScore += localCorrect ? 1 : 0;
    state.quizAnswers[index] = {
      question_index: index,
      index,
      chosen: optionIndex,
      selected_index: optionIndex,
      answer_index: question.answer_index,
      correct: localCorrect,
      explanation: question.explanation_ru
    };
    state.quizFeedbackError = '';
    haptic(localCorrect ? 'success' : 'error');
    render();
    state.quizPending = true;
    render();
    try {
      const data = await apiPost('/api/deck/answer', {
        session_id: state.sessionId,
        question_index: index,
        index,
        answer_index: optionIndex,
        selected_index: optionIndex
      });
      if (requestId !== state.quizRequestId) {
        return;
      }
      const rawCorrect = data.correct ?? data.is_correct;
      const serverNumber = numberOrNull(rawCorrect);
      const serverCorrect = typeof rawCorrect === 'boolean' ? rawCorrect : rawCorrect === 'true' ? true : rawCorrect === 'false' ? false : serverNumber !== null ? serverNumber !== 0 : localCorrect;
      const current = state.quizAnswers[index];
      if (current) {
        if (serverCorrect !== localCorrect) {
          state.quizScore += serverCorrect ? 1 : -1;
        }
        current.correct = serverCorrect;
        current.explanation = asString(data.explanation || data.explanation_ru, current.explanation || '');
      }
    } catch (error) {
      if (requestId === state.quizRequestId) {
        state.quizFeedbackError = errorMessage(error);
      }
    } finally {
      if (requestId === state.quizRequestId && state.screen === 'quiz' && state.quizIndex === index && state.quizSelected === optionIndex) {
        state.quizPending = false;
        render();
      }
    }
  }

  function nextQuizQuestion() {
    if (state.quizPending) {
      return;
    }
    const questions = state.deck ? state.deck.quiz : [];
    if (!questions.length) {
      advanceFromSection();
      return;
    }
    if (state.quizIndex >= questions.length - 1) {
      advanceFromSection();
      return;
    }
    state.quizIndex += 1;
    state.quizSelected = null;
    state.quizFeedbackError = '';
    state.quizPending = false;
    haptic('light');
    render();
  }

  function resolveDialogueNext(choice) {
    const lines = state.deck.dialogue.lines;
    if (choice.next === null || choice.next === '') {
      return -1;
    }
    let value = choice.next;
    if (value === undefined) {
      const following = state.dialogueIndex + 1;
      return following < lines.length ? following : -1;
    }
    if (isObject(value)) {
      value = value.index ?? value.line_index ?? value.id ?? value.line;
    }
    const numeric = numberOrNull(value);
    if (numeric !== null) {
      let next = Math.trunc(numeric);
      if (next === state.dialogueIndex) {
        next += 1;
      }
      return next >= 0 && next < lines.length ? next : -1;
    }
    const text = asString(value);
    const found = lines.findIndex(line => String(line.id) === text || line.line === text);
    return found >= 0 ? found : -1;
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = () => reject(new Error('Не удалось прочитать запись'));
      reader.readAsDataURL(blob);
    });
  }

  async function checkSpokenPhrase(choiceIndex) {
    const item = getDialogueChoices().find(candidate => candidate.index === Number(choiceIndex));
    if (!item) {
      return;
    }
    if (!window.MediaRecorder || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      state.voiceFeedback[item.index] = { error: 'Запись недоступна в этом клиенте' };
      render();
      return;
    }
    if (state.voiceFeedback[item.index] && state.voiceFeedback[item.index].busy) {
      return;
    }
    state.voiceFeedback[item.index] = { busy: true };
    render();
    const chunks = [];
    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const stopped = new Promise(resolve => {
        recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
        recorder.onstop = () => resolve();
      });
      recorder.start();
      await delay(3500);
      recorder.stop();
      await stopped;
      if (!chunks.length) {
        throw new Error('Запись пустая');
      }
      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
      const audioBase64 = await blobToBase64(blob);
      const data = await apiPost('/api/voice/answer', {
        audio_base64: audioBase64,
        expected_line: item.choice.line
      });
      state.voiceFeedback[item.index] = {
        transcript: asString(data.transcript, ''),
        rating: numberOrNull(data.rating),
        tip: asString(data.tip, '')
      };
    } catch (error) {
      state.voiceFeedback[item.index] = { error: error && error.message ? error.message : 'Не удалось записать голос' };
    } finally {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
      render();
    }
  }

  function chooseDialogue(choiceIndex) {
    const item = getDialogueChoices().find(candidate => candidate.index === Number(choiceIndex));
    if (!item) {
      return;
    }
    const lines = state.deck.dialogue.lines;
    state.dialogueUsedChoices.add(item.index);
    state.dialogueLog.push({ type: 'user', character: 'Ты', line: item.choice.line });
    const nextIndex = resolveDialogueNext(item.choice);
    if (nextIndex < 0 || nextIndex >= lines.length || nextIndex <= state.dialogueIndex) {
      state.dialogueDone = true;
    } else {
      state.dialogueIndex = nextIndex;
      state.dialogueLog.push({ type: 'line', ...lines[nextIndex] });
    }
    haptic('medium');
    render();
  }

  function openFinish() {
    state.screen = 'finish';
    state.finishData = null;
    state.finishError = '';
    render();
    requestFinish();
  }

  function delay(milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds));
  }

  async function requestFinish() {
    if (state.finishRequesting) {
      return;
    }
    const requestId = state.finishRequestId;
    state.finishRequesting = true;
    state.finishError = '';
    render();
    const payload = {
      session_id: state.sessionId,
      preset: state.deck ? state.deck.preset : 'mixed',
      score: state.quizScore,
      quiz_answers: state.quizAnswers,
      answers: state.quizAnswers,
      flashcards: state.flashcards,
      words: state.flashcards
    };
    try {
      if (state.demo) {
        await delay(500);
        if (requestId !== state.finishRequestId) {
          return;
        }
        state.finishData = {
          xp: 35 + state.quizScore * 10,
          score: state.quizScore,
          next_topic: getSuggestedTopics()[0] || defaultTopics[0]
        };
      } else {
        const data = await apiPost('/api/deck/finish', payload);
        if (requestId !== state.finishRequestId) {
          return;
        }
        state.finishData = {
          xp: numberOrNull(data.xp) ?? 0,
          score: numberOrNull(data.score) ?? state.quizScore,
          next_topic: data.next_topic
        };
      }
      setClosingConfirmation(false);
    } catch (error) {
      if (requestId === state.finishRequestId) {
        state.finishError = `Не удалось сохранить итоги: ${errorMessage(error)}`;
      }
    } finally {
      if (requestId === state.finishRequestId) {
        state.finishRequesting = false;
        if (state.screen === 'finish') {
          render();
        }
      }
    }
  }

  async function startLesson() {
    if (state.loading) {
      return;
    }
    state.errorTitle = '';
    state.errorMessage = '';
    state.errorKind = '';
    resetLessonState();
    state.loading = true;
    state.screen = 'loading';
    setClosingConfirmation(true);
    render();
    const requestId = ++state.startRequestId;
    try {
      let data;
      if (state.demo) {
        await delay(720);
        data = { ok: true, deck: clone(demoDeck), session_id: 'demo-session' };
      } else {
        data = await apiPost('/api/deck/new', { topic: state.selectedTopic, preset: 'mixed' });
      }
      if (requestId !== state.startRequestId) {
        return;
      }
      if (!isObject(data.deck)) {
        throw new Error('Сервер вернул урок без дека. Попробуйте ещё раз.');
      }
      state.deck = normalizeDeck(data.deck);
      state.sessionId = data.session_id ?? null;
      const quota = numberOrNull(state.profile.quota_left);
      if (quota !== null && quota > 0) {
        state.profile.quota_left = quota - 1;
      }
      state.loading = false;
      state.sequence = getLessonSequence();
      state.sectionIndex = 0;
      if (!state.sequence.length) {
        openFinish();
        return;
      }
      openSection(state.sequence[0]);
    } catch (error) {
      if (requestId !== state.startRequestId) {
        return;
      }
      state.loading = false;
      resetLessonState();
      showError('Урок не загрузился', errorMessage(error), 'lesson');
    }
  }

  async function initialize() {
    applyTheme();
    if (telegram) {
      try {
        if (typeof telegram.ready === 'function') {
          telegram.ready();
        }
        if (typeof telegram.expand === 'function') {
          telegram.expand();
        }
        if (typeof telegram.onEvent === 'function') {
          telegram.onEvent('themeChanged', applyTheme);
        }
      } catch (error) {
        void error;
      }
    }
    state.initData = getInitData();
    setClosingConfirmation(false);
    if (!state.initData) {
      state.demo = true;
      state.profile = { ...defaultProfile };
      state.selectedTopic = '';
      render();
      return;
    }
    state.demo = false;
    state.profile = { ...defaultProfile };
    state.selectedTopic = '';
    render();
    try {
      const data = await apiPost('/api/init', {});
      state.profile = normalizeProfile(data);
      state.selectedTopic = '';
      render();
    } catch (error) {
      showError('Не удалось подключиться', errorMessage(error), 'init');
    }
  }

  function showComingSoon() {
    if (typeof window.alert === 'function') {
      window.alert('скоро');
      return;
    }
    showToast('скоро');
  }

  function closeApp() {
    setClosingConfirmation(false);
    if (telegram && typeof telegram.close === 'function') {
      try {
        telegram.close();
        return;
      } catch (error) {
        void error;
      }
    }
    if (typeof window.close === 'function') {
      window.close();
      return;
    }
    showToast('Откройте Mini App из Telegram, чтобы выйти в бот.', true);
  }

  function chooseRandomTopic() {
    const pool = uniqueStrings([...getSuggestedTopics(), ...defaultTopics]);
    if (!pool.length) {
      return;
    }
    const currentIndex = pool.indexOf(state.selectedTopic);
    let nextIndex = Math.floor(Math.random() * pool.length);
    if (pool.length > 1 && nextIndex === currentIndex) {
      nextIndex = (nextIndex + 1) % pool.length;
    }
    state.selectedTopic = pool[nextIndex];
    render();
  }

  function handleClick(event) {
    const target = event.target;
    const actionNode = target && typeof target.closest === 'function' ? target.closest('[data-action]') : null;
    if (!actionNode) {
      return;
    }
    event.preventDefault();
    const action = actionNode.dataset.action;
    if (action === 'select-topic') {
      state.selectedTopic = actionNode.dataset.topic || '';
      render();
    } else if (action === 'random-topic') {
      chooseRandomTopic();
    } else if (action === 'start-lesson' || action === 'retry-lesson') {
      startLesson();
    } else if (action === 'personality-stub' || action === 'interests-stub') {
      showComingSoon();
    } else if (action === 'back-menu') {
      goBackToMenu();
    } else if (action === 'premium-upsell') {
      showToast('Открой бота и отправь /premium 💎', true);
    } else if (action === 'use-demo') {
      state.demo = true;
      state.profile = { ...defaultProfile };
      state.errorTitle = '';
      state.errorMessage = '';
      state.errorKind = '';
      resetLessonState();
      setClosingConfirmation(false);
      state.screen = 'menu';
      render();
    } else if (action === 'retry-init') {
      initialize();
    } else if (action === 'presentation-prev') {
      changePresentation(-1);
    } else if (action === 'presentation-next') {
      changePresentation(1);
    } else if (action === 'presentation-dot') {
      state.presentationIndex = Number(actionNode.dataset.index) || 0;
      haptic('light');
      render();
    } else if (action === 'presentation-surface') {
      handleSurfaceTap(event, actionNode);
    } else if (action === 'card-flip') {
      toggleCard();
    } else if (action === 'card-speak') {
      const word = actionNode.dataset.word || '';
      apiTTS(word).catch(error => showToast(errorMessage(error), true));
    } else if (action === 'card-mark') {
      markCard(actionNode.dataset.known === 'true');
    } else if (action === 'quiz-answer') {
      answerQuiz(Number(actionNode.dataset.index));
    } else if (action === 'quiz-next') {
      nextQuizQuestion();
    } else if (action === 'dialogue-choice') {
      chooseDialogue(actionNode.dataset.choiceIndex);
    } else if (action === 'voice-check') {
      checkSpokenPhrase(Number(actionNode.dataset.choiceIndex));
    } else if (action === 'dialogue-next') {
      if (state.dialogueDone || state.dialogueShowAll) {
        advanceFromSection();
      }
    } else if (action === 'finish-retry') {
      requestFinish();
    } else if (action === 'finish-restart') {
      goBackToMenu();
    } else if (action === 'exit-app') {
      closeApp();
    }
  }

  function handleKeydown(event) {
    const target = event.target;
    const isControl = target && typeof target.closest === 'function' && target.closest('button, input, textarea, select');
    if (event.key === 'Escape' && state.screen !== 'menu') {
      event.preventDefault();
      goBackToMenu();
      return;
    }
    if (state.screen === 'presentation') {
      if (event.key === 'ArrowRight' || event.code === 'Space') {
        event.preventDefault();
        changePresentation(1);
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        changePresentation(-1);
      } else if (event.key === 'Enter' && target && typeof target.closest === 'function' && target.closest('.presentation-surface')) {
        event.preventDefault();
        const surface = target.closest('.presentation-surface');
        handleSurfaceTap({ clientX: surface.getBoundingClientRect().left + surface.getBoundingClientRect().width / 2 }, surface);
      }
      return;
    }
    if (state.screen === 'quiz' && !isControl && /^[1-9]$/.test(event.key)) {
      const index = Number(event.key) - 1;
      if (state.deck && state.deck.quiz[state.quizIndex] && state.deck.quiz[state.quizIndex].options[index] !== undefined) {
        event.preventDefault();
        answerQuiz(index);
      }
    }
  }

  function handleTouchStart(event) {
    const touch = event.touches && event.touches[0];
    if (touch) {
      touchStart = { x: touch.clientX, y: touch.clientY };
    }
  }

  function handleTouchEnd(event) {
    if (!touchStart || state.screen !== 'presentation') {
      touchStart = null;
      return;
    }
    const touch = event.changedTouches && event.changedTouches[0];
    if (!touch) {
      touchStart = null;
      return;
    }
    const deltaX = touch.clientX - touchStart.x;
    const deltaY = touch.clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY)) {
      ignoreSurfaceClickUntil = Date.now() + 350;
      changePresentation(deltaX < 0 ? 1 : -1);
    }
  }

  if (app) {
    app.addEventListener('click', handleClick);
    app.addEventListener('touchstart', handleTouchStart, { passive: true });
    app.addEventListener('touchend', handleTouchEnd, { passive: true });
    document.addEventListener('keydown', handleKeydown);
    initialize();
  }
})();
