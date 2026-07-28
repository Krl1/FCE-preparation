"use strict";

// --- i18n --------------------------------------------------------------------

const I18N = {
  pl: {
    "app.title": "FCE Trener",
    "tab.practice": "Ćwicz",
    "tab.tips": "Tipy",
    "tab.external": "Sprawdź z zewnątrz",
    "tab.errors": "Moje błędy",
    "tips.today": "dzisiaj",
    "tips.goalLabel": "Dzienny cel",
    "tips.goalSave": "Zapisz cel",
    "tips.newError": "Inny błąd",
    "tips.generate": "Ćwiczenie",
    "tips.more": "Kolejne ćwiczenie",
    "tips.streakDays": "dni w serii",
    "tips.empty": "Dziennik błędów jest pusty — rozwiąż lub wklej kilka zadań, a tu pojawią się tipy.",
    "errors.practiceThis": "Ćwicz ten błąd",
    "tab.stats": "Statystyki",
    "stats.learning": "Nauka",
    "stats.usage": "Zużycie Claude",
    "stats.usageNote": "Koszt liczony wg stawek API. Tryb headless niesie narzut systemowego promptu Claude Code, więc to górna granica — aplikacja na API zużyłaby mniej.",
    "stats.empty": "Brak danych — zacznij korzystać z aplikacji.",
    "stats.exercisesGenerated": "Wygenerowane ćwiczenia",
    "stats.attempts": "Sprawdzone odpowiedzi",
    "stats.accuracy": "Skuteczność",
    "stats.reviews": "Przerobione powtórki",
    "stats.errorsLogged": "Błędy w dzienniku",
    "stats.byType": "Wg typu zadania",
    "stats.calls": "Wywołania modelu",
    "stats.tokensIn": "Tokeny wejściowe",
    "stats.tokensOut": "Tokeny wyjściowe",
    "stats.tokensCacheWrite": "Tokeny cache (zapis)",
    "stats.tokensCacheRead": "Tokeny cache (odczyt)",
    "stats.cost": "Koszt trybu headless (górna granica)",
    "stats.avgTime": "Średni czas odpowiedzi",
    "stats.leanTitle": "Szacunek na API (bez narzutu)",
    "stats.leanUsed": "Przy tym samym modelu",
    "stats.leanSonnet": "Na tańszym modelu (Sonnet 5)",
    "stats.leanNote": "Liczone tylko z realnego promptu i odpowiedzi (bez narzutu Claude Code, ~4 znaki/token). Z cache'owaniem promptu na API będzie jeszcze taniej.",
    "stats.byKind": "Wg rodzaju wywołania",
    "kind.generate": "Generowanie zadań",
    "kind.grade": "Sprawdzanie",
    "kind.drill": "Ćwiczenia do błędów (Tipy)",
    "kind.explain": "Wyjaśnienia",
    "kind.extract": "Import (ekstrakcja)",
    "kind.other": "Inne",
    "practice.type": "Typ ćwiczenia",
    "practice.topic": "Temat (opcjonalnie)",
    "practice.topic.auto": "— dobierz automatycznie (wg moich błędów) —",
    "btn.generate": "Generuj zadanie",
    "btn.grade": "Sprawdź odpowiedź",
    "external.intro": "Wklej zadanie z książki lub od korepetytora oraz swoją odpowiedź — sprawdzę je i zapiszę błędy.",
    "external.type": "Typ ćwiczenia",
    "external.keyword": "Słowo-klucz (key word)",
    "external.question": "Treść zadania",
    "external.question.ph": "Wklej treść / polecenie zadania…",
    "external.answer": "Twoja odpowiedź",
    "external.answer.ph": "Wpisz swoją odpowiedź…",
    "btn.gradeExternal": "Sprawdź",
    "errors.weak": "Słabe punkty",
    "errors.journal": "Dziennik błędów",
    "btn.refresh": "Odśwież",
    "loader.default": "Pracuję…",
    "loader.generating": "Generuję zadanie…",
    "loader.grading": "Sprawdzam odpowiedź…",
    "loader.gradingExt": "Sprawdzam zadanie…",
    "loader.loading": "Wczytuję…",
    "topic.prefix": "Temat: ",
    "kw.label": "Słowo-klucz: ",
    "answer.ph": "Twoja odpowiedź…",
    "writing.ph": "Napisz swój tekst po angielsku…",
    "alert.answer": "Wpisz lub wybierz odpowiedź.",
    "alert.answerAll": "Odpowiedz na wszystkie luki.",
    "verdict.score": "Wynik:",
    "alert.fillExternal": "Uzupełnij treść zadania i odpowiedź.",
    "verdict.correct": "✓ Poprawnie",
    "verdict.incorrect": "✗ Do poprawy",
    "band.prefix": "Orientacyjna ocena: ",
    "corrected.label": "Poprawna wersja:",
    "result.optionNotes": "Dlaczego pozostałe warianty",
    "errors.detected": "Wykryte błędy",
    "noErrors": "Brak błędów. Świetna robota!",
    "error.prefix": "Błąd: ",
    "stats.empty": "Brak błędów w dzienniku — rozwiąż kilka zadań.",
    "journal.empty": "Dziennik jest pusty.",
    "taxonomy.fail": "Nie udało się wczytać taksonomii: ",
  },
  en: {
    "app.title": "FCE Trainer",
    "tab.practice": "Practice",
    "tab.tips": "Tips",
    "tab.external": "Check external",
    "tab.errors": "My mistakes",
    "tips.today": "today",
    "tips.goalLabel": "Daily goal",
    "tips.goalSave": "Save goal",
    "tips.newError": "Another mistake",
    "tips.generate": "Exercise",
    "tips.more": "Another exercise",
    "tips.streakDays": "day streak",
    "tips.empty": "Your mistake log is empty — do or paste a few exercises and tips will appear here.",
    "errors.practiceThis": "Practice this mistake",
    "tab.stats": "Statistics",
    "stats.learning": "Learning",
    "stats.usage": "Claude usage",
    "stats.usageNote": "Cost is at API rates. Headless mode carries Claude Code's system-prompt overhead, so this is an upper bound — an API app would use less.",
    "stats.empty": "No data yet — start using the app.",
    "stats.exercisesGenerated": "Exercises generated",
    "stats.attempts": "Answers checked",
    "stats.accuracy": "Accuracy",
    "stats.reviews": "Reviews completed",
    "stats.errorsLogged": "Mistakes logged",
    "stats.byType": "By exercise type",
    "stats.calls": "Model calls",
    "stats.tokensIn": "Input tokens",
    "stats.tokensOut": "Output tokens",
    "stats.tokensCacheWrite": "Cache tokens (write)",
    "stats.tokensCacheRead": "Cache tokens (read)",
    "stats.cost": "Headless cost (upper bound)",
    "stats.avgTime": "Avg response time",
    "stats.leanTitle": "API estimate (no overhead)",
    "stats.leanUsed": "Same model as used",
    "stats.leanSonnet": "On a cheaper model (Sonnet 5)",
    "stats.leanNote": "Counted from the real prompt and response only (no Claude Code overhead, ~4 chars/token). With API prompt caching it would be even lower.",
    "stats.byKind": "By call type",
    "kind.generate": "Exercise generation",
    "kind.grade": "Grading",
    "kind.drill": "Mistake drills (Tips)",
    "kind.explain": "Explanations",
    "kind.extract": "Import (extraction)",
    "kind.other": "Other",
    "practice.type": "Exercise type",
    "practice.topic": "Topic (optional)",
    "practice.topic.auto": "— auto-select (by my mistakes) —",
    "btn.generate": "Generate exercise",
    "btn.grade": "Check answer",
    "external.intro": "Paste an exercise from a book or your tutor together with your answer — I'll check it and log the mistakes.",
    "external.type": "Exercise type",
    "external.keyword": "Key word",
    "external.question": "Exercise text",
    "external.question.ph": "Paste the exercise / prompt…",
    "external.answer": "Your answer",
    "external.answer.ph": "Type your answer…",
    "btn.gradeExternal": "Check",
    "errors.weak": "Weak points",
    "errors.journal": "Mistake log",
    "btn.refresh": "Refresh",
    "loader.default": "Working…",
    "loader.generating": "Generating exercise…",
    "loader.grading": "Checking answer…",
    "loader.gradingExt": "Checking…",
    "loader.loading": "Loading…",
    "topic.prefix": "Topic: ",
    "kw.label": "Key word: ",
    "answer.ph": "Your answer…",
    "writing.ph": "Write your text in English…",
    "alert.answer": "Enter or select an answer.",
    "alert.answerAll": "Answer every gap.",
    "verdict.score": "Score:",
    "alert.fillExternal": "Fill in the exercise text and your answer.",
    "verdict.correct": "✓ Correct",
    "verdict.incorrect": "✗ Needs work",
    "band.prefix": "Estimated band: ",
    "corrected.label": "Correct version:",
    "result.optionNotes": "Why the other options",
    "errors.detected": "Detected mistakes",
    "noErrors": "No mistakes. Great job!",
    "error.prefix": "Error: ",
    "stats.empty": "No mistakes logged yet — do a few exercises.",
    "journal.empty": "The log is empty.",
    "taxonomy.fail": "Failed to load taxonomy: ",
  },
};

