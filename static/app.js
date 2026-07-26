"use strict";

// --- Stan i pomocnicze -------------------------------------------------------

let TAXONOMY = { exercise_types: [], topics: [] };
let TOPIC_LABELS = {};
let currentExercise = null; // {id, type, options, ...}

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function showLoader(text) {
  $("#loader-text").textContent = text || "Pracuję…";
  $("#loader").classList.remove("hidden");
}
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
  const t = TAXONOMY.exercise_types.find((x) => x.id === typeId);
  return t && t.area === "writing";
}

// --- Nawigacja zakładek ------------------------------------------------------

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("is-active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
    tab.classList.add("is-active");
    $("#view-" + tab.dataset.view).classList.add("is-active");
    if (tab.dataset.view === "errors") loadErrors();
  });
});

// --- Inicjalizacja taksonomii ------------------------------------------------

async function init() {
  try {
    TAXONOMY = await api("/api/taxonomy");
  } catch (e) {
    document.body.prepend(el("div", "error-banner", "Nie udało się wczytać taksonomii: " + esc(e.message)));
    return;
  }
  TAXONOMY.topics.forEach((t) => { TOPIC_LABELS[t.id] = t.label; });

  const fill = (sel) => {
    sel.innerHTML = "";
    TAXONOMY.exercise_types.forEach((t) => {
      const opt = el("option");
      opt.value = t.id; opt.textContent = t.label;
      sel.appendChild(opt);
    });
  };
  fill($("#practice-type"));
  fill($("#external-type"));

  $("#practice-type").addEventListener("change", populateTopics);
  $("#external-type").addEventListener("change", toggleExternalKeyword);
  populateTopics();
  toggleExternalKeyword();
}

function populateTopics() {
  const typeId = $("#practice-type").value;
  const t = TAXONOMY.exercise_types.find((x) => x.id === typeId);
  const sel = $("#practice-topic");
  sel.innerHTML = '<option value="">— dobierz automatycznie (wg moich błędów) —</option>';
  (t ? t.topics : []).forEach((topicId) => {
    const opt = el("option");
    opt.value = topicId; opt.textContent = TOPIC_LABELS[topicId] || topicId;
    sel.appendChild(opt);
  });
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
  showLoader("Generuję zadanie…");
  try {
    currentExercise = await api("/api/exercise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, topic }),
    });
    renderExercise(currentExercise);
  } catch (e) {
    showError("#exercise-area", e.message);
  } finally { hideLoader(); }
});

function renderExercise(ex) {
  $("#exercise-topic").textContent = "Temat: " + (TOPIC_LABELS[ex.topic] || ex.topic);
  $("#exercise-instructions").textContent = ex.instructions || "";
  let q = esc(ex.question_text || "");
  if (ex.key_word) q += `\n\nSłowo-klucz: <span class="kw">${esc(ex.key_word)}</span>`;
  $("#exercise-question").innerHTML = q;

  const area = $("#answer-area");
  area.innerHTML = "";
  if (ex.options && ex.options.length) {
    const wrap = el("div", "options");
    ex.options.forEach((opt, i) => {
      const lbl = el("label");
      lbl.innerHTML = `<input type="radio" name="mcq" value="${esc(opt)}"> ${esc(opt)}`;
      wrap.appendChild(lbl);
    });
    area.appendChild(wrap);
  } else {
    const input = el(isWritingType(ex.type) ? "textarea" : "input");
    input.id = "practice-answer";
    if (isWritingType(ex.type)) { input.rows = 10; input.placeholder = "Napisz swój tekst po angielsku…"; }
    else { input.type = "text"; input.placeholder = "Twoja odpowiedź…"; }
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
  if (!answer) { alert("Wpisz lub wybierz odpowiedź."); return; }

  showLoader("Sprawdzam odpowiedź…");
  try {
    const result = await api("/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: currentExercise.type, exercise_id: currentExercise.id, student_answer: answer }),
    });
    renderResult("#practice-result", result, currentExercise.type);
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
  if (!question_text || !student_answer) { alert("Uzupełnij treść zadania i odpowiedź."); return; }

  showLoader("Sprawdzam zadanie…");
  try {
    const result = await api("/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, question_text, student_answer, key_word }),
    });
    renderResult("#external-result", result, type);
  } catch (e) {
    showError("#external-result", e.message);
  } finally { hideLoader(); }
});

// --- Renderowanie wyniku oceny ----------------------------------------------

