"use strict";

// --- i18n --------------------------------------------------------------------

const I18N = {
  pl: {
    "app.title": "FCE Trener",
    "tab.practice": "Ćwicz",
    "tab.external": "Sprawdź z zewnątrz",
    "tab.errors": "Moje błędy",
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
    "alert.fillExternal": "Uzupełnij treść zadania i odpowiedź.",
    "verdict.correct": "✓ Poprawnie",
    "verdict.incorrect": "✗ Do poprawy",
    "band.prefix": "Orientacyjna ocena: ",
    "corrected.label": "Poprawna wersja:",
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
    "tab.external": "Check external",
    "tab.errors": "My mistakes",
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
    "alert.fillExternal": "Fill in the exercise text and your answer.",
    "verdict.correct": "✓ Correct",
    "verdict.incorrect": "✗ Needs work",
    "band.prefix": "Estimated band: ",
    "corrected.label": "Correct version:",
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
}

document.querySelectorAll(".lang").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));

// --- Nawigacja zakładek ------------------------------------------------------

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("is-active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
    tab.classList.add("is-active");
    $("#view-" + tab.dataset.view).classList.add("is-active");
    if (tab.dataset.view === "errors") loadErrors();
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
  if (ex.options && ex.options.length) {
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
  let answer;
  const checked = document.querySelector('input[name="mcq"]:checked');
  if (checked) answer = checked.value;
  else { const inp = $("#practice-answer"); answer = inp ? inp.value.trim() : ""; }
  if (!answer) { alert(t("alert.answer")); return; }

  showLoader("loader.grading");
  try {
    const result = await api("/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: currentExercise.type, exercise_id: currentExercise.id, student_answer: answer, lang: LANG }),
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

  if (r.correct !== null && r.correct !== undefined) {
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

  if (Array.isArray(r.errors) && r.errors.length) {
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
    box.appendChild(item);
  });
}

init();