let LANG = localStorage.getItem("fce_lang") === "en" ? "en" : "pl";
const t = (key) => (I18N[LANG] && I18N[LANG][key]) || I18N.pl[key] || key;

// --- Stan i pomocnicze -------------------------------------------------------

let TAXONOMY = { exercise_types: [], topics: [] };
let TOPIC_LABELS = {}; // id -> {pl, en}
let currentExercise = null;

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const topicLabel = (id) => (TOPIC_LABELS[id] && TOPIC_LABELS[id][LANG]) || id;
const typeLabelOf = (typ) => (LANG === "en" ? typ.label_en : typ.label) || typ.label;

function showLoader(key) { $("#loader-text").textContent = t(key || "loader.default"); $("#loader").classList.remove("hidden"); }
function hideLoader() { $("#loader").classList.add("hidden"); }

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function isWritingType(typeId) {
  const t2 = TAXONOMY.exercise_types.find((x) => x.id === typeId);
  return t2 && t2.area === "writing";
}

// --- Przełącznik języka ------------------------------------------------------

function applyStaticI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = t(n.dataset.i18nPh); });
}

function setLang(lang) {
  LANG = lang === "en" ? "en" : "pl";
  localStorage.setItem("fce_lang", LANG);
  document.querySelectorAll(".lang").forEach((b) => b.classList.toggle("is-active", b.dataset.lang === LANG));
  applyStaticI18n();
  fillTypeSelects();
  populateTopics();
  if ($("#view-errors").classList.contains("is-active")) loadErrors();
  if ($("#view-tips").classList.contains("is-active")) loadTips();
  if ($("#view-stats").classList.contains("is-active")) loadStats();
}