function renderResult(sel, r, type) {
  const box = $(sel);
  box.innerHTML = "";
  box.classList.remove("hidden");

  if (r.correct !== null && r.correct !== undefined) {
    const v = el("div", "verdict " + (r.correct ? "good" : "bad"),
      r.correct ? "✓ Poprawnie" : "✗ Do poprawy");
    box.appendChild(v);
  }
  if (r.band) box.appendChild(el("p", "band", "Orientacyjna ocena: " + esc(r.band)));

  if (Array.isArray(r.scores) && r.scores.length) {
    const wrap = el("div", "scores");
    r.scores.forEach((s) => {
      const row = el("div", "score-row");
      row.innerHTML =
        `<span class="name">${esc(TOPIC_LABELS[s.criterion] || s.criterion)}</span>` +
        `<span class="bar"><span style="width:${(s.score / 5) * 100}%"></span></span>` +
        `<span class="count">${esc(s.score)}/5</span>`;
      wrap.appendChild(row);
      if (s.comment) { const c = el("p", "why", esc(s.comment)); wrap.appendChild(c); }
    });
    box.appendChild(wrap);
  }

  if (r.corrected) box.appendChild(el("div", "corrected", "<strong>Poprawna wersja:</strong> " + esc(r.corrected)));
  if (r.feedback) box.appendChild(el("p", "feedback", esc(r.feedback)));

  if (Array.isArray(r.errors) && r.errors.length) {
    box.appendChild(el("h2", null, "Wykryte błędy (" + r.errors.length + ")"));
    r.errors.forEach((err) => {
      const item = el("div", "err-item");
      item.innerHTML =
        `<div class="topic">${esc(TOPIC_LABELS[err.topic] || err.topic)}` +
        `<span class="badge ${err.severity === "major" ? "major" : "minor"}">${esc(err.severity)}</span></div>` +
        `<div class="diff"><span class="from">${esc(err.student_text)}</span> → <span class="to">${esc(err.correct_text)}</span></div>` +
        `<div class="why">${esc(err.explanation)}</div>`;
      box.appendChild(item);
    });
  } else if (r.correct) {
    box.appendChild(el("p", "muted", "Brak błędów. Świetna robota!"));
  }
}

function showError(sel, msg) {
  const box = $(sel);
  box.classList.remove("hidden");
  box.innerHTML = "";
  box.appendChild(el("div", "error-banner", "Błąd: " + esc(msg)));
}

// --- Moje błędy --------------------------------------------------------------

$("#btn-refresh-errors").addEventListener("click", loadErrors);

async function loadErrors() {
  showLoader("Wczytuję…");
  try {
    const [stats, errors] = await Promise.all([api("/api/stats"), api("/api/errors")]);
    renderStats(stats);
    renderErrorsList(errors);
  } catch (e) {
    showError("#errors-list", e.message);
  } finally { hideLoader(); }
}

function renderStats(stats) {
  const box = $("#stats");
  box.innerHTML = "";
  if (!stats.length) { box.appendChild(el("p", "stat-empty", "Brak błędów w dzienniku — rozwiąż kilka zadań.")); return; }
  const max = Math.max(...stats.map((s) => s.count));
  stats.forEach((s) => {
    const row = el("div", "stat-row");
    row.innerHTML =
      `<span class="name">${esc(s.topic_label || s.topic)}</span>` +
      `<span class="bar"><span style="width:${(s.count / max) * 100}%"></span></span>` +
      `<span class="count">${esc(s.count)}×</span>`;
    box.appendChild(row);
  });
}

function renderErrorsList(errors) {
  const box = $("#errors-list");
  box.innerHTML = "";
  if (!errors.length) { box.appendChild(el("p", "stat-empty", "Dziennik jest pusty.")); return; }
  errors.forEach((err) => {
    const item = el("div", "err-item");
    const date = (err.created_at || "").slice(0, 10);
    item.innerHTML =
      `<div class="topic">${esc(err.topic_label || err.topic)}` +
      `<span class="badge ${err.severity === "major" ? "major" : "minor"}">${esc(err.severity)}</span>` +
      `<span class="muted" style="float:right;font-weight:400;text-transform:none;letter-spacing:0">${esc(date)}</span></div>` +
      `<div class="diff"><span class="from">${esc(err.student_text)}</span> → <span class="to">${esc(err.correct_text)}</span></div>` +
      `<div class="why">${esc(err.explanation)}</div>`;
    box.appendChild(item);
  });
}

init();