document.querySelectorAll(".lang").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));

// --- Nawigacja zakładek ------------------------------------------------------

function activateTab(view) {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("is-active", x.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
  $("#view-" + view).classList.add("is-active");
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.view);
    if (tab.dataset.view === "errors") loadErrors();
    if (tab.dataset.view === "tips") loadTips();
    if (tab.dataset.view === "stats") loadStats();
  });
});

// --- Inicjalizacja taksonomii ------------------------------------------------

async function init() {
  applyStaticI18n();
  document.querySelectorAll(".lang").forEach((b) => b.classList.toggle("is-active", b.dataset.lang === LANG));
  try {
    TAXONOMY = await api("/api/taxonomy");
  } catch (e) {
    document.body.prepend(el("div", "error-banner", t("taxonomy.fail") + esc(e.message)));
    return;
  }
  TAXONOMY.topics.forEach((tp) => { TOPIC_LABELS[tp.id] = { pl: tp.label, en: tp.label_en }; });

  fillTypeSelects();
  $("#practice-type").addEventListener("change", populateTopics);
  $("#external-type").addEventListener("change", toggleExternalKeyword);
  populateTopics();
  toggleExternalKeyword();
}

function fillTypeSelects() {
  [["#practice-type"], ["#external-type"]].forEach(([sel]) => {
    const node = $(sel);
    if (!node) return;
    const prev = node.value;
    node.innerHTML = "";
    TAXONOMY.exercise_types.forEach((typ) => {
      const opt = el("option");
      opt.value = typ.id; opt.textContent = typeLabelOf(typ);
      node.appendChild(opt);
    });
    if (prev) node.value = prev;
  });
}

function populateTopics() {
  const typeId = $("#practice-type").value;
  const typ = TAXONOMY.exercise_types.find((x) => x.id === typeId);
  const sel = $("#practice-topic");
  const prev = sel.value;
  sel.innerHTML = "";
  const auto = el("option");
  auto.value = ""; auto.textContent = t("practice.topic.auto");
  sel.appendChild(auto);
  (typ ? typ.topics : []).forEach((topicId) => {
    const opt = el("option");
    opt.value = topicId; opt.textContent = topicLabel(topicId);
    sel.appendChild(opt);
  });
  if (prev) sel.value = prev;
}

function toggleExternalKeyword() {
  const isKwt = $("#external-type").value === "uoe_part4_key_word_transformation";
  $("#external-keyword-wrap").classList.toggle("hidden", !isKwt);
}

// --- Ćwicz: generowanie ------------------------------------------------------

$("#btn-generate").addEventListener("click", async () => {
  const type = $("#practice-type").value;
  const topic = $("#practice-topic").value || null;
  $("#practice-result").classList.add("hidden");
  showLoader("loader.generating");
  try {
    currentExercise = await api("/api/exercise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, topic, lang: LANG }),
    });
    renderExercise(currentExercise);
  } catch (e) {
    showError("#exercise-area", e.message);
  } finally { hideLoader(); }
});

function renderExercise(ex) {
  $("#exercise-topic").textContent = t("topic.prefix") + topicLabel(ex.topic);
  $("#exercise-instructions").textContent = ex.instructions || "";
  let q = esc(ex.question_text || "");
  if (ex.key_word) q += `\n\n${esc(t("kw.label"))}<span class="kw">${esc(ex.key_word)}</span>`;
  $("#exercise-question").innerHTML = q;

  const area = $("#answer-area");
  area.innerHTML = "";
  if (ex.items && ex.items.length) {
    // Zadanie wieloczęściowe: jedna grupa wariantów na każdą lukę.
    const wrap = el("div", "gap-items");
    ex.items.forEach((item) => {
      const block = el("div", "gap-item");
      block.appendChild(el("span", "gap-num", esc(String(item.number))));
      const opts = el("div", "options options-inline");
      item.options.forEach((opt) => {
        const lbl = el("label");
        lbl.innerHTML = `<input type="radio" name="mcq-${esc(String(item.number))}" value="${esc(opt)}"> ${esc(opt)}`;
        opts.appendChild(lbl);
      });
      block.appendChild(opts);
      wrap.appendChild(block);
    });
    area.appendChild(wrap);
  } else if (ex.options && ex.options.length) {
    const wrap = el("div", "options");
    ex.options.forEach((opt) => {
      const lbl = el("label");
      lbl.innerHTML = `<input type="radio" name="mcq" value="${esc(opt)}"> ${esc(opt)}`;
      wrap.appendChild(lbl);
    });
    area.appendChild(wrap);
  } else {
    const input = el(isWritingType(ex.type) ? "textarea" : "input");
    input.id = "practice-answer";
    if (isWritingType(ex.type)) { input.rows = 10; input.placeholder = t("writing.ph"); }
    else { input.type = "text"; input.placeholder = t("answer.ph"); }
    area.appendChild(input);
  }
  $("#exercise-area").classList.remove("hidden");
}

$("#btn-grade").addEventListener("click", async () => {
  if (!currentExercise) return;
  const body = { type: currentExercise.type, exercise_id: currentExercise.id, lang: LANG };

  if (currentExercise.items && currentExercise.items.length) {
    const answers = currentExercise.items.map((item) => {
      const c = document.querySelector(`input[name="mcq-${item.number}"]:checked`);
      return c ? c.value : "";
    });
    if (answers.some((a) => !a)) { alert(t("alert.answerAll")); return; }
    body.student_answers = answers;
  } else {
    const checked = document.querySelector('input[name="mcq"]:checked');
    const inp = $("#practice-answer");
    const answer = checked ? checked.value : (inp ? inp.value.trim() : "");
    if (!answer) { alert(t("alert.answer")); return; }
    body.student_answer = answer;
  }

  showLoader("loader.grading");
  try {
    const result = await api("/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderResult("#practice-result", result);
  } catch (e) {
    showError("#practice-result", e.message);
  } finally { hideLoader(); }
});

// --- Sprawdź z zewnątrz ------------------------------------------------------

$("#btn-grade-external").addEventListener("click", async () => {
  const type = $("#external-type").value;
  const question_text = $("#external-question").value.trim();
  const student_answer = $("#external-answer").value.trim();
  const key_word = $("#external-keyword").value.trim() || null;
  if (!question_text || !student_answer) { alert(t("alert.fillExternal")); return; }

  showLoader("loader.gradingExt");
  try {
    const result = await api("/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, question_text, student_answer, key_word, lang: LANG }),
    });
    renderResult("#external-result", result);
  } catch (e) {
    showError("#external-result", e.message);
  } finally { hideLoader(); }
});

// --- Renderowanie wyniku oceny ----------------------------------------------

function renderResult(sel, r) {
  const box = $(sel);
  box.innerHTML = "";
  box.classList.remove("hidden");

  if (r.score) {
    box.appendChild(el("div", "verdict " + (r.correct ? "good" : "partial"),
      t("verdict.score") + " " + esc(r.score)));
  } else if (r.correct !== null && r.correct !== undefined) {
    box.appendChild(el("div", "verdict " + (r.correct ? "good" : "bad"),
      r.correct ? t("verdict.correct") : t("verdict.incorrect")));
  }
  if (r.band) box.appendChild(el("p", "band", t("band.prefix") + esc(r.band)));

  if (Array.isArray(r.scores) && r.scores.length) {
    const wrap = el("div", "scores");
    r.scores.forEach((s) => {
      const row = el("div", "score-row");
      row.innerHTML =
        `<span class="name">${esc(topicLabel(s.criterion))}</span>` +
        `<span class="bar"><span style="width:${(s.score / 5) * 100}%"></span></span>` +
        `<span class="count">${esc(s.score)}/5</span>`;
      wrap.appendChild(row);
      if (s.comment) wrap.appendChild(el("p", "why", esc(s.comment)));
    });
    box.appendChild(wrap);
  }

  if (r.corrected) box.appendChild(el("div", "corrected", `<strong>${esc(t("corrected.label"))}</strong> ` + esc(r.corrected)));
  if (r.feedback) box.appendChild(el("p", "feedback", esc(r.feedback)));

  // Zadanie wieloczęściowe: wynik i omówienie każdej luki.
  if (Array.isArray(r.items) && r.items.length) {
    r.items.forEach((item) => {
      const block = el("div", "res-item " + (item.correct ? "ok" : "bad"));
      let head =
        `<span class="ri-num">${esc(String(item.number))}</span>` +
        `<span class="ri-mark">${item.correct ? "✓" : "✗"}</span>`;
      if (item.correct) {
        head += `<span class="to">${esc(item.correct_option)}</span>`;
      } else {
        head += `<span class="from">${esc(item.student_option || "—")}</span> → ` +
                `<span class="to">${esc(item.correct_option)}</span>`;
      }
      block.innerHTML = `<div class="ri-head">${head}</div>` +
        (item.comment ? `<div class="why">${esc(item.comment)}</div>` : "");
      if (Array.isArray(item.option_notes) && item.option_notes.length) {
        const wrap = el("div", "opt-notes");
        item.option_notes.forEach((o) => {
          const note = el("div", "opt-note " + (o.is_correct ? "ok" : "bad"));
          note.innerHTML =
            `<span class="opt">${o.is_correct ? "✓" : "✗"} ${esc(o.option)}</span>` +
            `<span class="opt-why">${esc(o.comment)}</span>`;
          wrap.appendChild(note);
        });
        block.appendChild(wrap);
      }
      box.appendChild(block);
    });
  }

  if (Array.isArray(r.option_notes) && r.option_notes.length) {
    box.appendChild(el("h2", null, t("result.optionNotes")));
    const wrap = el("div", "opt-notes");
    r.option_notes.forEach((o) => {
      const item = el("div", "opt-note " + (o.is_correct ? "ok" : "bad"));
      item.innerHTML =
        `<span class="opt">${o.is_correct ? "✓" : "✗"} ${esc(o.option)}</span>` +
        `<span class="opt-why">${esc(o.comment)}</span>`;
      wrap.appendChild(item);
    });
    box.appendChild(wrap);
  }

  const hasItems = Array.isArray(r.items) && r.items.length;
  if (Array.isArray(r.errors) && r.errors.length && !hasItems) {
    // Przy zadaniach wieloczęściowych bloki per luka już pokazują błędy — nie dublujemy.
    box.appendChild(el("h2", null, t("errors.detected") + " (" + r.errors.length + ")"));
    r.errors.forEach((err) => {
      const item = el("div", "err-item");
      item.innerHTML =
        `<div class="topic">${esc(topicLabel(err.topic))}` +
        `<span class="badge ${err.severity === "major" ? "major" : "minor"}">${esc(err.severity)}</span></div>` +
        `<div class="diff"><span class="from">${esc(err.student_text)}</span> → <span class="to">${esc(err.correct_text)}</span></div>` +
        `<div class="why">${esc(err.explanation)}</div>`;
      box.appendChild(item);
    });
  } else if (r.correct) {
    box.appendChild(el("p", "muted", t("noErrors")));
  }
}

function showError(sel, msg) {
  const box = $(sel);
  box.classList.remove("hidden");
  box.innerHTML = "";
  box.appendChild(el("div", "error-banner", t("error.prefix") + esc(msg)));
}

// --- Moje błędy --------------------------------------------------------------

$("#btn-refresh-errors").addEventListener("click", loadErrors);

async function loadErrors() {
  showLoader("loader.loading");
  try {
    const [stats, errors] = await Promise.all([
      api("/api/stats?lang=" + LANG),
      api("/api/errors?lang=" + LANG),
    ]);
    renderStats(stats);
    renderErrorsList(errors);
  } catch (e) {
    showError("#errors-list", e.message);
  } finally { hideLoader(); }
}

function renderStats(stats) {
  const box = $("#stats");
  box.innerHTML = "";
  if (!stats.length) { box.appendChild(el("p", "stat-empty", t("stats.empty"))); return; }
  const max = Math.max(...stats.map((s) => s.count));
  stats.forEach((s) => {
    const row = el("div", "stat-row");
    row.innerHTML =
      `<span class="name">${esc(s.topic_label || topicLabel(s.topic))}</span>` +
      `<span class="bar"><span style="width:${(s.count / max) * 100}%"></span></span>` +
      `<span class="count">${esc(s.count)}×</span>`;
    box.appendChild(row);
  });
}

function renderErrorsList(errors) {
  const box = $("#errors-list");
  box.innerHTML = "";
  if (!errors.length) { box.appendChild(el("p", "stat-empty", t("journal.empty"))); return; }
  errors.forEach((err) => {
    const item = el("div", "err-item");
    const date = (err.created_at || "").slice(0, 10);
    item.innerHTML =
      `<div class="topic">${esc(err.topic_label || topicLabel(err.topic))}` +
      `<span class="badge ${err.severity === "major" ? "major" : "minor"}">${esc(err.severity)}</span>` +
      `<span class="muted" style="float:right;font-weight:400;text-transform:none;letter-spacing:0">${esc(date)}</span></div>` +
      `<div class="diff"><span class="from">${esc(err.student_text)}</span> → <span class="to">${esc(err.correct_text)}</span></div>` +
      `<div class="why">${esc(err.explanation)}</div>`;
    const btn = el("button", "practice-btn", t("errors.practiceThis"));
    btn.addEventListener("click", () => focusOnError(err));
    item.appendChild(btn);
    box.appendChild(item);
  });
}

// --- Tipy (tryb skupienia) ---------------------------------------------------

let tipsError = null;
let tipsExercise = null;

async function loadTips(exclude) {
  showLoader("loader.loading");
  try {
    const url = "/api/tips/focus?lang=" + LANG + (exclude ? "&exclude=" + exclude : "");
    const data = await api(url);
    renderGoal(data.progress);
    setFocus(data.error);
  } catch (e) {
    showError("#tips-result", e.message);
  } finally { hideLoader(); }
}

function renderGoal(progress) {
  $("#tips-done").textContent = progress.done;
  $("#tips-goal").textContent = progress.goal;
  $("#tips-goal-input").value = progress.goal;
  const pct = progress.goal ? Math.min(100, (progress.done / progress.goal) * 100) : 0;
  $("#tips-goal-bar").style.width = pct + "%";
  const streak = progress.streak || 0;
  const streakEl = $("#tips-streak");
  streakEl.textContent = "🔥 " + streak + " " + t("tips.streakDays");
  streakEl.classList.toggle("is-zero", streak === 0);
}

async function refreshProgress() {
  try { renderGoal(await api("/api/tips/progress")); } catch (_) {}
}

// Skok z „Moje błędy" do Tipów z konkretnym błędem + automatyczne wygenerowanie ćwiczenia.
async function focusOnError(err) {
  activateTab("tips");
  setFocus(err);
  await refreshProgress();
  $("#tips-generate").click();
}

function setFocus(err) {
  tipsError = err;
  tipsExercise = null;
  $("#tips-exercise-area").classList.add("hidden");
  $("#tips-result").classList.add("hidden");
  $("#tips-generate").textContent = t("tips.generate");
  if (!err) {
    $("#tips-focus").classList.add("hidden");
    $("#tips-empty").classList.remove("hidden");
    return;
  }
  $("#tips-empty").classList.add("hidden");
  $("#tips-topic").textContent = err.topic_label || topicLabel(err.topic);
  $("#tips-from").textContent = err.student_text;
  $("#tips-to").textContent = err.correct_text;
  $("#tips-why").textContent = err.explanation || "";
  $("#tips-focus").classList.remove("hidden");
}

function renderTipsExercise(ex) {
  $("#tips-result").classList.add("hidden");
  $("#tips-instructions").textContent = ex.instructions || "";
  let q = esc(ex.question_text || "");
  if (ex.key_word) q += `\n\n${esc(t("kw.label"))}<span class="kw">${esc(ex.key_word)}</span>`;
  $("#tips-question").innerHTML = q;

  const area = $("#tips-answer-area");
  area.innerHTML = "";
  if (ex.options && ex.options.length) {
    const wrap = el("div", "options");
    ex.options.forEach((opt) => {
      const lbl = el("label");
      lbl.innerHTML = `<input type="radio" name="tips-mcq" value="${esc(opt)}"> ${esc(opt)}`;
      wrap.appendChild(lbl);
    });
    area.appendChild(wrap);
  } else {
    const input = el("input");
    input.id = "tips-answer"; input.type = "text"; input.placeholder = t("answer.ph");
    area.appendChild(input);
  }
  $("#tips-exercise-area").classList.remove("hidden");
}

$("#tips-new").addEventListener("click", () => loadTips(tipsError ? tipsError.id : undefined));

$("#tips-goal-save").addEventListener("click", async () => {
  const goal = parseInt($("#tips-goal-input").value, 10) || 1;
  try {
    const progress = await api("/api/tips/goal", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal }),
    });
    renderGoal(progress);
  } catch (e) { showError("#tips-result", e.message); }
});

$("#tips-generate").addEventListener("click", async () => {
  if (!tipsError) return;
  showLoader("loader.generating");
  try {
    tipsExercise = await api("/api/tips/exercise", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error_id: tipsError.id, lang: LANG }),
    });
    renderTipsExercise(tipsExercise);
  } catch (e) { showError("#tips-result", e.message); }
  finally { hideLoader(); }
});

$("#tips-grade").addEventListener("click", async () => {
  if (!tipsExercise) return;
  let answer;
  const checked = document.querySelector('input[name="tips-mcq"]:checked');
  if (checked) answer = checked.value;
  else { const inp = $("#tips-answer"); answer = inp ? inp.value.trim() : ""; }
  if (!answer) { alert(t("alert.answer")); return; }

  showLoader("loader.grading");
  try {
    const result = await api("/api/grade", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: tipsExercise.type, exercise_id: tipsExercise.id, student_answer: answer, lang: LANG }),
    });
    renderResult("#tips-result", result);
    // Błąd liczy się do dziennego celu dopiero po POPRAWNYM rozwiązaniu ćwiczenia
    // (maks. +1 na błąd/dzień — zapis jest idempotentny po stronie serwera).
    if (result.correct === true) {
      const progress = await api("/api/tips/complete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ error_id: tipsError.id }),
      });
      renderGoal(progress);
    }
    $("#tips-generate").textContent = t("tips.more");
  } catch (e) { showError("#tips-result", e.message); }
  finally { hideLoader(); }
});

// --- Statystyki --------------------------------------------------------------

const kindLabel = (k) => t("kind." + k) !== "kind." + k ? t("kind." + k) : k;
const fmtNum = (n) => Number(n || 0).toLocaleString(LANG === "en" ? "en-US" : "pl-PL");
const fmtCost = (c) => "$" + Number(c || 0).toFixed(Number(c) < 1 ? 4 : 2);

function statLine(label, value) {
  const row = el("div", "stat-line");
  row.innerHTML = `<span class="sl-label">${esc(label)}</span><span class="sl-value">${esc(value)}</span>`;
  return row;
}

async function loadStats() {
  showLoader("loader.loading");
  try {
    const [learning, usage] = await Promise.all([
      api("/api/stats/learning?lang=" + LANG),
      api("/api/stats/usage"),
    ]);
    renderLearning(learning);
    renderUsage(usage);
  } catch (e) {
    showError("#stats-usage", e.message);
  } finally { hideLoader(); }
}

function renderLearning(d) {
  const box = $("#stats-learning");
  box.innerHTML = "";
  const acc = d.accuracy == null ? "—" : Math.round(d.accuracy * 100) + "%";
  box.appendChild(statLine(t("stats.exercisesGenerated"), fmtNum(d.exercises_generated)));
  box.appendChild(statLine(t("stats.attempts"), fmtNum(d.attempts_total)));
  box.appendChild(statLine(t("stats.accuracy"),
    acc + (d.attempts_graded ? ` (${d.attempts_correct}/${d.attempts_graded})` : "")));
  box.appendChild(statLine(t("stats.reviews"), fmtNum(d.reviews_total)));
  box.appendChild(statLine(t("stats.errorsLogged"), fmtNum(d.errors_logged)));

  if (d.by_type && d.by_type.length) {
    box.appendChild(el("h3", "stat-sub", t("stats.byType")));
    const max = Math.max(...d.by_type.map((r) => r.attempts));
    d.by_type.forEach((r) => {
      const row = el("div", "stat-row");
      row.innerHTML =
        `<span class="name">${esc(r.label || r.type)}</span>` +
        `<span class="bar"><span style="width:${(r.attempts / max) * 100}%"></span></span>` +
        `<span class="count">${r.correct}/${r.attempts}</span>`;
      box.appendChild(row);
    });
  }
}

function renderUsage(d) {
  const box = $("#stats-usage");
  box.innerHTML = "";
  const total = d.total || {};
  if (!total.calls) {
    box.appendChild(el("p", "stat-empty", t("stats.empty")));
    return;
  }
  box.appendChild(statLine(t("stats.calls"), fmtNum(total.calls)));
  const costLine = statLine(t("stats.cost"), fmtCost(total.cost_usd));
  costLine.classList.add("cost-highlight");
  box.appendChild(costLine);
  box.appendChild(statLine(t("stats.tokensIn"), fmtNum(total.input_tokens)));
  box.appendChild(statLine(t("stats.tokensOut"), fmtNum(total.output_tokens)));
  box.appendChild(statLine(t("stats.tokensCacheWrite"), fmtNum(total.cache_creation_input_tokens)));
  box.appendChild(statLine(t("stats.tokensCacheRead"), fmtNum(total.cache_read_input_tokens)));
  box.appendChild(statLine(t("stats.avgTime"), Math.round(total.avg_duration_ms) + " ms"));

  if (d.lean) {
    box.appendChild(el("h3", "stat-sub", t("stats.leanTitle")));
    const leanUsed = statLine(t("stats.leanUsed"), fmtCost(d.lean.used_model));
    leanUsed.classList.add("cost-highlight");
    box.appendChild(leanUsed);
    box.appendChild(statLine(t("stats.leanSonnet"), fmtCost(d.lean.sonnet)));
    box.appendChild(el("p", "muted", t("stats.leanNote")));
  }

  if (d.by_kind && d.by_kind.length) {
    box.appendChild(el("h3", "stat-sub", t("stats.byKind")));
    d.by_kind.forEach((r) => {
      box.appendChild(statLine(`${kindLabel(r.kind)} (${r.calls}×)`, fmtCost(r.cost_usd)));
    });
  }
}

init();
